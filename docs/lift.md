# Findings 2 to 4: How much did the ads actually do?

Numbers come from `results/lift.json` (`python/scripts/lift_analysis.py`) and `results/lift_aipw.json`
(`python/scripts/lift_aipw.py`). Charts: `figures/lift/naive_vs_caused.png`, `figures/lift/raw_vs_adjusted.png`.

**Read every absolute number as "in this benchmark file".** Criteo sub-sampled the data so its real incrementality
can't be recovered. Comparisons between methods hold; the levels describe this file, not Criteo's live campaigns.

## Finding 2: the naive view is wildly inflated

A dashboard compares users who saw an ad with users who didn't:

| | Saw an ad | Didn't see an ad | Looks like |
|---|---|---|---|
| Visit rate | 41.5% | 3.5% | 11.7x |
| Conversion rate | 5.38% | 0.13% | **41x** |

This is not the ad's effect. Users who get shown ads are not a random slice: they tend to be active, interested
shoppers, which is exactly who ad systems bid on. The test shows those users would have converted at about **2.49% with no ad at all**, already
19 times the rate of everyone else. Most of the 41x is who they are, not what the ad did.

## Finding 3: the estimated lift for the whole treatment group (intent-to-treat)

Compare the randomly assigned groups as a whole, whether or not each person saw an ad.

| | Raw difference | Adjusted, linear | **Adjusted, doubly robust (preferred)** |
|---|---|---|---|
| Visits | +1.03 points (+27%) | +0.77 points (+20%) | **+0.75 points (+20%)**, 95% interval 0.72 to 0.77 |
| Conversions | +0.115 points (+59%) | +0.100 points (+52%) | **+0.102 points (+52%)**, 95% interval 0.094 to 0.109 |

**Why three columns.** Finding 1 found a small leak: the features predict the group very slightly, a leftover from
merging several advertisers' tests. On its own the leak looks harmless (no feature differs by more than 0.05
standard deviations), but the features also strongly predict who visits, so the small imbalance pushes the raw
difference up. The raw and adjusted estimates differ by far more than chance allows.

The features were logged when users were assigned, before any ad (Diemert et al. 2021), so adjusting for them cannot
pick up any effect of the ads themselves. We prefer the adjusted estimates, on the assumption that the leak runs through
these recorded features. Two different adjustments agree:

- **Linear (Lin 2013):** a regression of the outcome on the group and the features.
- **Doubly robust (AIPW):** gradient-boosted models of both who ends up treated and who converts, fitted on one half
  of the data and scored on the other (cross-fitting). It is right if either model is right, and lets the leak be
  non-linear. The estimated chance of being treated stays between 0.845 and 0.895 for 98% of users, so every kind
  of user appears in both groups.

Without the adjustment, the raw numbers would overstate visit lift by about a third (27% vs 20%) and conversion lift
by about an eighth (59% vs 52%).

### Sensitivity: how much does the correction depend on the method?

`python/scripts/sensitivity_analysis.py` (about 20 minutes) re-estimates the lift seven ways: the linear adjustment,
and with two model families (gradient boosting and logistic regression) the doubly robust estimate, weighting only
(IPW) and the outcome model only. Results: `results/sensitivity.json`; chart: `figures/lift/sensitivity.png`.

| Specification | Visits | Conversions |
|---|---|---|
| Raw difference | +27% | +59% |
| Linear (Lin) | +20% | +52% |
| Doubly robust, gradient boosting (preferred) | +20% | +52% |
| Weighting only, gradient boosting | +20% | +51% |
| Outcome model only, gradient boosting | +19% | +56% |
| Doubly robust, logistic regression | +19% | +50% |
| Weighting only, logistic regression | +20% | +51% |
| Outcome model only, logistic regression | +19% | +50% |
| **Adjusted range** | **+19% to +20%** | **+50% to +56%** |

- **Every adjusted estimate sits below the raw one**, for both outcomes and both model families.
- **The weights balance the features.** Weighting each user by the fitted chance of being treated shrinks the largest
  feature gap from 0.049 to 0.002 standard deviations (boosting) and 0.001 (logistic). So both propensity models
  capture the leak that the features carry.
- **The spread is about the size of the statistical interval.** Scaled to caused conversions, the adjusted
  specifications give 51 to 58 per 100 credited, against the headline's 95% interval of 50 to 58.
- **What it can't rule out:** a leak through something the file doesn't record. No adjustment can see that; only a
  cleaner test could.

## Finding 4: the effect of actually seeing an ad

Only 3.60% of the treatment group (3.52% after adjustment) saw an ad, so the whole-group lift is spread thin. Dividing by that
share gives the effect on the people who saw one (an instrumental-variables estimate: random assignment is the
lever that shifts who sees an ad, and nobody in control can see one).

| | Rate with the ad | Rate without the ad (estimated) | Effect | Looks like (naive) | Estimated causal multiple |
|---|---|---|---|---|---|
| Visits | 41.5% | 20.3% | **+21.2 points** (20.5 to 21.9) | 11.7x | **2.0x** |
| Conversions | 5.38% | 2.49% | **+2.89 points** (2.68 to 3.10) | 41x | **2.2x** |

So seeing an ad roughly doubles a user's chance of visiting and of buying: a big effect, but far smaller than the
dashboard view suggests (for conversions, 2.2x against 41x).

The raw (unadjusted) versions are +28.7 points for visits and +3.20 points for conversions; both checks (my own
formula and linearmodels' two-stage least squares) give the same raw numbers to five decimal places.

**The assumption behind it.** Being assigned to the treatment group changes behaviour only through seeing an ad.
That is reasonable here: a user can't notice being in the treatment group unless an ad appears.

## Leads into finding 5

Among users who saw an ad, **an estimated 54 of every 100 conversions were caused by it** (95% interval 50 to 58); the
other 46 would have happened anyway. See `docs/attribution_vs_incrementality.md`.

## Plain-English glossary

- **Intent-to-treat (ITT):** treatment group minus control group, as assigned. Honest, but diluted when few people
  actually see an ad.
- **Instrumental variable:** something random (the group) that changes who gets the treatment (an ad view). It lets us
  scale the ITT up to the effect on people actually treated.
- **Doubly robust / AIPW:** an estimate that combines a model of who gets treated with a model of the outcome, and
  stays correct if either one is right.
- **Cross-fitting:** fit the models on one half of the users and score the other half, then swap, so models never
  grade their own homework.
