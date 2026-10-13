"""Findings 3 and 4, adjusted: doubly robust (AIPW) lift and effect of seeing an ad, on all users.

    py python/scripts/lift_aipw.py

Why: finding 1 found a small link between features and treatment, and the raw and linear-adjusted lift disagree.
The features were logged at treatment assignment (Diemert et al. 2021), so adjusting for them is valid. AIPW with
gradient-boosted models and 2-fold cross-fitting allows the link to be non-linear.

Reads data/processed/criteo_uplift.parquet and writes results/lift_aipw.json. Takes several minutes.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from incrementality.experiment import FEATURES
from incrementality.lift import aipw, ratio_of_effects

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "processed" / "criteo_uplift.parquet"
OUT = ROOT / "results" / "lift_aipw.json"
SEED = 42


def main() -> None:
    start = time.time()
    tbl = pq.read_table(DATA)
    X = np.column_stack([tbl.column(f).to_numpy() for f in FEATURES])
    t, d = tbl.column("treatment").to_numpy().astype(float), tbl.column("exposure").to_numpy().astype(float)
    outcomes = {y: tbl.column(y).to_numpy().astype(float) for y in ["visit", "conversion"]}
    del tbl

    exposure, e = aipw(X, t, d, seed=SEED, control_outcome_is_zero=True)
    print(f"propensity: mean {e.mean():.4f}, 1st-99th pct {np.percentile(e, 1):.3f} to {np.percentile(e, 99):.3f} "
          f"({time.time() - start:.0f}s)")
    out = {"seed": SEED, "folds": 2, "propensity": {
        "mean": float(e.mean()), "p01": float(np.percentile(e, 1)), "p99": float(np.percentile(e, 99))},
        "exposure_itt": {"estimate": exposure.estimate, "se": exposure.se}}

    for name, y in outcomes.items():
        itt, _ = aipw(X, t, y, seed=SEED, propensity=e)
        cace, cace_se = ratio_of_effects(itt, exposure)
        rate_exposed = float(y[d == 1].mean())
        baseline = rate_exposed - cace
        print(f"{name}: ITT {itt.estimate:+.5f} [{itt.lo:+.5f}, {itt.hi:+.5f}] | effect of seeing an ad "
              f"{cace:+.5f} [{cace - 1.96 * cace_se:+.5f}, {cace + 1.96 * cace_se:+.5f}] | "
              f"caused share {cace / rate_exposed:.1%} ({time.time() - start:.0f}s)")
        out[name] = {
            "itt": {"estimate": itt.estimate, "se": itt.se, "lo": itt.lo, "hi": itt.hi},
            "cace": {"estimate": cace, "se": cace_se, "lo": cace - 1.959964 * cace_se, "hi": cace + 1.959964 * cace_se},
            "rate_exposed": rate_exposed, "baseline": baseline,
            "caused_share": cace / rate_exposed,
            "caused_share_lo": (cace - 1.959964 * cace_se) / rate_exposed,
            "caused_share_hi": (cace + 1.959964 * cace_se) / rate_exposed,
        }

    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} in {time.time() - start:.0f}s")


if __name__ == "__main__":
    main()
