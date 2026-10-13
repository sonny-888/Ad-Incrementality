"""Finding 8, step 2: simulated geo tests on real Iowa county sales. Methods demonstration: real data, simulated campaign.

    py python/scripts/geo_simulation.py                     (about 12 minutes, uses all CPU cores)
    py python/scripts/geo_simulation.py --summarise-only    (re-summarise the saved runs in seconds)

For each test design (number of test counties x test length), run many simulated tests WITHOUT a campaign:
random test counties, random start week, 104 weeks of history before it. Each method estimates the "lift".
- With no campaign, any significant result is a false alarm; the spread of estimates is the method's accuracy.
- Every method learns only from pre-campaign weeks, so a campaign of +L% shifts its estimate and interval by exactly
  L% (in logs; proven in python/tests/test_geo.py). So each run also tells us whether a +L% campaign would have
  been detected, for every L, without re-running. That gives power and the minimum detectable lift.

Design choices fixed before seeing results: 5/10/20 test counties, 4/8/12 week tests, 300 runs per design,
104 pre-weeks, and no test window overlapping March to June 2020 (no one would run a geo test in a lockdown).

Reads data/processed/iowa_log_sales.parquet; writes results/geo.json and data/processed/geo_sims.parquet.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from incrementality.geo import did, structural_ts, synthetic_control

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "processed" / "iowa_log_sales.parquet"
OUT = ROOT / "results" / "geo.json"
SIMS = ROOT / "data" / "processed" / "geo_sims.parquet"

N_TEST = [5, 10, 20]
WEEKS = [4, 8, 12]
PRE = 104
REPS = 300
SEED = 2026
EXCLUDE = (pd.Timestamp("2020-03-01"), pd.Timestamp("2020-06-30"))
LIFT_GRID = np.round(np.arange(0, 0.4001, 0.0025), 4)  # widened from 20% after a 4-run trial showed noisy sales
METHODS = {"did": did, "synthetic_control": synthetic_control, "structural_ts": structural_ts}


def one_run(panel: pd.DataFrame, n_test: int, weeks: int, rep: int) -> list[dict]:
    rng = np.random.default_rng([SEED, n_test, weeks, rep])
    idx = panel.index
    ok = [s for s in range(PRE, len(idx) - weeks + 1)
          if not (idx[s] <= EXCLUDE[1] and idx[s + weeks - 1] >= EXCLUDE[0])]
    start = int(rng.choice(ok))
    test = list(rng.choice(panel.columns, n_test, replace=False))
    rows = []
    for name, method in METHODS.items():
        e = method(panel, test, start, weeks, PRE)
        rows.append({"n_test": n_test, "weeks": weeks, "rep": rep, "start": str(idx[start].date()), "method": name,
                     "est": np.log1p(e.lift), "lo": np.log1p(e.lo), "hi": np.log1p(e.hi)})
    return rows


def _mde(power: np.ndarray) -> float | None:
    return next((float(l) for l, p in zip(LIFT_GRID, power) if p >= 0.8), None)


def summarise(sims: pd.DataFrame) -> dict:
    """Per method and design: accuracy, false alarms, power curve, minimum detectable lift (MDE).

    Two MDEs. "Own intervals": detection when the method's own 95% interval excludes 0; flattering for a method
    whose intervals are too narrow. "Size-adjusted": detection when the estimate beats the 97.5th percentile of
    that method's own no-campaign estimates, so every method gets exactly a 5% two-sided false-alarm rate.
    """
    out = {}
    for (method, n_test, weeks), g in sims.groupby(["method", "n_test", "weeks"]):
        shift = np.log1p(LIFT_GRID)[:, None]
        power = ((g["lo"].to_numpy()[None, :] + shift) > 0).mean(axis=1)  # detected, in the right direction
        mde = _mde(power)
        threshold = np.percentile(g["est"], 97.5)
        power_adj = ((g["est"].to_numpy()[None, :] + shift) > threshold).mean(axis=1)
        out.setdefault(method, {})[f"{n_test}c_{weeks}w"] = {
            "n_test": int(n_test), "weeks": int(weeks), "runs": len(g),
            "bias_pct": float(np.expm1(g["est"].mean())),
            "rmse_pct_points": float(np.sqrt(np.mean(np.expm1(g["est"]) ** 2))),
            "false_alarm_rate": float(((g["lo"] > 0) | (g["hi"] < 0)).mean()),
            "median_interval_width_pct_points": float(np.median(np.expm1(g["hi"]) - np.expm1(g["lo"]))),
            "power": {f"{l:.4f}": float(p) for l, p in zip(LIFT_GRID, power)},
            "min_detectable_lift_80pct_power": mde,
            "power_size_adjusted": {f"{l:.4f}": float(p) for l, p in zip(LIFT_GRID, power_adj)},
            "min_detectable_lift_size_adjusted": _mde(power_adj),
        }
    return out


def main(summarise_only: bool = False) -> None:
    start = time.time()
    if summarise_only:  # re-summarise saved runs without re-simulating
        sims = pd.read_parquet(SIMS)
    else:
        panel = pd.read_parquet(PANEL)
        jobs = [(n, w, r) for n in N_TEST for w in WEEKS for r in range(REPS)]
        rows = Parallel(n_jobs=-2, batch_size=8)(delayed(one_run)(panel, n, w, r) for n, w, r in jobs)
        sims = pd.DataFrame([row for run in rows for row in run])
        sims.to_parquet(SIMS)
    out = {"design": {"n_test": N_TEST, "weeks": WEEKS, "pre_weeks": PRE, "runs_per_design": REPS, "seed": SEED,
                      "excluded_window": [str(EXCLUDE[0].date()), str(EXCLUDE[1].date())],
                      "label": "Methods demonstration: real data, simulated campaign"},
           "methods": summarise(sims)}
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")

    for method, cells in out["methods"].items():
        print(f"\n{method}")
        for key, c in cells.items():
            fmt = lambda v: f"{v:.1%}" if v is not None else ">40%"
            print(f"  {key:7s} false alarms {c['false_alarm_rate']:.1%} | rmse {c['rmse_pct_points']:.2%} | "
                  f"bias {c['bias_pct']:+.2%} | MDE own {fmt(c['min_detectable_lift_80pct_power'])}, "
                  f"size-adjusted {fmt(c['min_detectable_lift_size_adjusted'])}")
    print(f"\nwrote {OUT.relative_to(ROOT)} in {time.time() - start:.0f}s")


if __name__ == "__main__":
    import sys
    main(summarise_only="--summarise-only" in sys.argv)
