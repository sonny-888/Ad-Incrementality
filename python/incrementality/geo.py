"""Geo tests: measuring a campaign by region when users can't be split (finding 8).

Methods demonstration: real Iowa county sales, simulated campaign. A known lift is added to chosen "test" counties
for a few weeks; each method then estimates it from the data, so we can grade accuracy, power and false alarms.

The panel is a counties x weeks table of log sales (logs turn a % lift into an additive shift: +5% = +0.049).

Three methods, all estimating the average % lift in test counties over the test window:
- Difference-in-differences (DiD): test counties' change from before to during, minus control counties' change.
  Collapsed to one change per county, with a t-test across counties.
- Synthetic control: a weighted mix of control counties that tracked the test counties before the campaign
  (weights >= 0, summing to 1). The gap during the campaign is the effect. Inference: placebo runs on control counties.
- Structural time series (CausalImpact-style): a local-level model of the test counties' sales with the most closely
  matching control counties as predictors, fitted before the campaign and forecast through it.
  The same idea as Google's CausalImpact, built with statsmodels rather than the R package.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from scipy.optimize import minimize

Z95 = 1.959964


@dataclass(frozen=True)
class GeoEstimate:
    method: str
    lift: float  # estimated average % lift in test counties during the test window (0.05 = +5%)
    lo: float
    hi: float

    @property
    def significant(self) -> bool:
        return self.lo > 0 or self.hi < 0


def to_pct(log_effect: float) -> float:
    return float(np.exp(log_effect) - 1)


def inject_lift(log_sales: pd.DataFrame, test: list[str], start: int, weeks: int, lift: float) -> pd.DataFrame:
    """Copy of the panel (rows = weeks, columns = counties) with a +lift% campaign in the test counties."""
    out = log_sales.copy()
    out.iloc[start:start + weeks, out.columns.get_indexer(test)] += np.log1p(lift)
    return out


def did(log_sales: pd.DataFrame, test: list[str], start: int, weeks: int, pre: int) -> GeoEstimate:
    """DiD collapsed to one before/during change per county (Bertrand, Duflo and Mullainathan 2004).

    Each county's change = its average during the test minus its average over the pre-period. The effect is the
    test counties' average change minus the controls'. The interval uses a Welch t-test across counties, which
    stays honest when weekly sales are correlated over time (a plain week-level regression does not).
    """
    pre_mean = log_sales.iloc[start - pre:start].mean()
    post_mean = log_sales.iloc[start:start + weeks].mean()
    change = post_mean - pre_mean
    is_test = change.index.isin(test)
    a, b = change[is_test], change[~is_test]
    effect = a.mean() - b.mean()
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    se = np.sqrt(va + vb)
    dof = (va + vb) ** 2 / (va**2 / (len(a) - 1) + vb**2 / (len(b) - 1))
    q = stats.t.ppf(0.975, dof)
    return GeoEstimate("did", to_pct(effect), to_pct(effect - q * se), to_pct(effect + q * se))


def synth_weights(target: np.ndarray, donors: np.ndarray) -> np.ndarray:
    """Non-negative weights summing to 1 that make the donor mix track the target series (least squares)."""
    k = donors.shape[1]
    obj = lambda w: np.sum((target - donors @ w) ** 2)
    grad = lambda w: -2 * donors.T @ (target - donors @ w)
    res = minimize(obj, np.full(k, 1 / k), jac=grad, method="SLSQP", bounds=[(0, 1)] * k,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}], options={"maxiter": 500})
    return res.x


def synth_series(log_sales: pd.DataFrame, test: list[str], start: int, pre: int) -> tuple[np.ndarray, np.ndarray]:
    """(test group's average log sales, its synthetic twin) over the whole panel, weights fitted on the pre-period."""
    controls = [c for c in log_sales.columns if c not in test]
    target = log_sales[test].mean(axis=1).to_numpy()
    donors = log_sales[controls].to_numpy()
    # Demean on the pre-period so the mix matches shape, not just level (a common synthetic-control variant)
    pre_slice = slice(start - pre, start)
    t_mean, d_mean = target[pre_slice].mean(), donors[pre_slice].mean(axis=0)
    w = synth_weights(target[pre_slice] - t_mean, donors[pre_slice] - d_mean)
    return target, (donors - d_mean) @ w + t_mean


def _synth_gap(log_sales: pd.DataFrame, test: list[str], start: int, weeks: int, pre: int) -> tuple[float, float]:
    """(average gap during the test window, pre-period root mean squared gap) for the test group's average."""
    target, synth = synth_series(log_sales, test, start, pre)
    gap = target - synth
    return float(gap[start:start + weeks].mean()), float(np.sqrt(np.mean(gap[start - pre:start] ** 2)))


def synthetic_control(log_sales: pd.DataFrame, test: list[str], start: int, weeks: int, pre: int,
                      placebos: int = 40, seed: int = 0) -> GeoEstimate:
    """Synthetic control for the average of the test counties, with a placebo-based 95% interval.

    Placebos: pretend random groups of control counties (same size) got the campaign and record their gaps.
    The spread of those gaps is what "no effect" looks like, giving the interval around the real gap.
    """
    effect, _ = _synth_gap(log_sales, test, start, weeks, pre)
    controls = [c for c in log_sales.columns if c not in test]
    rng = np.random.default_rng(seed)
    pool = log_sales[controls]
    null = []
    for _ in range(placebos):
        fake = list(rng.choice(controls, size=len(test), replace=False))
        null.append(_synth_gap(pool, fake, start, weeks, pre)[0])
    # Spread of placebo gaps x t multiplier. Reading the 2.5th/97.5th percentiles straight off 40 placebos leans
    # on the one or two most extreme values and gave intervals that were too narrow in testing.
    half = stats.t.ppf(0.975, placebos - 1) * np.std(null, ddof=1)
    return GeoEstimate("synthetic_control", to_pct(effect), to_pct(effect - half), to_pct(effect + half))


def structural_ts(log_sales: pd.DataFrame, test: list[str], start: int, weeks: int, pre: int,
                  predictors: int = 5) -> GeoEstimate:
    """CausalImpact-style: local level + regression on the best-matching control counties, forecast through the test.

    Predictors are the control counties most correlated with the test group's average before the campaign (CausalImpact
    picks predictors with a spike-and-slab prior; picking the top correlations is a simple stand-in).
    """
    controls = [c for c in log_sales.columns if c not in test]
    y = log_sales[test].mean(axis=1)
    pre_idx = slice(start - pre, start)
    corr = log_sales[controls].iloc[pre_idx].corrwith(y.iloc[pre_idx])
    X = log_sales[corr.nlargest(predictors).index]
    y_fit, X_fit = y.iloc[pre_idx].to_numpy(), X.iloc[pre_idx].to_numpy()
    X_test, y_test = X.iloc[start:start + weeks].to_numpy(), y.iloc[start:start + weeks].to_numpy()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = sm.tsa.UnobservedComponents(y_fit, level="llevel", exog=X_fit)
        res = model.fit(disp=False, maxiter=200)
        fc = res.get_forecast(steps=weeks, exog=X_test)
    # Average effect over the window. Forecast errors are correlated across weeks, so use the simulated covariance
    sims = res.simulate(nsimulations=weeks, repetitions=500, anchor="end", exog=X_test,
                        rng=np.random.default_rng(1)).reshape(weeks, -1)
    effect = float(np.mean(y_test - fc.predicted_mean))
    avg_paths = sims.mean(axis=0)
    lo_q, hi_q = np.percentile(y_test.mean() - avg_paths, [2.5, 97.5])
    return GeoEstimate("structural_ts", to_pct(effect), to_pct(lo_q), to_pct(hi_q))
