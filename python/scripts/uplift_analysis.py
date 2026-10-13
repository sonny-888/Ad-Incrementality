"""Finding 6, step 1: train uplift models and score held-out users.

    py python/scripts/uplift_analysis.py     (about 10 minutes)
    py python/scripts/uplift_evaluate.py     (step 2: grading, seconds)

80% of users (random, seed 42) train, per outcome: a T-learner, an X-learner and a response model ("likely buyers").
One more model predicts each user's chance of being shown an ad if targeted, for the per-ad-view ranking.
The other 20% are scored; their doubly robust pseudo-outcomes (psi, which correct for the leak from finding 1) are
computed with cross-fitting inside the test set.

Writes data/processed/uplift_test_scores.parquet (per-user scores; stays local, never published).
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.ensemble import HistGradientBoostingClassifier

from incrementality.experiment import FEATURES
from incrementality.lift import aipw
from incrementality.uplift import fit_uplift

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "processed" / "criteo_uplift.parquet"
SCORES = ROOT / "data" / "processed" / "uplift_test_scores.parquet"
SEED = 42
TEST_SHARE = 0.2


def main() -> None:
    start = time.time()
    tbl = pq.read_table(DATA)
    X = np.column_stack([tbl.column(f).to_numpy() for f in FEATURES]).astype(np.float32)
    t = tbl.column("treatment").to_numpy().astype(np.int8)
    d = tbl.column("exposure").to_numpy().astype(np.int8)
    outcomes = {y: tbl.column(y).to_numpy().astype(np.int8) for y in ["visit", "conversion"]}
    del tbl

    test = np.random.default_rng(SEED).random(len(t)) < TEST_SHARE
    train = ~test
    saved = {"row": np.flatnonzero(test), "treatment": t[test], "exposure": d[test],
             **{y: v[test] for y, v in outcomes.items()}}

    treated_train = train & (t == 1)
    exposure_model = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1, early_stopping=True,
                                                    random_state=SEED).fit(X[treated_train], d[treated_train])
    saved["p_exposed"] = exposure_model.predict_proba(X[test])[:, 1]
    print(f"exposure model fitted ({time.time() - start:.0f}s)")

    propensity = None
    for name, y in outcomes.items():
        models = fit_uplift(X[train], t[train], y[train], seed=SEED)
        res, propensity = aipw(X[test], t[test], y[test].astype(float), seed=SEED, propensity=propensity)
        saved[f"{name}_psi"] = res.psi
        saved[f"{name}_x_learner"] = models.x_learner(X[test])
        saved[f"{name}_t_learner"] = models.t_learner(X[test])
        saved[f"{name}_response"] = models.response(X[test])
        print(f"{name}: models fitted and test users scored ({time.time() - start:.0f}s)")

    pq.write_table(pa.table(saved), SCORES)
    print(f"wrote {SCORES.relative_to(ROOT)} in {time.time() - start:.0f}s")


if __name__ == "__main__":
    main()
