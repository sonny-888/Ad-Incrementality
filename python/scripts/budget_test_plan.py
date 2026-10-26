"""Finding 9: a concrete test proposal for cutting the weaker half of spend (a hypothesis, not a validated saving).

    py python/scripts/budget_test_plan.py

The held-out analysis (finding 6) predicts that the half of ad spend on the least likely buyers brings only about 16%
of the conversions the ads cause. Model predictions on historical data aren't proof: changing targeting can change
auction prices, frequency and who sees ads. So the proposal is a randomised test inside that segment:

- Segment: users ranked below the point where likely-buyer targeting has used half of today's ad views.
- Design: split the segment 50/50 into "keep ads" and "no ads" (holding out a weak segment costs little).
- Primary metric: incremental conversions in the segment (relative lift, no ads as baseline).
- Decision rule: cut the segment's spend if the lift is credibly below break-even, i.e. the one-sided 95% upper bound
  is below the lift at which the segment's spend pays for itself (scenario: dashboard ROAS 8, margin 30%).
- Size: users needed so that, if the model's prediction is right, the test reaches that conclusion 80% of the time.

Reads data/processed/uplift_test_scores.parquet and results/; writes results/budget_test.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from scipy import stats

from incrementality.uplift import spend_capture

ROOT = Path(__file__).resolve().parents[2]
SCORES = ROOT / "data" / "processed" / "uplift_test_scores.parquet"
MONEY = json.loads((ROOT / "results" / "money.json").read_text(encoding="utf-8"))
OUT = ROOT / "results" / "budget_test.json"


def users_to_separate(p0: float, lift_true: float, lift_threshold: float, alpha: float = 0.05,
                      power: float = 0.8) -> float:
    """Users (split 50/50) for a one-sided test to conclude lift < threshold when the true lift is lift_true."""
    gap = np.log1p(lift_threshold) - np.log1p(lift_true)
    z = stats.norm.ppf(1 - alpha) + stats.norm.ppf(power)
    p1 = p0 * (1 + lift_true)
    per_user_var = (1 - p1) / (0.5 * p1) + (1 - p0) / (0.5 * p0)  # variance of the log ratio x total users
    return float(per_user_var * (z / gap) ** 2)


def main() -> None:
    s = pq.read_table(SCORES).to_pandas()
    t, d = s["treatment"].to_numpy(), s["exposure"].to_numpy()
    cost = ((t == 1) & (d == 1)).astype(float)
    out = {"design": "50/50 randomised holdout inside the weaker-half segment", "outcomes": {}}
    for o in ["conversion", "visit"]:
        score, psi, y = s[f"{o}_response"].to_numpy(), s[f"{o}_psi"].to_numpy(), s[o].to_numpy()
        half = spend_capture(score, psi, cost, 0.5)  # top_share = share of users that uses half the ad views
        order = np.argsort(-score, kind="stable")
        weak = np.zeros(len(score), dtype=bool)
        weak[order[int(round(half.top_share * len(score))):]] = True
        p0 = float(y[weak & (t == 0)].mean())
        itt = float(psi[weak].mean())
        lift = itt / p0
        se = float(psi[weak].std(ddof=1) / np.sqrt(weak.sum())) / p0
        # Break-even for the segment: its spend pays when its incremental return per pound covers the margin.
        # Segment efficiency (incremental conversions per ad view vs the campaign average) at break-even, scenario:
        caused = MONEY["from_experiment"]["caused_share"]["estimate"]
        roas, margin = MONEY["assumptions"]["attributed_roas"], MONEY["assumptions"]["margin"]
        eff_pred = MONEY["from_experiment"]["other_half_efficiency"]["estimate"]
        eff_break_even = 1 / (roas * caused * margin)
        lift_break_even = lift * eff_break_even / eff_pred
        out["outcomes"][o] = {
            "segment_share_of_users": float(weak.mean()), "segment_share_of_ad_views": 0.5,
            "control_rate": p0, "predicted_lift": lift, "predicted_lift_lo": lift - 1.96 * se,
            "predicted_lift_hi": lift + 1.96 * se,
            "break_even_lift": lift_break_even, "break_even_efficiency": eff_break_even,
            "predicted_efficiency": eff_pred,
            "users_needed": users_to_separate(p0, lift, lift_break_even),
        }
        r = out["outcomes"][o]
        print(f"{o}: segment = {r['segment_share_of_users']:.0%} of users, half the ad views | control rate "
              f"{p0:.3%} | predicted lift {lift:+.1%} [{r['predicted_lift_lo']:+.1%}, {r['predicted_lift_hi']:+.1%}] | "
              f"break-even lift {lift_break_even:+.1%} | users needed {r['users_needed'] / 1e6:.1f}M")
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
