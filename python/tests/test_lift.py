import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
from linearmodels.iv import IV2SLS

from incrementality.lift import (aipw, complier_baseline, exposed_effect, ipw_effect, lin_ate, rate_diff,
                                 ratio_of_effects, weighted_smd)


def test_rate_diff_matches_hand_calculation():
    r = rate_diff(60, 1000, 40, 1000)
    assert r.diff == pytest.approx(0.02)
    assert r.rel == pytest.approx(0.5)
    se = np.sqrt(0.06 * 0.94 / 1000 + 0.04 * 0.96 / 1000)
    assert r.diff_lo == pytest.approx(0.02 - 1.959964 * se, rel=1e-5)
    assert r.rel_lo < r.rel < r.rel_hi


def _experiment(n=40_000, seed=3):
    """Simulated one-sided-exposure test: only treated, high-intent users can be exposed."""
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 2))
    z = rng.binomial(1, 0.85, n)
    intent = 1 / (1 + np.exp(-(x[:, 0] - 2)))
    d = z * rng.binomial(1, intent)
    y = rng.binomial(1, np.clip(0.02 + 0.05 * intent + 0.03 * d, 0, 1))
    return pd.DataFrame({"f0": x[:, 0], "f1": x[:, 1], "treatment": z, "exposure": d, "y": y})


def test_lin_ate_equals_statsmodels_interacted_ols_with_hc1():
    df = _experiment()
    feats = ["f0", "f1"]
    cols = {c: df[c].to_numpy() for c in df}
    halves = lambda: [{c: v[: len(df) // 2] for c, v in cols.items()}, {c: v[len(df) // 2:] for c, v in cols.items()}]
    ours = lin_ate(halves, "y", feats)

    xc = df[feats] - df[feats].mean()
    X = pd.concat([df[["treatment"]], xc, xc.mul(df["treatment"], axis=0).add_suffix("_t")], axis=1)
    ref = sm.OLS(df["y"], sm.add_constant(X)).fit(cov_type="HC1")
    assert ours.estimate == pytest.approx(ref.params["treatment"], rel=1e-8)
    assert ours.se == pytest.approx(ref.bse["treatment"], rel=1e-6)


def test_wald_ratio_equals_2sls_and_complier_baseline_is_consistent_with_it():
    df = _experiment()
    itt_y = df.groupby("treatment")["y"].mean().diff().iloc[-1]
    share = df.loc[df.treatment == 1, "exposure"].mean()
    iv = IV2SLS(df["y"], np.ones(len(df)), df["exposure"], df["treatment"]).fit(cov_type="robust")
    assert iv.params["exposure"] == pytest.approx(itt_y / share, rel=1e-8)

    # Two routes to the exposed users' no-ad rate must agree: subtracting never-seers from control, or observed rate minus effect
    rate_c = df.loc[df.treatment == 0, "y"].mean()
    rate_nt = df.loc[(df.treatment == 1) & (df.exposure == 0), "y"].mean()
    rate_exposed = df.loc[df.exposure == 1, "y"].mean()
    assert complier_baseline(rate_c, rate_nt, share) == pytest.approx(rate_exposed - itt_y / share, rel=1e-8)


def test_aipw_removes_confounding_that_biases_the_raw_difference():
    """Treatment share depends on a feature that also drives the outcome (like merged tests with different ratios)."""
    rng = np.random.default_rng(7)
    n = 200_000
    x = rng.normal(size=(n, 2))
    p_treat = np.where(x[:, 0] > 1, 0.97, 0.80)
    t = rng.binomial(1, p_treat)
    intent = 1 / (1 + np.exp(-(x[:, 0] - 1.5)))
    d = t * rng.binomial(1, 0.3 * intent)
    true_effect_on_exposed = 0.10
    y = rng.binomial(1, np.clip(0.03 + 0.4 * intent + true_effect_on_exposed * d, 0, 1))

    raw = y[t == 1].mean() - y[t == 0].mean()
    res_y, e = aipw(x, t, y, seed=1)
    res_d, _ = aipw(x, t, d, seed=1, control_outcome_is_zero=True, propensity=e)
    true_itt = true_effect_on_exposed * (0.3 * intent).mean()
    assert abs(raw - true_itt) > 4 * res_y.se  # the raw difference is visibly biased
    assert abs(res_y.estimate - true_itt) < 3 * res_y.se
    cace, se = ratio_of_effects(res_y, res_d)
    assert abs(cace - true_effect_on_exposed) < 3 * se

    # Sensitivity checks: weighting alone also removes the bias, and the weights balance the confounder
    ipw = ipw_effect(t, y, e)
    assert abs(ipw.estimate - true_itt) < 3 * ipw.se
    raw_gap = abs(x[t == 1, 0].mean() - x[t == 0, 0].mean())
    assert abs(weighted_smd(x, t, e)[0]) < raw_gap / 4


def test_exposed_effect_matches_2sls_point_and_interval():
    df = _experiment(n=200_000)
    e, nt, c = df[df.exposure == 1], df[(df.treatment == 1) & (df.exposure == 0)], df[df.treatment == 0]
    ours = exposed_effect(e.y.sum(), len(e), nt.y.sum(), len(nt), c.y.sum(), len(c))
    iv = IV2SLS(df["y"], np.ones(len(df)), df["exposure"], df["treatment"]).fit(cov_type="robust")
    assert ours.cace == pytest.approx(iv.params["exposure"], rel=1e-8)
    # Our interval holds the exposure share fixed; 2SLS lets it vary. With a large exposed group they nearly agree.
    assert (ours.cace_hi - ours.cace_lo) / 2 / 1.959964 == pytest.approx(iv.std_errors["exposure"], rel=0.05)
    assert ours.caused_share == pytest.approx(ours.cace / ours.rate_exposed)
    assert ours.caused_lo < ours.caused_share < ours.caused_hi
