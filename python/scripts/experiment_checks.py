"""Finding 1, experiment health: sample ratio, covariate balance and a classifier test on the Criteo data.

    py python/scripts/experiment_checks.py

Reads data/processed/criteo_uplift.parquet (run criteo_to_parquet.py first) and writes
results/experiment_checks.json, which later scripts and the report read numbers from.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import duckdb
import numpy as np
import pyarrow.parquet as pq

from incrementality.experiment import FEATURES, balance, classifier_test, srm

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "processed" / "criteo_uplift.parquet"
OUT = ROOT / "results" / "experiment_checks.json"
DESIGNED_SHARE = 0.85  # treatment ratio stated in the dataset documentation
CLASSIFIER_SAMPLE = 1_000_000
SEED = 42


def main() -> None:
    con = duckdb.connect()
    src = f"'{DATA.as_posix()}'"

    n_total, n_treated = con.execute(f"SELECT count(*), sum(treatment) FROM {src}").fetchone()
    ratio = srm(int(n_treated), int(n_total), DESIGNED_SHARE)
    print(f"SRM: treated share {ratio.observed_share:.5f} vs designed {DESIGNED_SHARE} "
          f"(chi2 {ratio.chi2:.2f}, p {ratio.p_value:.3g}) -> {'MISMATCH' if ratio.mismatch else 'ok'}")

    bal = balance(con, src)
    print("\nBalance (standardised mean difference, |SMD| < 0.1 is balanced):")
    print(bal.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    table = pq.read_table(DATA, columns=FEATURES + ["treatment"])
    rows = np.sort(np.random.default_rng(SEED).choice(table.num_rows, CLASSIFIER_SAMPLE, replace=False))
    sample = table.take(rows).to_pandas()
    del table
    clf = classifier_test(sample[FEATURES], sample["treatment"], seed=SEED)
    print(f"\nClassifier test on {len(sample):,} users: AUC {clf.auc:.4f} "
          f"(folds {', '.join(f'{a:.4f}' for a in clf.fold_aucs)}), "
          f"{clf.z:.1f} standard errors from a coin flip")
    # Placebo: same model, same users, treatment labels shuffled. Shows the AUC above 0.5 is not a modelling artefact.
    shuffled = sample["treatment"].sample(frac=1, random_state=SEED + 1).reset_index(drop=True)
    placebo = classifier_test(sample[FEATURES], shuffled, seed=SEED)
    print(f"Placebo (shuffled labels): AUC {placebo.auc:.4f}, {placebo.z:.1f} standard errors from a coin flip")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "srm": {**asdict(ratio), "mismatch": ratio.mismatch},
        "balance": bal.round(6).to_dict(orient="records"),
        "max_abs_smd": round(float(bal["smd"].abs().max()), 6),
        "smd_noise_se": float(np.sqrt(1 / n_treated + 1 / (n_total - n_treated))),
        "classifier": {**asdict(clf), "z": clf.z, "sample_size": len(sample), "seed": SEED},
        "classifier_placebo": {**asdict(placebo), "z": placebo.z},
    }, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
