"""Sensitivity analysis for the leak correction (findings 1, 3 and 5).

    py python/scripts/sensitivity_analysis.py     (about 20 minutes)

The adjusted estimates rest on one assumption: the 12 pre-treatment features capture how the treated share varied
across the merged advertiser tests. This script asks how much the answer depends on the modelling choices used to
make that adjustment:

- six specifications: raw difference; linear (Lin) adjustment; and, with two different model families (gradient
  boosting and logistic regression), doubly robust (AIPW), weighting only (IPW) and outcome model only;
- balance after weighting: if the propensity model captured the leak, the weighted feature gaps should be near zero.

Reads data/processed/criteo_uplift.parquet, results/lift.json; writes results/sensitivity.json.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from incrementality.experiment import FEATURES
from incrementality.lift import aipw, ipw_effect, ratio_of_effects, weighted_smd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "processed" / "criteo_uplift.parquet"
LIFT = json.loads((ROOT / "results" / "lift.json").read_text(encoding="utf-8"))
OUT = ROOT / "results" / "sensitivity.json"
SEED = 42


def main() -> None:
    start = time.time()
    tbl = pq.read_table(DATA)
    X = np.column_stack([tbl.column(f).to_numpy() for f in FEATURES])
    t = tbl.column("treatment").to_numpy().astype(float)
    d = tbl.column("exposure").to_numpy().astype(float)
    ys = {o: tbl.column(o).to_numpy().astype(float) for o in ["visit", "conversion"]}
    del tbl

    rows = []
    for o in ["visit", "conversion"]:
        L = LIFT[o]
        rc = L["itt"]["rate_c"]
        rows.append({"outcome": o, "specification": "Raw difference", "family": "none",
                     "lift": L["itt"]["rel"], "lo": L["itt"]["rel_lo"], "hi": L["itt"]["rel_hi"],
                     "caused_share": L["exposed"]["caused_share"] if o == "conversion" else None})
        rows.append({"outcome": o, "specification": "Linear adjustment (Lin)", "family": "linear",
                     "lift": L["itt_adjusted"]["estimate"] / rc, "lo": L["itt_adjusted"]["lo"] / rc,
                     "hi": L["itt_adjusted"]["hi"] / rc, "caused_share": None})

    balance = {"raw_max_abs_smd": float(np.max(np.abs(
        (X[t == 1].mean(0) - X[t == 0].mean(0)) / np.sqrt((X[t == 1].var(0) + X[t == 0].var(0)) / 2))))}
    for family in ["boosting", "logistic"]:
        exposure, e = aipw(X, t, d, seed=SEED, control_outcome_is_zero=True, learner=family)
        smd = weighted_smd(X, t, e)
        balance[f"{family}_weighted_max_abs_smd"] = float(np.max(np.abs(smd)))
        balance[f"{family}_propensity_p01_p99"] = [float(np.percentile(e, 1)), float(np.percentile(e, 99))]
        print(f"{family}: propensity fitted; max |SMD| after weighting {np.max(np.abs(smd)):.4f} "
              f"({time.time() - start:.0f}s)", flush=True)
        for o, y in ys.items():
            rc = LIFT[o]["itt"]["rate_c"]
            res, _ = aipw(X, t, y, seed=SEED, propensity=e, learner=family)
            ipw = ipw_effect(t, y, e)
            reg = float(np.mean(res.m1 - res.m0))
            rate_exposed = float(y[d == 1].mean())
            cace, _ = ratio_of_effects(res, exposure)
            label = "gradient boosting" if family == "boosting" else "logistic regression"
            rows += [
                {"outcome": o, "specification": f"Doubly robust, {label}", "family": family,
                 "lift": res.estimate / rc, "lo": res.lo / rc, "hi": res.hi / rc,
                 "caused_share": cace / rate_exposed if o == "conversion" else None},
                {"outcome": o, "specification": f"Weighting only (IPW), {label}", "family": family,
                 "lift": ipw.estimate / rc, "lo": ipw.lo / rc, "hi": ipw.hi / rc, "caused_share": None},
                {"outcome": o, "specification": f"Outcome model only, {label}", "family": family,
                 "lift": reg / rc, "lo": None, "hi": None, "caused_share": None},
            ]
            print(f"  {o}: AIPW {res.estimate / rc:+.1%}  IPW {ipw.estimate / rc:+.1%}  outcome-only {reg / rc:+.1%} "
                  f"({time.time() - start:.0f}s)", flush=True)

    adjusted = [r for r in rows if r["specification"] != "Raw difference"]
    summary = {o: {"adjusted_min": min(r["lift"] for r in adjusted if r["outcome"] == o),
                   "adjusted_max": max(r["lift"] for r in adjusted if r["outcome"] == o),
                   "raw": next(r["lift"] for r in rows if r["outcome"] == o and r["specification"] == "Raw difference")}
               for o in ["visit", "conversion"]}
    caused = [r["caused_share"] for r in rows if r["caused_share"] is not None and r["family"] != "none"]
    summary["caused_share_adjusted_range"] = [min(caused), max(caused)]
    OUT.write_text(json.dumps({"rows": rows, "balance": balance, "summary": summary, "seed": SEED}, indent=1),
                   encoding="utf-8")
    print(json.dumps(summary, indent=1))
    print(f"wrote {OUT.relative_to(ROOT)} in {time.time() - start:.0f}s")


if __name__ == "__main__":
    main()
