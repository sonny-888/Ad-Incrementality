"""Export small, tidy CSVs for the Looker Studio dashboard (dashboard/data/), all read from results/.

    py python/scripts/export_dashboard_data.py

Every file is aggregated results; no user-level data leaves the project. Upload each CSV to Looker Studio with
the "File upload" connector (see dashboard/README.md).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from incrementality.planning import mde_relative

ROOT = Path(__file__).resolve().parents[2]
R = lambda n: json.loads((ROOT / "results" / f"{n}.json").read_text(encoding="utf-8"))
OUT = ROOT / "dashboard" / "data"
NAMES = {"x_learner": "Uplift model (X-learner)", "t_learner": "Uplift model (T-learner)",
         "response": "Likely buyers", "per_ad_view": "Effect per ad view",
         "did": "Difference-in-differences", "synthetic_control": "Synthetic control",
         "structural_ts": "CausalImpact-style"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    facts = json.loads((ROOT / "results" / "headline_facts.json").read_text(encoding="utf-8"))
    lift, aipw, up, money, geo, plan = (R(n) for n in ["lift", "lift_aipw", "uplift", "money", "geo", "plan"])
    tables = {}

    a = aipw["conversion"]
    f5, f6, f7 = (facts[k] for k in ["finding_5_credited_vs_caused", "finding_6_who_is_persuaded", "finding_7_money"])
    best_geo = min(geo["methods"][m]["20c_12w"]["min_detectable_lift_size_adjusted"] for m in ("did", "synthetic_control"))
    top20 = next(c for c in up["conversion"]["models"][up["conversion"]["best_model"]]["capture"] if c["top_share"] == 0.2)
    tables["kpis"] = pd.DataFrame([  # value is numeric for Looker Studio scorecards; format says how to show it
        ("Caused per 100 credited conversions", 100 * a["caused_share"], "number", f5["caused_per_100"],
         "95% interval " + f5["caused_per_100_interval"]),
        ("Naive effect of seeing an ad (multiple)", lift["conversion"]["naive"]["rate_t"] / lift["conversion"]["naive"]["rate_c"],
         "multiple", facts["finding_2_naive"]["naive_multiple"], "What a dashboard comparison shows"),
        ("Real effect of seeing an ad (multiple)", a["rate_exposed"] / a["baseline"], "multiple",
         facts["finding_4_effect_of_seeing_an_ad"]["real_multiple"], "From the randomised test"),
        ("Conversion lift, whole treated group", a["itt"]["estimate"] / lift["conversion"]["itt"]["rate_c"], "percent",
         facts["finding_3_itt"]["conversion_lift_adjusted"], "Adjusted (raw " + facts["finding_3_itt"]["conversion_lift_raw"] + ")"),
        ("Share of effect in top 20% of users", top20["lift_share"], "percent",
         f6["top20_share_of_conversion_effect"], "Conversions"),
        ("Real profit per £1 of ads", money["base"]["real_profit_per_pound"]["estimate"], "currency",
         f7["real_profit_per_pound"], "Dashboard implies " + f7["dashboard_profit_per_pound"] + " (illustrative)"),
        ("Smallest lift a 20-county, 12-week geo test detects", best_geo, "percent",
         facts["finding_8_geo"]["best_design_min_detectable_lift"], "Iowa sales, simulated campaigns"),
    ], columns=["kpi", "value", "format", "display", "note"])

    tables["lift_estimates"] = pd.DataFrame([
        {"outcome": o, "estimate": est, "lift": v, "lo": lo, "hi": hi}
        for o in ["visit", "conversion"]
        for est, v, lo, hi in [
            ("Raw difference", lift[o]["itt"]["rel"], lift[o]["itt"]["rel_lo"], lift[o]["itt"]["rel_hi"]),
            ("Adjusted, linear", lift[o]["itt_adjusted"]["rel"], lift[o]["itt_adjusted"]["lo"] / lift[o]["itt"]["rate_c"],
             lift[o]["itt_adjusted"]["hi"] / lift[o]["itt"]["rate_c"]),
            ("Adjusted, doubly robust", aipw[o]["itt"]["estimate"] / lift[o]["itt"]["rate_c"],
             aipw[o]["itt"]["lo"] / lift[o]["itt"]["rate_c"], aipw[o]["itt"]["hi"] / lift[o]["itt"]["rate_c"])]])

    tables["naive_vs_caused"] = pd.DataFrame([
        ("Didn't see an ad", "Conversion rate", lift["conversion"]["naive"]["rate_c"]),
        ("Saw an ad", "Would have bought anyway", a["baseline"]),
        ("Saw an ad", "Caused by the ad", a["cace"]["estimate"]),
    ], columns=["group", "component", "conversion_rate"])

    rows = []
    for o in ["visit", "conversion"]:
        for m, b in up[o]["models"].items():
            for kind, key in [("Share of users targeted", "curve"), ("Share of ad spend used", "spend_curve")]:
                if m == "per_ad_view" and key == "curve":
                    continue  # this ranking only makes sense against spend
                rows += [{"outcome": o, "ranking": NAMES[m], "x_axis": kind, "x": x, "share_of_effect": y}
                         for x, y in zip(b[key]["x"], b[key]["y"])]
    tables["targeting_curves"] = pd.DataFrame(rows)

    tables["money_sensitivity"] = pd.DataFrame([
        {"dashboard_roas": int(k.split("x_")[0]), "margin": int(k.split("_")[1].rstrip("pct")) / 100,
         "profit_per_pound_all_spend": v["real_profit_per_pound"]["estimate"],
         "profit_per_pound_other_half": v["other_half_profit_per_pound"]["estimate"],
         "dashboard_profit_per_pound": v["dashboard_profit_per_pound"]}
        for k, v in money["grid"].items()])
    tables["break_even"] = pd.DataFrame([
        {"margin": int(k.rstrip("pct")) / 100, "spend": part.replace("_", " "), "break_even_dashboard_roas": v["estimate"],
         "lo": v["lo"], "hi": v["hi"]}
        for k, parts in money["break_even_attributed_roas"].items() for part, v in parts.items()])

    tables["geo_designs"] = pd.DataFrame([
        {"method": NAMES[m], "test_counties": c["n_test"], "test_weeks": c["weeks"],
         "false_alarm_rate": c["false_alarm_rate"], "min_detectable_lift": c["min_detectable_lift_size_adjusted"],
         "typical_error": c["rmse_pct_points"]}
        for m, cells in geo["methods"].items() for c in cells.values()])

    users = np.unique(np.round(np.logspace(np.log10(2e5), np.log10(3e7), 40), -4))
    tables["holdout_sizing"] = pd.DataFrame([
        {"outcome": o, "holdout_share": s, "users": int(u), "min_detectable_lift": float(mde_relative(u, s, plan["outcomes"][o]["base_rate"]))}
        for o in ["visit", "conversion"] for s in plan["control_shares"] for u in users])

    for name, df in tables.items():
        df.to_csv(OUT / f"{name}.csv", index=False, float_format="%.6g", encoding="utf-8")
        print(f"dashboard/data/{name}.csv: {len(df)} rows")


if __name__ == "__main__":
    main()
