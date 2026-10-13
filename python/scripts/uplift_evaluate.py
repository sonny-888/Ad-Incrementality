"""Finding 6, step 2: grade the uplift rankings on held-out users.

    py python/scripts/uplift_evaluate.py

Reads data/processed/uplift_test_scores.parquet (from uplift_analysis.py); writes results/uplift.json.

Two ways to grade a ranking:
- per user:  target the top X% of users; what share of the ads' total effect do they hold?
- per spend: target users best first until X% of spend is used; what share of the effect is captured?
  Spend is proxied by ad exposures (an advertiser pays when an ad is shown).

The headline cut-off (top 20% of users) was fixed before any result was seen. The per-ad-view ranking was added
after the first results showed that spend, not user count, is the right yardstick; it is marked exploratory.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from sklift.metrics import qini_auc_score

from incrementality.uplift import (area_vs_random, capture, capture_diff, exposure_share, overlap, spend_capture,
                                   spend_capture_diff, spend_curve, top_weights, uplift_curve)

ROOT = Path(__file__).resolve().parents[2]
SCORES = ROOT / "data" / "processed" / "uplift_test_scores.parquet"
OUT = ROOT / "results" / "uplift.json"
HEADLINE_TOP = 0.2
CUTS = [0.1, 0.2, 0.3, 0.5]
SPEND_CUTS = [0.25, 0.5, 0.75]
MIN_P_EXPOSED = 0.001  # floor before dividing, so users almost never shown an ad don't get absurd scores

warnings.filterwarnings("ignore", message=".*stable_cumsum.*", category=FutureWarning)


def main() -> None:
    s = pq.read_table(SCORES).to_pandas()
    t, d = s["treatment"].to_numpy(), s["exposure"].to_numpy()
    cost = ((t == 1) & (d == 1)).astype(float)
    out = {"n_test": len(s), "headline_top": HEADLINE_TOP, "min_p_exposed": MIN_P_EXPOSED,
           "exploratory": ["per_ad_view"]}

    for name in ["visit", "conversion"]:
        psi, y = s[f"{name}_psi"].to_numpy(), s[name].to_numpy()
        scores = {m: s[f"{name}_{m}"].to_numpy() for m in ["x_learner", "t_learner", "response"]}
        scores["per_ad_view"] = scores["x_learner"] / np.maximum(s["p_exposed"].to_numpy(), MIN_P_EXPOSED)

        block = {"test_effect": float(psi.mean()), "control_rate_test": float(y[t == 0].mean()), "models": {}}
        for model, sc in scores.items():
            ux, uy = uplift_curve(sc, psi)
            sx, sy = spend_curve(sc, psi, cost)
            block["models"][model] = {
                "area_vs_random": area_vs_random(sc, psi),
                "qini_auc_raw": float(qini_auc_score(y, sc, t)),
                "capture": [asdict(capture(sc, psi, c)) for c in CUTS],
                "exposure_share": [{"top_share": c, "share": exposure_share(sc, d, t, c)} for c in CUTS],
                "spend_capture": [{"spend_share": c, **asdict(spend_capture(sc, psi, cost, c))} for c in SPEND_CUTS],
                "curve": {"x": ux.round(4).tolist(), "y": uy.round(5).tolist()},
                "spend_curve": {"x": sx.round(4).tolist(), "y": sy.round(5).tolist()},
            }

        best = max(["x_learner", "t_learner"], key=lambda m: block["models"][m]["area_vs_random"])
        w = top_weights(scores[best], HEADLINE_TOP)
        block.update({
            "best_model": best,
            "vs_response": [dict(zip(["top_share", "diff", "lo", "hi"], (c, *capture_diff(scores[best], scores["response"], psi, c))))
                            for c in CUTS],
            "spend_vs_response": {m: [dict(zip(["spend_share", "diff", "lo", "hi"],
                                               (c, *spend_capture_diff(scores[m], scores["response"], psi, cost, c))))
                                      for c in SPEND_CUTS] for m in [best, "per_ad_view"]},
            "overlap_top_uplift_vs_top_response": overlap(scores[best], scores["response"], HEADLINE_TOP),
            "avg_effect_top": float((w * psi).sum() / w.sum()),
            "avg_effect_rest": float(((1 - w) * psi).sum() / (1 - w).sum()),
        })
        out[name] = block

        print(f"=== {name} (best uplift model: {best}) ===")
        for model, b in block["models"].items():
            caps = " ".join(f"{c['top_share']:.0%}u:{c['lift_share']:.0%}" for c in b["capture"])
            exps = " ".join(f"{e['share']:.0%}" for e in b["exposure_share"])
            spends = " ".join(f"{c['spend_share']:.0%}$:{c['lift_share']:.0%}" for c in b["spend_capture"])
            print(f"  {model:11s} area {b['area_vs_random']:+.3f} | {caps} | exposures {exps} | {spends}")
        print("  best vs response by users:", " ".join(f"{v['top_share']:.0%}:{v['diff']:+.1%}[{v['lo']:+.1%},{v['hi']:+.1%}]"
                                                         for v in block["vs_response"]))
        for m, vals in block["spend_vs_response"].items():
            print(f"  {m} vs response by spend:", " ".join(f"{v['spend_share']:.0%}:{v['diff']:+.1%}[{v['lo']:+.1%},{v['hi']:+.1%}]"
                                                           for v in vals))
        print(f"  overlap {block['overlap_top_uplift_vs_top_response']:.0%}, avg effect top 20% "
              f"{block['avg_effect_top']:+.5f} vs rest {block['avg_effect_rest']:+.5f}")

    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
