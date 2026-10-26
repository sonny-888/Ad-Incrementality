"""Every headline number quoted in the README, report and deck, read straight from results/*.json.

This is the single source of truth for figures in the written material: if a number appears in the README, the
report or the deck, it is produced here. python/tests/test_headline_facts.py fails if the README quotes a headline
that doesn't match.

    py python/scripts/headline_facts.py        (prints the facts and writes results/headline_facts.json)
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"


def _load(name: str) -> dict:
    return json.loads((RESULTS / f"{name}.json").read_text(encoding="utf-8"))


def pct(v: float, digits: int = 0) -> str:
    return f"{v:.{digits}%}"


def signed_pct(v: float, digits: int = 0) -> str:
    return f"{v:+.{digits}%}"


def pounds(v: float) -> str:
    return f"{'+' if v >= 0 else '-'}£{abs(v):.2f}"


def millions(v: float) -> str:
    return f"{v / 1e6:.1f} million"


def facts() -> dict[str, dict[str, str]]:
    exp, lift, aipw, up, money, geo, plan, panel, sens, budget = (
        _load(n) for n in ["experiment_checks", "lift", "lift_aipw", "uplift", "money", "geo", "plan", "iowa_panel",
                           "sensitivity", "budget_test"])
    ss, bt = sens["summary"], budget["outcomes"]["conversion"]
    adjusted = [r for r in sens["rows"] if r["outcome"] == "conversion" and r["specification"] != "Raw difference"]
    n_adjusted = len(adjusted)
    # For a fixed share of users who saw an ad, the caused share is proportional to the whole-group lift, so each
    # specification's caused share is scaled from the doubly robust estimate of its own model family (boosting for Lin).
    ref = {r["family"]: r for r in adjusted if r["caused_share"] is not None}
    caused_range = [r["lift"] * ref.get(r["family"], ref["boosting"])["caused_share"]
                    / ref.get(r["family"], ref["boosting"])["lift"] for r in adjusted]
    conv, visit = lift["conversion"], lift["visit"]
    a_conv, a_visit = aipw["conversion"], aipw["visit"]
    resp_half = lambda o: next(s for s in up[o]["models"]["response"]["spend_capture"] if s["spend_share"] == 0.5)
    cap20 = lambda o: next(c for c in up[o]["models"][up[o]["best_model"]]["capture"] if c["top_share"] == 0.2)
    fa_range = lambda m: [c["false_alarm_rate"] for c in geo["methods"][m].values()]
    best_geo = min(geo["methods"][m]["20c_12w"]["min_detectable_lift_size_adjusted"] for m in ("did", "synthetic_control"))
    be30 = money["break_even_attributed_roas"]["30pct"]
    conv_plan = plan["outcomes"]["conversion"]["users_needed"]

    return {
        "data": {
            "criteo_users": f"{exp['srm']['n_total']:,}",
            "treated_share": pct(exp["srm"]["observed_share"], 2),
            "iowa_counties": str(panel["counties"]),
            "iowa_weeks": str(panel["weeks"]),
        },
        "finding_1_experiment_health": {
            "max_abs_smd": f"{exp['max_abs_smd']:.3f}",
            "classifier_auc": f"{exp['classifier']['auc']:.3f}",
            "placebo_auc": f"{exp['classifier_placebo']['auc']:.3f}",
        },
        "finding_2_naive": {
            "naive_multiple": f"{conv['naive']['rate_t'] / conv['naive']['rate_c']:.0f}x",
            "exposed_conversion_rate": pct(a_conv["rate_exposed"], 2),
            "unexposed_conversion_rate": pct(conv["naive"]["rate_c"], 2),
            "baseline_conversion_rate": pct(a_conv["baseline"], 2),
            "baseline_multiple": f"{a_conv['baseline'] / conv['naive']['rate_c']:.0f}x",
        },
        "finding_3_itt": {
            "conversion_lift_raw": signed_pct(conv["itt"]["rel"]),
            "conversion_lift_adjusted": signed_pct(a_conv["itt"]["estimate"] / conv["itt"]["rate_c"]),
            "visit_lift_raw": signed_pct(visit["itt"]["rel"]),
            "visit_lift_adjusted": signed_pct(a_visit["itt"]["estimate"] / visit["itt"]["rate_c"]),
        },
        "finding_4_effect_of_seeing_an_ad": {
            "conversion_effect_points": f"+{a_conv['cace']['estimate'] * 100:.2f} points",
            "causal_multiple": f"{a_conv['rate_exposed'] / a_conv['baseline']:.1f}x",
        },
        "finding_5_credited_vs_caused": {
            "caused_per_100": f"{round(100 * a_conv['caused_share'])}",
            "caused_per_100_interval": f"{round(100 * a_conv['caused_share_lo'])} to {round(100 * a_conv['caused_share_hi'])}",
            "caused_per_100_raw": f"{round(100 * conv['exposed']['caused_share'])}",
            "attribution_overstatement": f"{1 / a_conv['caused_share']:.1f}x",
        },
        "finding_6_who_is_persuaded": {
            "top20_share_of_conversion_effect": pct(cap20("conversion")["lift_share"]),
            "top20_share_of_visit_effect": pct(cap20("visit")["lift_share"]),
            "half_spend_keeps_conversions": pct(resp_half("conversion")["lift_share"]),
            "half_spend_keeps_conversions_interval": f"{pct(resp_half('conversion')['lo'])} to {pct(resp_half('conversion')['hi'])}",
            "half_spend_keeps_visits": pct(resp_half("visit")["lift_share"]),
        },
        "finding_7_money": {
            "assumed_roas": f"{money['assumptions']['attributed_roas']:.0f}",
            "assumed_margin": pct(money["assumptions"]["margin"]),
            "dashboard_profit_per_pound": pounds(money["base"]["dashboard_profit_per_pound"]),
            "incremental_profit_per_pound": pounds(money["base"]["incremental_profit_per_pound"]["estimate"]),
            "best_half_profit_per_pound": pounds(money["base"]["best_half_profit_per_pound"]["estimate"]),
            "other_half_profit_per_pound": pounds(money["base"]["other_half_profit_per_pound"]["estimate"]),
            "profit_multiple_after_cut": f"{money['base']['profit_after_cut_vs_now']['estimate']:.1f}x",
            "break_even_roas_30pct_margin": f"{be30['all_spend']['estimate']:.1f}",
            "break_even_roas_other_half_30pct_margin": f"{be30['other_half']['estimate']:.1f}",
        },
        "finding_8_geo": {
            "did_false_alarms": f"{pct(min(fa_range('did')))} to {pct(max(fa_range('did')))}",
            "synthetic_control_false_alarms": f"{pct(min(fa_range('synthetic_control')))} to {pct(max(fa_range('synthetic_control')))}",
            "causalimpact_style_false_alarms": f"{pct(min(fa_range('structural_ts')))} to {pct(max(fa_range('structural_ts')))}",
            "best_design_min_detectable_lift": pct(best_geo),
            "simulated_tests": f"{sum(c['runs'] for c in geo['methods']['did'].values()):,}",
        },
        "sensitivity": {
            "adjusted_specifications": str(n_adjusted),
            "conversion_adjusted_range": f"{signed_pct(ss['conversion']['adjusted_min'])} to "
                                         f"{signed_pct(ss['conversion']['adjusted_max'])}",
            "visit_adjusted_range": f"{signed_pct(ss['visit']['adjusted_min'])} to {signed_pct(ss['visit']['adjusted_max'])}",
            "caused_per_100_adjusted_range": f"{round(100 * min(caused_range))} to {round(100 * max(caused_range))}",
            "weighted_max_abs_smd": f"{max(sens['balance']['boosting_weighted_max_abs_smd'], sens['balance']['logistic_weighted_max_abs_smd']):.3f}",
        },
        "budget_test": {
            "segment_share_of_users": pct(bt["segment_share_of_users"]),
            "predicted_lift": signed_pct(bt["predicted_lift"]),
            "predicted_lift_interval": f"{signed_pct(bt['predicted_lift_lo'])} to {signed_pct(bt['predicted_lift_hi'])}",
            "break_even_lift": signed_pct(bt["break_even_lift"]),
            "users_needed": millions(bt["users_needed"]),
        },
        "finding_9_plan": {
            "users_for_10pct_conversion_lift_10pct_holdout": millions(conv_plan["0.10"]["0.10"]),
            "users_for_10pct_conversion_lift_even_split": millions(conv_plan["0.10"]["0.50"]),
            "users_for_5pct_visit_lift_10pct_holdout": millions(plan["outcomes"]["visit"]["users_needed"]["0.05"]["0.10"]),
        },
    }


def main() -> None:
    f = facts()
    for group, items in f.items():
        print(f"\n== {group}")
        for k, v in items.items():
            print(f"  {k}: {v}")
    (RESULTS / "headline_facts.json").write_text(json.dumps(f, indent=1, ensure_ascii=False), encoding="utf-8")
    print("\nwrote results/headline_facts.json")


if __name__ == "__main__":
    main()
