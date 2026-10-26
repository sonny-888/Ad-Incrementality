# Finding 5: Credited vs caused

**In this benchmark, an estimated 54 of every 100 conversions credited by view-through attribution were caused by
the ads** (95% interval 50 to 58). The other 46 would have happened without the ad. Chart:
`figures/attribution/credited_vs_caused.png`, made by `python/scripts/fig_attribution.py` from
`results/lift_aipw.json`.

## The assumptions behind the 54

1. **Random assignment, apart from the small leak in finding 1**, and the leak runs through the recorded features
   f0 to f11, so adjusting for them removes it.
2. **Showing nothing to the control group changes nothing else** (the exclusion restriction): being in the treated
   group affects buying only through seeing an ad.
3. **The control group saw no ads from this campaign** (one-sided noncompliance), which holds by design.
4. **Credit means view-through credit**: every conversion by a user who saw an ad. Other rules credit less.

If assumption 1 is wrong in a way the features don't capture, the 54 moves. The sensitivity check in
`docs/lift.md` shows how far it moves across the adjustment methods we tried.

## How the two numbers are defined

- **Credited:** every conversion by a user who saw an ad. This is how view-based (view-through) attribution hands out
  credit: the user saw an ad, then bought, so the ad gets the sale. The dataset has ad views, not clicks, so this is the attribution
  rule we can reproduce. A click-based rule would credit fewer conversions, and the overstatement would be smaller.
- **Caused:** the effect of seeing an ad from finding 4 (doubly robust, +2.89 points), divided by the conversion rate
  of the users who saw one (5.38%). That gives 54%.

## What it means

- An attribution report built on ad views overstates the conversions the ads drove by about **1.9x** (100 / 54).
  Return on ad spend computed from it is overstated by the same factor.
- Ads still work: seeing one roughly doubles a user's chance of buying (finding 4). The problem is not that ads do
  nothing; it's that attribution also hands them the sales of keen shoppers who were going to buy anyway.
- For visits the split is similar: **51 of every 100** visits after an ad view were caused by it.

## How much the correction matters

| | Caused per 100 credited conversions | 95% interval |
|---|---|---|
| Raw, without correcting the leak from finding 1 | 59 | 56 to 63 |
| **Corrected (doubly robust), headline** | **54** | **50 to 58** |
| Range across 7 adjusted specifications (`docs/lift.md`) | 51 to 58 | |

The spread across adjustment methods is about as wide as the statistical interval, and every method lands below the
raw 59.

## Limits

- **Benchmark, not live results.** Criteo sub-sampled the file so its real incrementality can't be recovered. The
  share applies to this file; real campaigns will differ, which is exactly why they need their own holdout tests.
- **Interval.** The 95% interval comes from the uncertainty in the ad's effect. It treats the exposed users'
  conversion rate (428,000 users) as known, which adds very little error.
- **One attribution rule.** Real attribution reports mix rules (last click, data-driven, view-through windows). The
  method is the same for any rule: compare what it credits with what a holdout test shows was caused.
