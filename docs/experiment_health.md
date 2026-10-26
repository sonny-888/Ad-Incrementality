# Finding 1: Is the experiment healthy?

Before trusting any lift number, check that the randomisation worked. Every number here comes from
`results/experiment_checks.json`, written by `python/scripts/experiment_checks.py`. Chart: `figures/experiment/balance.png`.

## What we checked

| Check | Question | Result | Verdict |
|---|---|---|---|
| Sample ratio | Did 85% of users land in the treated group, as designed? | 85.00% (11,882,655 of 13,979,592), p = 0.999 | Passes |
| Covariate balance | Do treated and control users look alike before any ad? | All 12 features within 0.05 standard deviations; largest gap f3 at -0.049 | Balanced in practice (the usual line is 0.1) |
| Classifier test | Can a model tell treated from control using only the features? | AUC 0.509 on 1,000,000 users; shuffled-label placebo 0.499 | Very slightly, see below |

## The nuance

With 14 million users, chance alone moves a balance gap by only about 0.00075 standard deviations. Gaps of 0.02 to
0.05 are therefore real, not noise, even though they are small. The classifier agrees: it beats a coin flip by a hair
(AUC 0.509), and the placebo run on shuffled labels (0.499) shows that edge is not a modelling artefact.

Criteo's benchmark paper (Diemert et al. 2021, arXiv 2111.10106) explains the background:

- The file merges several advertisers' incrementality tests. Those tests had **different treated shares**, so in the
  first release (v1) the features, which differ by advertiser, leaked which group a user was in. The paper calls the
  hidden test id a confounder.
- Version 2 fixed this by sub-sampling every test to the same 85% treated share. Criteo then ran a classifier
  two-sample test and found no leak (p = 0.14); its table notes "300 samples".
- The features were logged **at the moment of treatment assignment**, before any ad was shown, so the ads cannot have
  changed them.

Our check is far larger (1,000,000 users, plus a placebo) and finds a small leak still there. We can't tell which step
of building the file left it; we only see that it exists. Because the features are pre-treatment, adjusting for them
cannot introduce bias from the ads themselves, so the adjusted figures are our preferred estimates. This rests on an
assumption we cannot test: that the leak runs through f0 to f11, which the file records, and not through something it
doesn't. Finding 3 shows how much the answer moves across several adjustment methods.

The sample ratio check also needs care. The treated share matches 85% to within 2 users, which is closer than chance
would usually give. The most likely explanation is that the ratio was fixed when Criteo sub-sampled the file. So this
check confirms the file is complete and matches its documentation; it cannot tell us whether the original live tests
had a clean split.

## What we do about it

1. **Report lift raw and adjusted (finding 3):** the simple treated minus control difference, a linear adjustment for
   f0 to f11, and a doubly robust (AIPW) estimate that allows the leak to be non-linear. They disagree beyond chance,
   so the adjusted figures are the headline numbers. See `docs/lift.md`.
2. **Frame absolute numbers carefully:** the privacy sub-sampling was designed so that Criteo's real incrementality
   cannot be recovered. Lift levels describe this benchmark file, not Criteo's actual campaign results. Comparisons
   (naive vs causal, attribution vs incrementality, who is persuaded) remain valid on this data.

## Plain-English glossary

- **Standardised mean difference (SMD):** the gap between two group averages divided by how spread out the feature is.
  0.1 means the groups differ by a tenth of a typical spread.
- **AUC:** how often a model ranks a random treated user above a random control user. 0.5 is a coin flip; 1.0 is perfect.
- **Placebo run:** repeat the test where we know there is no signal (labels shuffled). It should land at 0.5.
