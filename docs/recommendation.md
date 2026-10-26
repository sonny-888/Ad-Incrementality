# Finding 9: Recommendation. A test-and-learn measurement plan

Sizing numbers come from `results/plan.json` (`python/scripts/plan_analysis.py`) and `results/budget_test.json`
(`python/scripts/budget_test_plan.py`). Chart: `figures/plan/holdout_sizing.png`. Everything else draws on findings
1 to 8.

## The three decisions this project informs

| Decision | Answer from this project | Confidence |
|---|---|---|
| **Should we trust attribution?** | No, not on its own. In this benchmark an estimated 54 of every 100 view-through-credited conversions were caused by the ads, so attributed ROAS overstates incremental ROAS by about 1.9x | Randomised test; holds across the adjustment methods we tried |
| **Should we move budget?** | Probably, but test first. In the scenario (ROAS 8, margin 30%) the weaker half of spend loses about 58p per £1 | A model-based hypothesis; production effects can change it |
| **Which experiment next?** | A 50/50 holdout inside the weaker-half segment, then an always-on 10% holdout | Sized below from the test's own rates |

## What we found, in one page

| # | Finding | Number |
|---|---|---|
| 1 | The test was sound, with a small leftover imbalance from merging several advertisers' tests | Classifier AUC 0.509 (placebo 0.499) |
| 2 | The dashboard view (saw an ad vs didn't) is wildly inflated | Looks like 41x; those users were already 19x likelier to buy |
| 3 | Estimated lift for the whole treated group, adjusted for the imbalance | Conversions +52%, visits +20% (raw: +59%, +27%) |
| 4 | Estimated causal effect of seeing an ad (CACE) | Conversion rate 2.49% to 5.38%: 2.2x, not 41x |
| 5 | Credited vs caused | An estimated **54 of every 100** view-through-credited conversions were caused by ads (50 to 58) |
| 6 | Who is persuaded | Top 20% of users hold 91% of the effect; a simple likely-buyer model finds them as well as uplift models |
| 7 | Worth the money (scenario: ROAS 8, margin 30%) | Each £1 looks like +£1.40 but makes an incremental +£0.29; the weaker half of spend loses about 58p per £1 |
| 8 | Measuring by region (methods benchmark: real sales, simulated campaigns) | Two simple methods stay honest; even 20 counties for 12 weeks only detect about a 9% lift |
| 9 | Sizing a holdout | Seeing a 10% conversion lift with a 10% holdout takes about 4.9 million users |

## Recommendations

### 1. Judge retargeting on what it causes, not what it is credited with

Incremental ROAS = dashboard ROAS x caused share. In this benchmark the estimated caused share was 54%, so
dashboards overstate retargeting's return by about 1.9x. **With a 30% margin, a campaign would need a dashboard ROAS
above about 6 to break even** (finding 7). Report incremental ROAS next to attributed ROAS in every campaign review.

### 2. Keep an always-on holdout

Hold a random share of users out of retargeting permanently and read the lift regularly. It keeps the caused share
current instead of relying on a one-off test.

- **Size it with the calculator** (`python/incrementality/planning.py`). With conversions as rare as in this test
  (0.19% without ads):

  | To detect a conversion lift of | 10% held out | 15% held out | Even 50/50 split |
  |---|---|---|---|
  | 20% | 1.4M users | 1.0M users | 0.5M users |
  | 10% | 4.9M users | 3.5M users | 1.8M users |
  | 5% | 18.9M users | 13.3M users | 6.8M users |

- **Use visits as the early read.** They are 20 times more common, so a 5% visit lift shows with about 0.9M users at
  a 10% holdout. Confirm on conversions over a longer window.
- **The trade-off:** a bigger holdout gives faster, sharper answers but forgoes more sales while it runs (held-out
  users don't see ads, so you give up that share of the conversions the ads cause). A 10% to 15% always-on holdout is
  a sensible default for a large advertiser; a smaller one may need a 50/50 split for a short burst instead.
- The formula was checked against the Criteo test itself: it predicted +/- 0.9 and +/- 5.4 points for visits and
  conversions; the test achieved +/- 0.9 and +/- 5.2.

### 3. Test the budget cut before making it

Finding 7 suggests the weaker half of spend loses money, but that comes from scoring users in a past test. Changing
targeting can move auction prices, ad frequency and who is in the audience (finding 7 lists these), so the cut needs
its own test:

| | Proposal |
|---|---|
| Segment | Users ranked lowest by the likely-buyer model, up to half of today's ad views: about 89% of users |
| Design | Split the segment 50/50 into "keep ads" and "no ads"; leave the best half unchanged |
| Primary metric | Relative conversion lift in the segment (no ads as baseline); visits as the early read |
| Prediction | +55% (95% interval +33% to +76%) |
| Break-even | The segment's spend pays for itself only at a lift of about +131% (scenario: ROAS 8, margin 30%) |
| Decision rule | Cut the segment's spend if the one-sided 95% upper bound on lift is below break-even; otherwise keep it and re-rank |
| Size | About 0.4 million users in the segment gives an 80% chance of reaching "cut" if the prediction is right |
| Guardrails | Total conversions, cost per ad view and ads per user in the best half, so price and frequency shifts show up |

Holding out a weak segment costs little: the model expects it to bring about 16% of the conversions the ads cause.
This turns a model's suggestion into a measured result.

### 4. Target with the simple model first

A plain likely-buyer model matched the uplift models on conversions and is easier to build, explain and maintain
(finding 6). Revisit uplift modelling when there are more conversions to learn from, or for visit-focused campaigns
on tight budgets, where it did beat the simple model (top 10% of users: 80% vs 68% of the effect).

### 5. Check the experiment's health before reading it

Run the sample-ratio, balance and classifier checks (finding 1) on every test. Our test looked balanced, but the
classifier and a placebo exposed a small leak that inflated the raw visit lift from 20% to 27%. When features are
recorded before treatment, adjust for them (finding 3) and report raw and adjusted side by side.

### 6. Where a holdout is impossible, run geo tests carefully

TV, radio, outdoor and some ad platforms can't hold out individual users. Then:

- Use **difference-in-differences or synthetic control**. Both kept false alarms near 5% (finding 8).
- **Placebo-test any model-based method first.** The CausalImpact-style model raised 2 to 3.5 times too many false
  alarms on real sales.
- **Size the test by simulation on your own regional history** (`python/scripts/geo_simulation.py`). On weekly Iowa
  liquor sales, even 20 counties for 12 weeks only reliably detected a lift of about 9%. If the campaign can't
  plausibly move sales that much, a geo test won't settle the question.
- More regions help faster than more weeks; smoother outcomes (fortnightly rather than weekly) help too.

### 7. Use a marketing mix model for cross-channel budgets, anchored by experiments

A marketing mix model (MMM) spreads budget across channels using history, but on its own it shows correlation, not
cause. Project 1 built one (with Robyn) and noted exactly this limit: it could not be calibrated because there were
no experiment results. This project supplies the missing piece. **Use the holdout and geo results as anchors**: where
an experiment has measured a channel's effect, the MMM should agree with it; where it doesn't, trust the experiment
and recalibrate the model.

## Which method for which question

| Question | Best method | Why | Watch out for |
|---|---|---|---|
| Is this digital campaign working? | User-level holdout | Most precise; cause is clear | Holdout too small for rare conversions |
| Who should we target? | Likely-buyer or uplift model, checked by holdout | Effect is concentrated | Grade by spend, not head count |
| Is a channel with no user-level control working? | Geo test (DiD or synthetic control) | Works for TV, outdoor, walled gardens | Detects only large effects on noisy data |
| How should we split budget across channels? | MMM calibrated with experiments | Covers every channel at once | Correlation unless anchored by tests |
| Should we cut part of the budget? | Holdout on that part | Measures what the cut costs | Needs enough users in that part |

## A first quarter

| When | Action | Readout |
|---|---|---|
| Month 1 | Launch a 10% always-on retargeting holdout; add incremental ROAS to dashboards | Visits after about 2 weeks |
| Month 2 | Start the "cut test" on the weaker half of spend | Conversions after enough users |
| Month 2 | Simulate a geo test for one upper-funnel channel on its regional history | Go or no-go on the design |
| Month 3 | First conversion readout from the holdout; decide the budget cut | Caused share and break-even check |
| Each half-year | Refresh the MMM, calibrated with every experiment result so far | Budget split across channels |

## Before trusting any ad number: five questions

1. Is it **attributed** (credited) or **incremental** (caused)? Only a holdout or geo test gives the second.
2. Was the comparison **randomised**, and did the health checks pass?
3. **How big was the test**, and could it have seen an effect of the size claimed?
4. What is the **95% interval**, not just the point estimate?
5. Has the method been **placebo-tested** on periods with no campaign?

## Limits

- **Benchmark data.** Criteo sub-sampled its file to hide real incrementality; the numbers here describe that file.
  The methods transfer; each business must measure its own caused share.
- **Money assumptions.** ROAS and margin in finding 7 are illustrative; the break-even rule and sensitivity tables
  show how conclusions move.
- **One geo dataset.** Liquor wholesale orders are lumpy; smoother sales give smaller detectable lifts.
- **Sizing assumes** a stable base rate and simple random assignment; feature adjustment can help (it made the visit
  estimate as precise as having 32% more users) but did not help for rare conversions here.
