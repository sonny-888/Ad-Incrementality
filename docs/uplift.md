# Finding 6: Who is persuaded?

Numbers come from `results/uplift.json` (`python/scripts/uplift_analysis.py`). Chart: `figures/uplift/uplift_curves.png`.

## The question

Findings 3 to 5 measured the ads' *average* effect. But the effect is not the same for everyone. Think of four kinds
of user:

| | Buys without an ad | Doesn't buy without an ad |
|---|---|---|
| **Buys with an ad** | *Sure things*: an ad is wasted money | ***Persuadables*: the only people an ad helps** |
| **Doesn't buy with an ad** | *Do-not-disturbs*: an ad puts them off | *Lost causes*: an ad is wasted money |

Retargeting usually aims at the people most likely to buy. Many of those are sure things. The money is better spent on
persuadables. An **uplift model** tries to find them.

## How

1. **Split the users at random:** 80% (11.2 million) to train models, 20% (2.8 million) held back to grade them.
   Models never see the users they are graded on.
2. **Train three ways of ranking users**, separately for visits and for conversions:
   - **T-learner:** one model predicts the outcome for treated users, another for control users. A user's uplift is
     the difference between the two predictions.
   - **X-learner:** starts from the T-learner, works out each training user's own estimated effect, and fits a second
     pair of models to those. It tends to do better when one group is much smaller, as control is here (15%).
   - **Response model ("likely buyers"):** the treated-user model on its own. This is what retargeting normally
     optimises, and it is the comparison that matters.
3. **Grade on the held-out users.** Rank them by each model's score and ask: if we target the top 10%, 20%, 30% and
   so on, what share of the ads' total effect do we capture? Random targeting captures 20% of the effect with 20% of
   users; a useful model captures more.
4. **Correct for the leak.** Grading uses the same doubly robust correction as finding 3, so the small imbalance from
   finding 1 can't flatter or penalise a model.
5. **Fix the headline cut-off in advance.** The headline compares models at the top 20%, chosen before the results
   were seen, so the cut-off can't be picked to look good.

## Results

### 1. The effect is concentrated in a fifth of users (headline, cut-off set in advance)

| Top 20% of users, ranked by | Share of the visit effect | Share of the conversion effect |
|---|---|---|
| Uplift model (X-learner) | **91%** (87 to 94) | **91%** (83 to 98) |
| Likely buyers (response model) | 89% (87 to 92) | 91% (86 to 96) |
| Random | 20% | 20% |

The top fifth's average visit lift is +3.4 points; the other 80% average +0.09 points, close to nothing. Chart:
`figures/uplift/uplift_curves.png`.

**The uplift model and the simple likely-buyer model tie at 20%** (difference +1 point for visits, -2 to +4; 0 for
conversions, -8 to +8). They largely pick the same people: 77% of the top fifth overlaps for visits, 75% for
conversions. That makes sense here: only users who see an ad can be persuaded, and ad systems show ads to active,
keen users, so persuadable users and likely buyers are mostly the same crowd.

The uplift model only wins clearly on a **tight budget, for visits**: the top 10% of users hold 80% of the visit
effect when ranked by uplift, against 68% for likely buyers (+12 points, 7 to 16). For conversions there is no
measurable difference at any cut-off; with about 800 control-group conversions in the test set, the signal is too
weak. Criteo's paper warns about exactly this.

The X-learner beat the T-learner on both outcomes, by a wide margin on conversions. That is what theory predicts when
the control group is small (15% here).

### 2. Measured by spend, half the budget keeps most of the effect

Advertisers pay when an ad is shown, so the fairer yardstick is spend, not head count. A fifth of users hold 91% of
the effect, but they also receive 64% to 81% of the ad views (depending on the model and outcome): the ad system
already aims most of its spend at them.
So "drop 80% of users" would save far less than 80% of the money.

Targeting users best first until a given share of today's spend (ad views) is used:

| Share of spend | Visit effect kept (likely buyers) | Conversion effect kept (likely buyers) |
|---|---|---|
| 25% | 35% | 70% |
| **50%** | **69%** (66 to 73) | **84%** (78 to 90) |
| 75% | 91% | 93% |

**Half the ad spend, aimed at likely buyers, keeps about 84% of the conversions the ads cause**, so each pound works
about 1.7 times as hard. Chart: `figures/uplift/spend_curves.png`. Finding 7 turns this into money.

**Exploratory, added after the first results:** ranking by *effect per ad view* (the uplift score divided by each
user's predicted chance of being shown an ad), which is what spend efficiency calls for in theory. It beats likely
buyers for visits at a quarter of spend (+8 points, 3 to 13), but trails for conversions at a quarter of spend
(-12 points, -23 to -1), and is level elsewhere. Not a reliable improvement on this data.

### 3. What to recommend

- **Test concentrating spend.** The bulk of the estimated effect comes from a minority of users and ad views, which
  suggests moving spend towards them. Whether that holds once auction prices, ad frequency and audience mix respond
  is a question for a holdout test (finding 9 proposes one).
- **Start with the simple model.** A likely-buyer ranking is as good as an uplift model for conversions here, and
  simpler to build, explain and maintain.
- **Use uplift modelling where it earns its keep:** visits, or very tight budgets. And test any switch with a holdout
  before trusting it, because the gains are small and the conversion signal is weak.

## How the grading avoids two traps

- **The leak from finding 1.** Every share uses doubly robust pseudo-outcomes, computed with cross-fitting inside the
  held-out set, so the small imbalance between groups can't flatter or penalise a model.
- **Tied scores.** Models give big blocks of users exactly the same score. A plain sort would order those users by
  their position in the file, which here is linked to treatment, and that bent the first version of the conversion
  curves. Grading now treats tied users as interchangeable (the average of breaking ties at random).

## Limits

- **Spend is proxied by ad views** (exposed or not). Real spend also depends on how many ads each user sees and what
  each costs; the data doesn't include either.
- **Benchmark, not live results.** Criteo sub-sampled the file; shares describe this file.
- **Anonymised features.** We can say who the persuadable users are only as "high on f-something"; that is not useful
  to a marketer, so we describe them by behaviour (likely buyers who are also shown ads) instead.

## Plain-English glossary

- **Uplift:** how much targeting a user changes their chance of visiting or buying.
- **Uplift curve:** share of users targeted (best first) against share of the ads' total effect captured. The
  diagonal is random targeting.
- **Held-out users:** users kept aside so models are graded on people they never trained on.
- **Qini score:** a standard single-number summary of an uplift curve. We report it uncorrected, for comparison with
  other studies, next to our leak-corrected version.
