# Dashboard (Looker Studio)

**Live dashboard:** *link added once published*

Five pages that let a marketing team explore the findings: the headline numbers, raw vs corrected lift, who to target,
the money, and how to measure next time. Screenshots are in `screenshots/`.

## Data

Every chart reads one of the small CSVs in `data/`, written by `python/scripts/export_dashboard_data.py` from
`results/`. They are aggregated results only; no user-level data is uploaded anywhere.

| File | Rows | Used for |
|---|---|---|
| `kpis.csv` | 7 | Headline scorecards (`value` is numeric; `format` says how to show it) |
| `naive_vs_caused.csv` | 3 | Saw an ad vs didn't, split into "would have bought anyway" and "caused by the ad" |
| `lift_estimates.csv` | 6 | Raw vs adjusted lift for visits and conversions, with 95% intervals |
| `targeting_curves.csv` | 1,414 | Share of the ads' effect captured, by share of users targeted or of spend used |
| `money_sensitivity.csv` | 24 | Profit per £1 for dashboard ROAS 4 to 15 and margin 20% to 50% (illustrative) |
| `break_even.csv` | 12 | Break-even dashboard ROAS by margin, for all spend, the best half and the other half |
| `geo_designs.csv` | 27 | False alarms, smallest detectable lift and typical error per geo method and design |
| `holdout_sizing.csv` | 320 | Smallest detectable lift by number of users and share held out |

## Pages

| Page | What it shows | Charts |
|---|---|---|
| 1 Overview | The headline numbers | Scorecards from `kpis`; stacked bar from `naive_vs_caused` |
| 2 Lift | Why the raw comparison misleads, and the corrected lift | Bar chart and table from `lift_estimates` |
| 3 Targeting | Who to aim at, by head count and by spend | Line chart from `targeting_curves`, with outcome and x-axis controls |
| 4 Money | When retargeting pays | Two heatmap tables from `money_sensitivity`; table from `break_even` |
| 5 Measurement | How to measure next time | Heatmap and bar chart from `geo_designs`; line chart from `holdout_sizing` |

## How to build it (about an hour)

You do this in your own browser and Google account; nothing here needs a password or key.

### 1. Set up

1. Go to **lookerstudio.google.com** and click **Blank report**.
2. In "Add data to report", choose the **File Upload** connector and upload `data/kpis.csv`. Click **Add**.
3. Repeat **Resource > Manage added data sources > Add a data source > File Upload** for the other seven CSVs.
4. For each data source, open it (**Resource > Manage added data sources > Edit**) and check field types:
   set `lift`, `lo`, `hi`, `share_of_effect`, `x`, `false_alarm_rate`, `min_detectable_lift`, `typical_error`,
   `margin` and `holdout_share` to **Percent**; set the profit fields to **Currency (GBP)**.

### 2. Apply the Nordic style (same as Project 1)

**Theme and layout > Customise:**

| Setting | Value |
|---|---|
| Background | `#ECEFF4` |
| Chart backgrounds | `#FFFFFF`, rounded corners, border `#D8DEE9` |
| Text | `#2E3440` |
| Chart palette, in order | `#5E81AC`, `#BF616A`, `#EBCB8B`, `#A3BE8C`, `#B48EAD`, `#88C0D0` |
| Font | Roboto (Segoe UI isn't available in Looker Studio) |

On every page, add a slate header: **Insert > Rectangle** across the top, fill `#2E3440`, with a white text box
for the page title. Steel blue carries the data; aurora red `#BF616A` marks the one thing to look at.

### 3. Build the pages

**Page 1, Overview**
- Seven **Scorecards** from `kpis`: metric `value`, and a chart filter `kpi` equals each KPI name. Set the number
  format from the `format` column (Percent, Currency or Number), and use the `note` text as a caption below.
- A **Stacked bar chart** from `naive_vs_caused`: dimension `group`, breakdown `component`, metric
  `conversion_rate` (Sum). Colour "Caused by the ad" `#BF616A` and the other parts `#CED6E2`.

**Page 2, Lift**
- A **Bar chart** from `lift_estimates`: dimension `estimate`, breakdown `outcome`, metric `lift` (Sum).
- A **Table** from `lift_estimates` with `outcome`, `estimate`, `lift`, `lo`, `hi`.
- Text box: "The raw comparison is inflated by a small leak in the test; the adjusted figures are the headline."

**Page 3, Targeting**
- Two **Drop-down list** controls: `outcome` and `x_axis` (default "Share of ad spend used").
- A **Line chart** from `targeting_curves`: dimension `x`, breakdown `ranking`, metric `share_of_effect` (Average).
- Text box: "Half the spend, aimed at likely buyers, keeps 84% of the conversions ads cause."

**Page 4, Money**
- Text box at the top: "Illustrative: assumes a dashboard ROAS and margin; the data has no prices or costs."
- Two **Pivot tables with heatmap** from `money_sensitivity`: rows `dashboard_roas`, columns `margin`; metric
  `profit_per_pound_all_spend` in one, `profit_per_pound_other_half` in the other (Average). Heatmap red for
  negative, blue for positive.
- A **Table** from `break_even`: `margin`, `spend`, `break_even_dashboard_roas`.

**Page 5, Measurement**
- A **Drop-down list** control on `method`.
- A **Pivot table with heatmap** from `geo_designs`: rows `test_counties`, columns `test_weeks`, metric
  `min_detectable_lift` (Average).
- A **Bar chart** from `geo_designs`: dimension `method`, metric `false_alarm_rate` (Average), with a reference
  line at 5%.
- A **Line chart** from `holdout_sizing` with a drop-down on `outcome`: dimension `users`, breakdown
  `holdout_share`, metric `min_detectable_lift` (Average).
- Text box: "Geo tests on this data: real Iowa sales, simulated campaigns."

### 4. Screenshots and sharing

1. For each page, take a screenshot and save it into `dashboard/screenshots/` as `1_overview.png`, `2_lift.png`,
   `3_targeting.png`, `4_money.png`, `5_measurement.png`.
2. Sharing is your choice: **Share > Manage access > Anyone with the link can view** makes it public. Paste the
   link at the top of this file once you've decided.
