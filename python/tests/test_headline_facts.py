"""The README must quote the same numbers the results produce. If an analysis changes, this fails until the README
is updated, so written claims can't drift from the evidence."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("headline_facts", ROOT / "python" / "scripts" / "headline_facts.py")
headline_facts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(headline_facts)


def readme_phrases() -> list[str]:
    f = headline_facts.facts()
    n, m, l, u, g, p = (f["finding_5_credited_vs_caused"], f["finding_7_money"], f["finding_3_itt"],
                        f["finding_6_who_is_persuaded"], f["finding_8_geo"], f["finding_9_plan"])
    nv, e4, h1 = f["finding_2_naive"], f["finding_4_effect_of_seeing_an_ad"], f["finding_1_experiment_health"]
    return [
        f["data"]["criteo_users"],
        f"{n['caused_per_100']} of every 100",
        f"95% interval {n['caused_per_100_interval']}",
        f"about {n['attribution_overstatement']}",
        f"would read {n['caused_per_100_raw']} caused conversions per 100",
        f"{nv['naive_multiple']} vs {e4['real_multiple']}",
        f"already {nv['baseline_multiple']} likelier",
        f"Visit lift {l['visit_lift_raw']} raw, {l['visit_lift_adjusted']} adjusted",
        f"conversion lift {l['conversion_lift_raw']} raw, {l['conversion_lift_adjusted']} adjusted",
        f"AUC {h1['classifier_auc']}", f"AUC {h1['placebo_auc']}", f"more than {h1['max_abs_smd']} standard deviations",
        f"top 20% of users; half the spend, aimed at likely buyers, keeps {u['half_spend_keeps_conversions']}",
        f"**{u['top20_share_of_conversion_effect']}**",
        f"{m['dashboard_profit_per_pound']} vs {m['real_profit_per_pound']}",
        f"makes {m['other_half_profit_per_pound']} per £1",
        f"above {m['break_even_roas_30pct_margin']} to break even",
        f"needs {m['break_even_roas_other_half_30pct_margin']}",
        f"**{g['best_design_min_detectable_lift']}**",
        f"{g['causalimpact_style_false_alarms']} of the time",
        g["simulated_tests"],
        f"{p['users_for_10pct_conversion_lift_10pct_holdout']} users to see a +10% conversion lift",
        f"({p['users_for_10pct_conversion_lift_even_split']} with a 50/50 split)",
        f"visits read with {p['users_for_5pct_visit_lift_10pct_holdout']}",
    ]


def test_readme_quotes_match_results():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    missing = [phrase for phrase in readme_phrases() if phrase not in readme]
    assert not missing, "README out of date with results/; expected these phrases:\n" + "\n".join(missing)
