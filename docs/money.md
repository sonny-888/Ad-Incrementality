# Finding 7: Is it worth the money?

Numbers come from `results/money.json` (`python/scripts/money_analysis.py`). Chart: `figures/money/profit_per_pound.png`.

## What comes from the test, and what is assumed

The data has visits and conversions but **no prices or costs**, so money figures need two inputs:

| Input | Value used | Where it comes from |
|---|---|---|
| Caused share: of conversions credited to ads, the share the ads caused | 54% (50 to 58) | The test (finding 5) |
| Share of caused conversions brought by the best half of spend | 84% (78 to 90) | The test (finding 6, ranking by likely buyers, spend measured as ad views) |
| Dashboard ROAS: revenue credited to ads per £1 of spend | **8, illustrative** | Assumed. Read yours off your dashboard |
| Margin: profit kept from each £1 of revenue | **30%, illustrative** | Assumed. Use your own |

Uncertainty from the test is carried through every money figure by simulation (200,000 draws). The assumptions are
varied in the sensitivity tables below.

## The three formulas

- **Real (incremental) ROAS** = dashboard ROAS x caused share. At 8 x 0.54, that is 4.3, not 8.
- **Profit per £1 of spend** = real ROAS x margin - 1.
- **Break-even dashboard ROAS** = 1 / (margin x caused share). Below this, the ads lose money.

## Result at the illustrative assumptions (ROAS 8, margin 30%)

| Profit per £1 of ad spend | Estimate (95% interval) |
|---|---|
| What the dashboard implies | +£1.40 |
| **Real, all spend** | **+£0.29** (+£0.19 to +£0.38) |
| Real, best half of spend | +£1.16 (+£0.94 to +£1.39) |
| **Real, other half of spend** | **-£0.58** (-£0.74 to -£0.42) |

- The dashboard overstates profit nearly fivefold, because it credits the ads with conversions that would have
  happened anyway.
- The campaign does make money overall, but only because the best half of spend carries the other half, which
  **loses about 58p of every £1**.
- **Cutting the other half** halves spend, gives up about 16% of the conversions the ads cause, and roughly
  **doubles profit** (x2.0, 1.6 to 2.7).

## Break-even dashboard ROAS (no ROAS assumption needed)

The lowest dashboard ROAS at which the ads pay for themselves, by margin:

| Margin | All spend | Best half of spend | Other half of spend |
|---|---|---|---|
| 20% | 9.3 (8.7 to 10.0) | 5.6 (5.0 to 6.2) | 28.7 (20.7 to 46.6) |
| 30% | 6.2 (5.8 to 6.7) | 3.7 (3.4 to 4.1) | 19.2 (13.8 to 31.1) |
| 40% | 4.7 (4.3 to 5.0) | 2.8 (2.5 to 3.1) | 14.4 (10.3 to 23.3) |
| 50% | 3.7 (3.5 to 4.0) | 2.2 (2.0 to 2.5) | 11.5 (8.3 to 18.7) |

**Rule of thumb from this test:** with a 30% margin, a retargeting campaign needs a dashboard ROAS above about 6 to
break even, and the weaker half of its spend needs about 19, which few campaigns reach.

## Sensitivity: real profit per £1

**All spend** (losses in bold):

| Dashboard ROAS | 20% margin | 30% margin | 40% margin | 50% margin |
|---|---|---|---|---|
| 4 | **-£0.57** | **-£0.36** | **-£0.14** | +£0.07 |
| 6 | **-£0.36** | **-£0.03** | +£0.29 | +£0.61 |
| 8 | **-£0.14** | +£0.29 | +£0.72 | +£1.15 |
| 10 | +£0.07 | +£0.61 | +£1.15 | +£1.68 |
| 12 | +£0.29 | +£0.93 | +£1.58 | +£2.22 |
| 15 | +£0.61 | +£1.41 | +£2.22 | +£3.02 |

**Other half of spend** (losses in bold):

| Dashboard ROAS | 20% margin | 30% margin | 40% margin | 50% margin |
|---|---|---|---|---|
| 4 | **-£0.86** | **-£0.79** | **-£0.72** | **-£0.65** |
| 6 | **-£0.79** | **-£0.69** | **-£0.58** | **-£0.48** |
| 8 | **-£0.72** | **-£0.58** | **-£0.44** | **-£0.30** |
| 10 | **-£0.65** | **-£0.48** | **-£0.30** | **-£0.13** |
| 12 | **-£0.58** | **-£0.37** | **-£0.17** | +£0.04 |
| 15 | **-£0.48** | **-£0.22** | +£0.04 | +£0.30 |

The weaker half of spend loses money in 21 of the 24 combinations. Even where it doesn't, each pound there causes
about a fifth as many conversions as a pound in the best half (0.32 vs 1.68 times the average), so moving budget
towards the best half pays under every assumption shown; only whether to cut outright depends on the numbers.

## Limits

- **Assumptions, not facts.** Dashboard ROAS and margin are illustrative; the tables show how answers move with them.
- **Spend is proxied by ad views.** Real cost also depends on how many ads each user sees and their price.
- **Benchmark caused share.** Criteo sub-sampled the file to hide its real incrementality. A real campaign must use
  its own holdout test's caused share; the method carries over unchanged.
- **Halving spend is a test, not a switch.** The 84% figure comes from ranking users in this test. Before cutting
  spend, run it as a holdout test of its own (finding 9 sets out how).

## Plain-English glossary

- **ROAS (return on ad spend):** revenue per £1 of ad spend. Dashboards report the attributed kind.
- **Incremental ROAS:** revenue the ads actually *caused* per £1 of spend.
- **Margin:** share of each £1 of revenue kept as profit after the cost of goods.
- **Break-even:** the point where profit from the ads exactly covers what they cost.
