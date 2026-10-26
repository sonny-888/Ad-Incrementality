"""Finding 7: is it worth the money?

    py python/scripts/money_analysis.py

From the experiment (conversions):
- caused share: of conversions credited to ads, the share the ads caused (results/lift_aipw.json, finding 5)
- concentration: share of caused conversions the best half of spend brings, ranking by likely buyers
  (results/uplift.json, finding 6)
Assumed, because the data has no prices or costs (ILLUSTRATIVE, swap in your own):
- the dashboard's attributed ROAS, and the profit margin on revenue

Uncertainty from the experiment is carried into every money figure by simulation. Writes results/money.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from incrementality.money import break_even_attributed_roas, draws, profit_per_pound, split_efficiency

ROOT = Path(__file__).resolve().parents[2]
AIPW = json.loads((ROOT / "results" / "lift_aipw.json").read_text(encoding="utf-8"))
UPLIFT = json.loads((ROOT / "results" / "uplift.json").read_text(encoding="utf-8"))
OUT = ROOT / "results" / "money.json"

ASSUMED_ROAS = 8.0  # illustrative dashboard ROAS for retargeting
ASSUMED_MARGIN = 0.30  # illustrative share of revenue kept as profit
ROAS_GRID = [4, 6, 8, 10, 12, 15]
MARGIN_GRID = [0.2, 0.3, 0.4, 0.5]
TOP_SPEND = 0.5
N_SIM, SEED = 200_000, 7


def interval(x: np.ndarray) -> dict:
    lo, hi = np.percentile(x, [2.5, 97.5])
    return {"estimate": float(np.median(x)), "lo": float(lo), "hi": float(hi)}


def main() -> None:
    c = AIPW["conversion"]
    caused = (c["caused_share"], c["caused_share_lo"], c["caused_share_hi"])
    top = next(s for s in UPLIFT["conversion"]["models"]["response"]["spend_capture"] if s["spend_share"] == TOP_SPEND)
    top_effect = (top["lift_share"], top["lo"], top["hi"])

    rng = np.random.default_rng(SEED)
    cs = draws(*caused, N_SIM, rng)
    te = np.clip(draws(*top_effect, N_SIM, rng), TOP_SPEND, 1)  # best half can't do worse than its spend share
    eff_top, eff_rest = split_efficiency(te, TOP_SPEND)

    def scenario(roas: float, margin: float) -> dict:
        iroas = roas * cs
        p_all, p_top, p_rest = (profit_per_pound(iroas * k, margin) for k in (1, eff_top, eff_rest))
        return {
            "dashboard_profit_per_pound": roas * margin - 1,
            "incremental_profit_per_pound": interval(p_all),
            "best_half_profit_per_pound": interval(p_top),
            "other_half_profit_per_pound": interval(p_rest),
            "incremental_roas": interval(iroas),
            # Cut the other half: spend halves, profit becomes half the spend at the best half's rate
            "profit_after_cut_vs_now": interval(np.where(p_all > 0, TOP_SPEND * p_top / p_all, np.nan)),
            "profit_change_per_pound_of_current_spend": interval(TOP_SPEND * p_top - p_all),
        }

    base = scenario(ASSUMED_ROAS, ASSUMED_MARGIN)
    grid = {f"{r}x_{int(m * 100)}pct": {k: base_k for k, base_k in scenario(r, m).items()
                                       if k in ("dashboard_profit_per_pound", "incremental_profit_per_pound",
                                                "other_half_profit_per_pound")}
            for r in ROAS_GRID for m in MARGIN_GRID}
    breakeven = {f"{int(m * 100)}pct": {
        "all_spend": interval(break_even_attributed_roas(m, cs)),
        "best_half": interval(break_even_attributed_roas(m, cs) / eff_top),
        "other_half": interval(break_even_attributed_roas(m, cs) / eff_rest),
    } for m in MARGIN_GRID}

    out = {
        "assumptions": {"attributed_roas": ASSUMED_ROAS, "margin": ASSUMED_MARGIN, "illustrative": True,
                        "spend_proxy": "ad views", "top_spend_share": TOP_SPEND},
        "from_experiment": {"caused_share": dict(zip(["estimate", "lo", "hi"], caused)),
                            "best_half_effect_share": dict(zip(["estimate", "lo", "hi"], top_effect)),
                            "best_half_efficiency": interval(eff_top), "other_half_efficiency": interval(eff_rest)},
        "base": base, "grid": grid, "break_even_attributed_roas": breakeven,
        "conversions_lost_by_cut": 1 - top_effect[0],
    }
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")

    f = lambda d: f"{d['estimate']:+.2f} ({d['lo']:+.2f} to {d['hi']:+.2f})"
    print(f"Assumed: dashboard ROAS {ASSUMED_ROAS}, margin {ASSUMED_MARGIN:.0%} (illustrative)")
    print(f"Profit per pound: dashboard {base['dashboard_profit_per_pound']:+.2f} | incremental {f(base['incremental_profit_per_pound'])}"
          f" | best half {f(base['best_half_profit_per_pound'])} | other half {f(base['other_half_profit_per_pound'])}")
    print(f"Cut the other half: profit x{base['profit_after_cut_vs_now']['estimate']:.2f} "
          f"({base['profit_after_cut_vs_now']['lo']:.2f} to {base['profit_after_cut_vs_now']['hi']:.2f}), "
          f"caused conversions -{1 - top_effect[0]:.0%}")
    print("Break-even dashboard ROAS by margin (all / best half / other half):")
    for m, b in breakeven.items():
        print(f"  {m}: {b['all_spend']['estimate']:.1f} / {b['best_half']['estimate']:.1f} / {b['other_half']['estimate']:.1f}")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
