# Finding 8: Measuring a campaign by region (geo tests)

**Technical appendix: a methods benchmark on real sales with simulated campaigns.** No real campaign is measured
here. The question is which geo methods give honest answers on noisy regional data, and how big a campaign must be
before any of them can see it. Numbers come from `results/geo.json`
(`python/scripts/geo_simulation.py`). Charts: `figures/geo/example_test.png`, `figures/geo/min_detectable_lift.png`,
`figures/geo/false_alarms.png`.

## The question

Findings 1 to 7 used a user-level holdout: random users never shown ads. Often that isn't possible (TV, radio,
billboards, or platforms that won't hold users out). The fallback is a **geo test**: run the campaign in some
regions, not in others, and compare. How well does that work, and which method should read it?

In a real geo test you never know the true answer, so you can't grade the method. Here we can: we take real sales,
add a campaign we invent (so we know its true size), and see which methods find it.

## Data

- **Iowa Liquor Sales** (BigQuery public data): every wholesale liquor order in Iowa. Pulled with
  `sql/iowa_county_week.sql` into weekly sales per county, January 2016 to April 2026 (537 full weeks).
- **96 of Iowa's 99 counties.** Fremont, Davis and Adams were left out: they had no orders in 9% to 31% of weeks.
  Elsewhere, 0.85% of county-weeks had no orders (mostly holiday weeks: Labor Day, Memorial Day, Thanksgiving) and
  were filled from neighbouring weeks.
- **It is noisy.** A typical county's sales move about 50% from one week to the next, because stores order in lumps.

## How the simulation works

1. Pick test counties at random (5, 10 or 20) and a random start week, with 104 weeks of history before it.
   No test window overlaps March to June 2020.
2. Run three methods on that "campaign" when **nothing was actually done**:
   - **Difference-in-differences:** each county's change from before to during; test counties' average change minus
     the others'. One number per county, so week-to-week correlation can't fake precision (Bertrand, Duflo and
     Mullainathan 2004).
   - **Synthetic control:** a weighted mix of other counties that tracked the test counties beforehand. The gap during
     the campaign is the effect; its interval comes from 40 placebo runs on fake test groups.
   - **CausalImpact-style time series:** the idea behind Google's CausalImpact (a model that forecasts the test
     counties from similar counties), built in Python with statsmodels.
3. Repeat 300 times for each of 9 designs (counties x test length of 4, 8 or 12 weeks): 2,700 simulated tests.
4. A significant result with no campaign is a **false alarm**. Because every method learns only from the weeks before
   the campaign, adding a +L% campaign moves its estimate by exactly L% (proved in `python/tests/test_geo.py`), so the
   same runs tell us whether each design would catch a +2%, +5%, +10% campaign and so on.

**What the simulated campaign assumes** (`inject_lift` in `python/incrementality/geo.py`):

- **Uniform multiplicative lift:** every test county's sales rise by the same +L% in every campaign week (added as
  log(1 + L) to log sales). No ramp-up, no carryover after the campaign ends.
- **Random test counties:** chosen uniformly at random, not matched or stratified.
- **No spillover:** control counties are untouched, so there is no leakage across county lines.
- **Fixed history:** 104 weeks of pre-period for every test, with March to June 2020 excluded.

Real campaigns break each of these, so the detectable lifts here are a best case for this data.

## Results

### 1. Two simple methods are trustworthy; the CausalImpact-style model is not

| Method | False alarms across the 9 designs (promised: 5%) |
|---|---|
| Difference-in-differences | 3% to 8% |
| Synthetic control | 4% to 7% |
| **CausalImpact-style time series** | **10% to 18%** |

The CausalImpact-style model raises 2 to 3.5 times too many false alarms: its intervals are too narrow for real,
lumpy sales. It was also the least accurate (typical error 5% to 10%, against 3% to 9% for the other two) and leaned
slightly positive (+0.3% to +1.2%). Our version leaves out one source of uncertainty that Google's package includes
(uncertainty in the model's own settings), so the real package may do somewhat better; the lesson stands either way:
**check a method's intervals with placebo tests before trusting them.**

### 2. Geo tests on this data only catch big effects

The smallest lift detected 80% of the time, with every method held to an honest 5% false-alarm rate:

**Difference-in-differences**

| Test counties | 4 weeks | 8 weeks | 12 weeks |
|---|---|---|---|
| 5 | 23% | 19% | 16% |
| 10 | 20% | 13% | 13% |
| 20 | 12% | 10% | **9%** |

**Synthetic control**

| Test counties | 4 weeks | 8 weeks | 12 weeks |
|---|---|---|---|
| 5 | 26% | 20% | 18% |
| 10 | 20% | 12% | 12% |
| 20 | 15% | 12% | **9%** |

(CausalImpact-style: 14% at best, 28% at worst.)

Even the largest design, **20 counties for 12 weeks, only reliably detects a lift of about 9%**. Most ad campaigns move
sales by a few percent, so on data this noisy a geo test of this size would usually come back "not significant" even
when the campaign worked. More counties and longer tests both help; more counties helps faster.

### 3. For scale: the user-level test

Not a like-for-like comparison (different business, different outcome), but it shows why scale matters. The best geo
design here reads a lift to within about +/- 6 percentage points (median 95% interval, 20 counties for 12 weeks). The
Criteo holdout, with millions of users, pinned the visit lift to within +/- 0.7 points (+20%, finding 3). Rare
outcomes are harder even with millions of users: its conversion lift came with +/- 4 points. **Where a user-level
holdout is possible, it can see much smaller effects; geo tests are the fallback when it isn't.**

## What to recommend (feeds finding 9)

- Use **difference-in-differences or synthetic control**; both stayed honest. Prefer synthetic control when test and
  control regions differ a lot in size or trend, since it builds a closer match.
- **Size the test before running it.** Run this kind of simulation on your own regional history to find the smallest
  lift your design can detect. If the campaign can't plausibly move sales that much, a geo test won't settle it.
- **Use many regions** and the least noisy outcome you have (for example, fortnightly instead of weekly sales).
- **Placebo-test any model** (especially forecast-based ones like CausalImpact) on periods with no campaign before
  trusting its intervals.

## Limits

- **Simulated campaign.** The lift is added evenly to every test county for every test week. Real campaigns ramp up,
  spill over into neighbouring regions and differ by region.
- **One dataset.** Liquor wholesale orders are lumpier than many retail series; smoother data would give smaller
  detectable lifts. The method carries over; the numbers would change.
- **Random test counties.** Choosing test and control counties to match each other (stratified designs) usually
  improves precision; we used random selection as the baseline.

## Plain-English glossary

- **Geo test:** an experiment where regions, not people, are split into test and control.
- **Placebo run:** pretend a campaign happened where none did, to see what "no effect" looks like.
- **False alarm:** a test saying "significant" when there was no effect. A 95% interval promises this 5% of the time.
- **Minimum detectable lift:** the smallest real effect a test design catches 80% of the time.
- **Size-adjusted:** each method's detection threshold set so it raises exactly 5% false alarms, so power is compared
  fairly.
