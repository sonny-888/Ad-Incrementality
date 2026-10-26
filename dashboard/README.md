# Dashboard (Power BI)

Three pages in the Nordic style, generated entirely from code by [`build_pbip.py`](build_pbip.py): every table, DAX
measure, page and visual is defined there, validated against Microsoft's report schemas, and every number in a title
or note is read from `results/headline_facts.json`, so the dashboard can't drift from the README, report and deck.

| 📊 [Dashboard (PDF)](AdIncrementality.pdf) | ⬇️ [Power BI file (.pbix)](AdIncrementality.pbix) | 🧮 [All DAX measures](measures.dax) |
|---|---|---|

![Overview page](screenshots/1_overview.png)

![Targeting & money page](screenshots/2_targeting_money.png)

![How to measure page](screenshots/3_how_to_measure.png)

## Pages

| Page | Question | What's on it |
|---|---|---|
| **Overview** | Did the ads actually work? | KPI cards (54 caused per 100 credited, 41x vs 2.2x, adjusted lift); dashboard view vs real effect; raw vs corrected lift; credited vs caused |
| **Targeting & money** | Who to target, and does it pay? | Share of the effect captured by share of spend for three rankings; profit per £1 by dashboard ROAS and margin, for all spend and the weaker half; break-even ROAS |
| **How to measure** | How to measure it next time? | False alarms by geo method; smallest detectable lift by geo design; users a holdout needs to detect a +5%, +10% or +20% conversion lift |

Each page has the slate sidebar with page buttons, a one-line finding under the title, four KPI cards with a thin
colour bar, and a decision strip (finding, evidence, interpretation, next action). Red marks the one thing to look at;
blue carries the data. Money figures are labelled illustrative; geo results are labelled "real sales, simulated
campaigns".

## Data

The model reads eight small CSVs in [`data/`](data/), written by `python/scripts/export_dashboard_data.py` from
`results/`. They hold aggregated results only; no user-level data.

| Table | Rows | Feeds |
|---|---|---|
| `kpis` | 15 | KPI cards (one measure per headline number) |
| `naive_vs_caused` | 3 | Dashboard view vs real effect |
| `lift_estimates` | 6 | Raw vs corrected lift |
| `targeting_curves` | 1,414 | Effect captured by share of users or spend |
| `money_sensitivity` | 24 | Profit per £1 by dashboard ROAS and margin |
| `break_even` | 12 | Break-even dashboard ROAS |
| `geo_designs` | 27 | Geo methods: false alarms and smallest detectable lift |
| `holdout_users` | 18 | Users needed to detect a given lift, by share held out |

## Open or rebuild it

- **Just look:** open [`AdIncrementality.pdf`](AdIncrementality.pdf), or download [`AdIncrementality.pbix`](AdIncrementality.pbix)
  and open it in Power BI Desktop (the data is inside).
- **Rebuild from code:** `python dashboard/build_pbip.py --validate`, then open `dashboard/AdIncrementality.pbip` in
  Power BI Desktop and click **Home > Refresh**. If your copy of the project lives elsewhere, set the `DataFolder`
  parameter (**Transform data > Edit parameters**) to your `dashboard/data/` folder.
