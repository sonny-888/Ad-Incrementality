"""Write the five walkthrough notebooks (run them with run_all.py, or nbconvert --execute).

    py python/scripts/build_notebooks.py

Each notebook explains one stage in plain English, runs the quick parts live and loads the slow parts
(doubly robust lift, uplift training, the 2,700 geo simulations) from results/, which run_all.py rebuilds.
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[2]
NB = ROOT / "notebooks"

SETUP = """\
from pathlib import Path
import json

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from IPython.display import Image, display

from incrementality.style import PAL, SOURCE, SOURCE_IOWA, apply, finish

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
CRITEO = (ROOT / "data" / "processed" / "criteo_uplift.parquet").as_posix()
results = lambda name: json.loads((ROOT / "results" / f"{name}.json").read_text(encoding="utf-8"))
show = lambda name: display(Image(filename=str(ROOT / "figures" / name), width=900))
pd.set_option("display.float_format", "{:,.4f}".format)
apply()"""

NOTEBOOKS = {
    "01_data.ipynb": [
        ("md", """# 01 Data: the Criteo test and the Iowa panel

Two datasets, two jobs:

- **Criteo Uplift v2.1**: a real randomised ad test on 13,979,592 users. Findings 1 to 7 and 9.
- **Iowa Liquor Sales**: real weekly sales for Iowa's counties, used with *simulated* campaigns to grade geo-test methods (finding 8).

Both are prepared by scripts in `python/scripts/` (`criteo_to_parquet.py`, `iowa_panel.py`); this notebook looks at what came out."""),
        ("code", SETUP),
        ("md", """## Criteo: who was treated, who saw an ad, who converted

85% of users were randomly allowed to see the retailer's ads (treatment); 15% had ads blocked (control). Being allowed to see ads doesn't mean you will: `exposure` records who actually saw one."""),
        ("code", """cells = duckdb.sql(f\"\"\"
    SELECT treatment, exposure, count(*) AS users,
           avg(visit) AS visit_rate, avg(conversion) AS conversion_rate
    FROM '{CRITEO}' GROUP BY ALL ORDER BY ALL\"\"\").df()
cells["share_of_all_users"] = cells["users"] / cells["users"].sum()
cells"""),
        ("md", """Three things to notice:

1. **No control user saw an ad** (there is no `treatment = 0, exposure = 1` row). That makes the effect of seeing an ad measurable (notebook 03).
2. **Only about 3.6% of treated users saw an ad.** The rest were allowed to but never were.
3. **Users who saw an ad convert far more often** than everyone else. Notebook 03 shows how little of that gap the ad itself caused."""),
        ("code", """duckdb.sql(f"SUMMARIZE SELECT * FROM '{CRITEO}'").df()[
    ["column_name", "min", "max", "avg", "std", "null_percentage"]]"""),
        ("md", """The 12 features (`f0` to `f11`) are anonymised and randomly projected by Criteo, so they can't be interpreted, only used. No column has missing values.

## Iowa: weekly sales per county

Pulled with `sql/iowa_county_week.sql` in BigQuery, then cleaned by `iowa_panel.py`: county names standardised, three counties with many empty weeks left out, and the remaining holiday-week gaps filled from neighbouring weeks."""),
        ("code", """s = results("iowa_panel")
panel = pd.read_parquet(ROOT / "data" / "processed" / "iowa_log_sales.parquet")  # log of weekly sales
print(f"{s['counties']} counties x {s['weeks']} weeks, {s['first_week']} to {s['last_week']}")
print("Left out for gaps:", ", ".join(f"{c} ({v:.0%} of weeks empty)" for c, v in s["counties_left_out_for_gaps"].items()))
print(f"County-weeks filled: {s['county_weeks_missing_or_zero']} of {s['counties'] * s['weeks']:,}")"""),
        ("code", """state = np.exp(panel).sum(axis=1) / 1e6
fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(state.index, state, color=PAL["primary"], lw=1)
ax.yaxis.set_major_formatter(lambda v, _: f"${v:.0f}M")
finish(fig, ax, "Iowa liquor sales swing from week to week, with deep holiday dips",
       "Weekly wholesale liquor sales across the 96 counties", source=SOURCE_IOWA)
plt.show()"""),
        ("md", """Weekly sales are lumpy because stores order in batches, and holiday weeks (Labor Day, Memorial Day, Thanksgiving) dip sharply. That noise is exactly what makes geo tests hard (notebook 05)."""),
    ],
    "02_experiment_checks.ipynb": [
        ("md", """# 02 Experiment checks (finding 1)

Before trusting any lift number, check that the randomisation worked. Three checks: the treated share, balance on the features, and whether a model can tell the groups apart. Write-up: `docs/experiment_health.md`."""),
        ("code", SETUP),
        ("code", """from incrementality.experiment import FEATURES, balance, classifier_test, srm

con = duckdb.connect()
n_total, n_treated = con.execute(f"SELECT count(*), sum(treatment) FROM '{CRITEO}'").fetchone()
r = srm(int(n_treated), int(n_total), 0.85)
print(f"Treated share {r.observed_share:.5f} vs designed 0.85: chi-square p = {r.p_value:.3f}, mismatch: {r.mismatch}")"""),
        ("md", """The split is exactly as designed. (So exactly that Criteo probably fixed it when building the file, so this check confirms the file is complete rather than proving the original tests were clean.)

**Balance:** standardised mean difference (SMD) is the gap between group averages in units of the feature's spread. Under 0.1 is the usual "balanced" line."""),
        ("code", """bal = balance(con, f"'{CRITEO}'")
bal"""),
        ("code", "show(\"experiment/balance.png\")"),
        ("md", """Every gap is under 0.05. But with 14 million users, chance alone moves an SMD by only about 0.00075, so these small gaps are real.

**Classifier test:** if assignment were random, no model could predict it from the features (AUC 0.5). The full check on 1 million users is in `results/experiment_checks.json`; here is a quicker live version on 200,000 users, plus a placebo with shuffled labels."""),
        ("code", """sample = duckdb.sql(f"SELECT {', '.join(FEATURES)}, treatment FROM '{CRITEO}' USING SAMPLE 200000 ROWS (reservoir, 7)").df()
live = classifier_test(sample[FEATURES], sample["treatment"], folds=3, seed=7)
shuffled = sample["treatment"].sample(frac=1, random_state=8).reset_index(drop=True)
placebo = classifier_test(sample[FEATURES], shuffled, folds=3, seed=7)
full = results("experiment_checks")
pd.DataFrame({
    "AUC": [live.auc, placebo.auc, full["classifier"]["auc"], full["classifier_placebo"]["auc"]],
    "standard errors from 0.5": [live.z, placebo.z, full["classifier"]["z"], full["classifier_placebo"]["z"]],
}, index=["live, 200k users", "live placebo", "full, 1M users", "full placebo"])"""),
        ("md", """A model beats a coin flip by a hair, and the placebo shows that edge is real. Criteo's paper explains why: the file merges several advertisers' tests that had different treated shares. The features were logged before any ad was shown, so notebook 03 adjusts for them."""),
    ],
    "03_lift.ipynb": [
        ("md", """# 03 Lift: naive view, estimated lift, effect of seeing an ad, and money (findings 2 to 5 and 7)

Write-ups: `docs/lift.md`, `docs/attribution_vs_incrementality.md`, `docs/money.md`.

*All absolute numbers describe this benchmark file: Criteo sub-sampled it so its real incrementality can't be recovered.*"""),
        ("code", SETUP),
        ("code", """from linearmodels.iv import IV2SLS

from incrementality.lift import exposed_effect, rate_diff

g = duckdb.sql(f\"\"\"SELECT treatment, exposure, count(*) AS n, sum(conversion) AS conv, sum(visit) AS visit
                    FROM '{CRITEO}' GROUP BY ALL\"\"\").df().set_index(["treatment", "exposure"])
e, nt, c = g.loc[(1, 1)], g.loc[(1, 0)], g.loc[(0, 0)]
unexposed = nt + c"""),
        ("md", "## Finding 2: the naive view (what a dashboard does)"),
        ("code", """naive = rate_diff(e["conv"], e["n"], unexposed["conv"], unexposed["n"])
print(f"Saw an ad: {naive.rate_t:.2%}   Didn't: {naive.rate_c:.2%}   Looks like {naive.rate_t / naive.rate_c:.0f}x")"""),
        ("md", "## Finding 3: the estimated lift for the whole treatment group (intent-to-treat)"),
        ("code", """itt = rate_diff(e["conv"] + nt["conv"], e["n"] + nt["n"], c["conv"], c["n"])
print(f"Raw: {itt.rel:+.1%} (95% interval {itt.rel_lo:+.1%} to {itt.rel_hi:+.1%})")
a = results("lift_aipw")
print(f"Adjusted for the features (doubly robust, cross-fitted; from results): "
      f"{a['conversion']['itt']['estimate'] / itt.rate_c:+.1%}")"""),
        ("code", "show(\"lift/raw_vs_adjusted.png\")"),
        ("md", """## Finding 4: the effect of actually seeing an ad

Random assignment shifts who sees an ad, and nobody in control can see one, so it works as an *instrument*: effect of seeing an ad = whole-group lift / share who saw one. Two-stage least squares (2SLS) gives the same number with a robust interval."""),
        ("code", """ex = exposed_effect(e["conv"], e["n"], nt["conv"], nt["n"], c["conv"], c["n"])
cols = duckdb.sql(f"SELECT conversion, exposure, treatment FROM '{CRITEO}'").df().astype(float)
iv = IV2SLS(cols["conversion"], np.ones(len(cols)), cols["exposure"], cols["treatment"]).fit(cov_type="robust")
print(f"Our formula: +{ex.cace * 100:.3f} points   2SLS: +{iv.params['exposure'] * 100:.3f} points")
print(f"Raw: users who saw an ad would have converted at {ex.baseline:.2%} anyway; with the ad {ex.rate_exposed:.2%}")
print(f"Adjusted (from results): {a['conversion']['baseline']:.2%} anyway, so the estimated causal effect is "
      f"{a['conversion']['rate_exposed'] / a['conversion']['baseline']:.1f}x, not {naive.rate_t / naive.rate_c:.0f}x")
del cols"""),
        ("code", "show(\"lift/naive_vs_caused.png\")"),
        ("md", """### How much does the correction depend on the method?

`sensitivity_analysis.py` (about 20 minutes) re-estimates the lift with two model families and three adjustment styles: doubly robust, weighting only and outcome model only. If weighting balances the features, the propensity model has captured the leak."""),
        ("code", """sens = results("sensitivity")
print({k: round(v, 4) if isinstance(v, float) else v for k, v in sens["balance"].items()})
pd.DataFrame(sens["rows"]).pivot(index="specification", columns="outcome", values="lift").round(3)"""),
        ("code", "show(\"lift/sensitivity.png\")"),
        ("md", "## Finding 5: credited vs caused"),
        ("code", "show(\"attribution/credited_vs_caused.png\")"),
        ("md", """## Finding 7: is it worth the money?

**Scenario analysis, not observed profit.** The data has no prices or costs, so two assumptions are stated openly (a dashboard ROAS of 8 and a 30% margin) and varied in the sensitivity tables in `docs/money.md`."""),
        ("code", """m = results("money")
b = m["base"]
pd.DataFrame({"profit per £1": [b["dashboard_profit_per_pound"], b["incremental_profit_per_pound"]["estimate"],
                                b["best_half_profit_per_pound"]["estimate"], b["other_half_profit_per_pound"]["estimate"]]},
             index=["what the dashboard implies", "incremental, all spend", "incremental, best half of spend",
                    "incremental, other half"])"""),
        ("code", "show(\"money/profit_per_pound.png\")"),
    ],
    "04_uplift.ipynb": [
        ("md", """# 04 Uplift: who is persuaded? (finding 6)

Models were trained on 80% of users and graded on the other 2.8 million (`uplift_analysis.py`, about 12 minutes). This notebook grades their saved scores. Write-up: `docs/uplift.md`."""),
        ("code", SETUP),
        ("code", """from incrementality.uplift import capture, capture_diff, spend_capture

s = pd.read_parquet(ROOT / "data" / "processed" / "uplift_test_scores.parquet")
cost = ((s["treatment"] == 1) & (s["exposure"] == 1)).astype(float).to_numpy()
print(f"{len(s):,} held-out users")"""),
        ("md", """**Grading.** Rank users by a model's score and ask what share of the ads' total effect the top 10%, 20%... hold. The effect per user comes from doubly robust pseudo-outcomes (`psi`), which correct for the leak found in notebook 02."""),
        ("code", """rows = []
for outcome in ["visit", "conversion"]:
    psi = s[f"{outcome}_psi"].to_numpy()
    for model in ["x_learner", "t_learner", "response"]:
        score = s[f"{outcome}_{model}"].to_numpy()
        rows.append({"outcome": outcome, "model": model,
                     **{f"top {k:.0%} of users": capture(score, psi, k).lift_share for k in (0.1, 0.2, 0.3)},
                     "half the spend": spend_capture(score, psi, cost, 0.5).lift_share})
pd.DataFrame(rows).set_index(["outcome", "model"]).style.format("{:.0%}")"""),
        ("code", """for outcome in ["visit", "conversion"]:
    psi = s[f"{outcome}_psi"].to_numpy()
    for k in (0.1, 0.2):
        d, lo, hi = capture_diff(s[f"{outcome}_x_learner"].to_numpy(), s[f"{outcome}_response"].to_numpy(), psi, k)
        print(f"{outcome:10s} top {k:.0%}: X-learner minus likely buyers {d:+.1%} (95% interval {lo:+.1%} to {hi:+.1%})")"""),
        ("md", """The effect is concentrated (about 91% in the top fifth), but the simple likely-buyer ranking finds those users as well as the uplift models do, except for visits on a tight budget."""),
        ("code", "show(\"uplift/uplift_curves.png\")"),
        ("code", "show(\"uplift/spend_curves.png\")"),
    ],
    "05_geo_tests.ipynb": [
        ("md", """# 05 Geo tests and holdout sizing (findings 8 and 9)

**Technical appendix: a methods benchmark, not a measured campaign.** Real Iowa county sales, with a campaign we add ourselves (a uniform lift in random counties, no spillover) so the true answer is known. Write-ups: `docs/geo.md`, `docs/recommendation.md`."""),
        ("code", SETUP),
        ("code", """from incrementality.geo import did, inject_lift, structural_ts, synthetic_control

panel = pd.read_parquet(ROOT / "data" / "processed" / "iowa_log_sales.parquet")
rng = np.random.default_rng(11)
test = list(rng.choice(panel.columns, 10, replace=False))
start, weeks, pre = len(panel) - 30, 8, 104
lifted = inject_lift(panel, test, start, weeks, 0.10)  # a +10% campaign we invented
pd.DataFrame([vars(m(lifted, test, start, weeks, pre)) for m in (did, synthetic_control, structural_ts)]).set_index("method")"""),
        ("code", "show(\"geo/example_test.png\")"),
        ("md", """One test proves little. `geo_simulation.py` ran 2,700 tests with **no** campaign (9 designs x 300) and recorded how often each method cried wolf and how big a campaign it would have caught."""),
        ("code", """g = results("geo")
rows = [{"method": m, "design": k, "false alarms": v["false_alarm_rate"],
         "smallest lift detected (size-adjusted)": v["min_detectable_lift_size_adjusted"]}
        for m, cells in g["methods"].items() for k, v in cells.items()]
pd.DataFrame(rows).pivot(index="design", columns="method").style.format("{:.0%}")"""),
        ("code", "show(\"geo/false_alarms.png\")"),
        ("code", "show(\"geo/min_detectable_lift.png\")"),
        ("md", "## Finding 9: how big must a user-level holdout be?"),
        ("code", """from incrementality.planning import users_needed

p = results("plan")["outcomes"]
table = pd.DataFrame({f"{share:.0%} held out": [users_needed(lift, share, p["conversion"]["base_rate"]) / 1e6
                                                for lift in (0.2, 0.1, 0.05)] for share in (0.1, 0.15, 0.5)},
                     index=["+20% conversion lift", "+10%", "+5%"])
table.style.format("{:.1f}M users")"""),
        ("code", "show(\"plan/holdout_sizing.png\")"),
    ],
}


def main() -> None:
    NB.mkdir(exist_ok=True)
    for name, cells in NOTEBOOKS.items():
        nb = nbf.v4.new_notebook()
        nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
        nb.cells = [nbf.v4.new_markdown_cell(src) if kind == "md" else nbf.v4.new_code_cell(src) for kind, src in cells]
        nbf.write(nb, NB / name)
        print(f"wrote notebooks/{name}")


if __name__ == "__main__":
    main()
