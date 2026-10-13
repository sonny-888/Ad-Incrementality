"""Finding 9: numbers behind the measurement plan. How big must a retargeting holdout be?

    py python/scripts/plan_analysis.py

Uses the control-group visit and conversion rates from the Criteo test (results/lift.json) as base rates, and checks
the sizing formula against the precision the Criteo test actually achieved. Writes results/plan.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from incrementality.planning import mde_relative, users_needed

ROOT = Path(__file__).resolve().parents[2]
LIFT = json.loads((ROOT / "results" / "lift.json").read_text(encoding="utf-8"))
AIPW = json.loads((ROOT / "results" / "lift_aipw.json").read_text(encoding="utf-8"))
OUT = ROOT / "results" / "plan.json"

USERS = [500_000, 1_000_000, 2_000_000, 5_000_000, 10_000_000, 20_000_000]
SHARES = [0.05, 0.10, 0.15, 0.50]
TARGETS = [0.05, 0.10, 0.20]


def main() -> None:
    out = {"users": USERS, "control_shares": SHARES, "outcomes": {}}
    for y in ["visit", "conversion"]:
        itt = LIFT[y]["itt"]
        p = itt["rate_c"]
        n = itt["n_t"] + itt["n_c"]
        share = itt["n_c"] / n
        # Check: formula's 95% half-width on the relative lift vs what the Criteo test actually got (raw estimate)
        se_log = np.sqrt((1 - p) / (itt["n_t"] * p) + (1 - p) / (itt["n_c"] * p))
        predicted_half = (1 + itt["rel"]) * np.expm1(1.959964 * se_log)
        actual_half = (itt["rel_hi"] - itt["rel_lo"]) / 2
        raw_se = (itt["diff_hi"] - itt["diff_lo"]) / (2 * 1.959964)
        adj_se = AIPW[y]["itt"]["se"]
        out["outcomes"][y] = {
            "base_rate": p,
            "check_criteo": {"users": n, "control_share": share, "predicted_half_width": float(predicted_half),
                             "actual_half_width_raw": float(actual_half)},
            "adjustment_effective_sample_multiplier": float((raw_se / adj_se) ** 2),
            "mde": {f"{s:.2f}": [float(mde_relative(u, s, p)) for u in USERS] for s in SHARES},
            "users_needed": {f"{t:.2f}": {f"{s:.2f}": users_needed(t, s, p) for s in SHARES} for t in TARGETS},
        }
        o = out["outcomes"][y]
        print(f"\n=== {y} (control rate {p:.3%}) ===")
        print(f"check vs Criteo ({n:,} users, {share:.0%} control): predicted +/-{predicted_half:.1%}, "
              f"actual +/-{actual_half:.1%}; feature adjustment worth x{o['adjustment_effective_sample_multiplier']:.2f} users")
        for s in SHARES:
            print(f"  {s:.0%} held out: MDE " + ", ".join(f"{u / 1e6:g}M users {m:.1%}" for u, m in zip(USERS, o["mde"][f'{s:.2f}'])))
        for t in TARGETS:
            print(f"  users to detect {t:.0%}: " + ", ".join(f"{s:.0%} held out {n_ / 1e6:.1f}M"
                                                          for s, n_ in zip(SHARES, o["users_needed"][f'{t:.2f}'].values())))
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
