"""Lift estimates for a randomised ad test with one-sided exposure (control users can never see an ad).

- rate_diff:         treatment minus control rate, with 95% intervals on the absolute and relative lift
- lin_ate:           the same difference adjusted for user features (Lin 2013 regression, robust errors),
                     computed in chunks so 14 million rows never sit in memory at once
- complier_baseline: how often the users who saw an ad would have converted anyway (their rate without the ad)

Notation: Z = assigned group (treatment), D = actually saw an ad (exposure), Y = outcome (visit or conversion).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np
from scipy import stats

Z95 = stats.norm.ppf(0.975)


@dataclass(frozen=True)
class RateDiff:
    rate_t: float
    rate_c: float
    n_t: int
    n_c: int
    diff: float
    diff_lo: float
    diff_hi: float
    rel: float  # relative lift, rate_t / rate_c - 1
    rel_lo: float
    rel_hi: float
    p_value: float


def rate_diff(x_t: float, n_t: int, x_c: float, n_c: int) -> RateDiff:
    """Difference in proportions (x = number of successes) with normal-approximation intervals.

    The relative lift interval is built on the log of the ratio, which keeps it asymmetric and positive-safe.
    """
    p_t, p_c = x_t / n_t, x_c / n_c
    diff = p_t - p_c
    se = np.sqrt(p_t * (1 - p_t) / n_t + p_c * (1 - p_c) / n_c)
    se_log = np.sqrt((1 - p_t) / (n_t * p_t) + (1 - p_c) / (n_c * p_c))
    ratio = p_t / p_c
    return RateDiff(
        p_t, p_c, int(n_t), int(n_c), diff, diff - Z95 * se, diff + Z95 * se,
        ratio - 1, ratio * np.exp(-Z95 * se_log) - 1, ratio * np.exp(Z95 * se_log) - 1,
        float(2 * stats.norm.sf(abs(diff / se))),
    )


@dataclass(frozen=True)
class AdjustedEffect:
    estimate: float
    se: float

    @property
    def lo(self) -> float:
        return self.estimate - Z95 * self.se

    @property
    def hi(self) -> float:
        return self.estimate + Z95 * self.se


def lin_ate(batches: Callable[[], Iterable[dict[str, np.ndarray]]], outcome: str, features: list[str],
            treatment: str = "treatment") -> AdjustedEffect:
    """Average treatment effect adjusted for features, following Lin (2013).

    Regress the outcome on treatment, centred features and treatment x centred features; the treatment coefficient is
    the effect. Robust (HC1) standard errors. `batches` is called once per pass and yields dicts of numpy columns.
    Three passes: feature means, then X'X and X'y, then the robust "meat" from residuals.
    """
    total, n = np.zeros(len(features)), 0
    for b in batches():
        total += np.array([b[f].sum() for f in features])
        n += len(b[outcome])
    means = total / n

    def design(b):
        t = b[treatment].astype(float)
        xc = np.column_stack([b[f] - m for f, m in zip(features, means)])
        return np.column_stack([np.ones_like(t), t, xc, xc * t[:, None]])

    k = 2 + 2 * len(features)
    xtx, xty = np.zeros((k, k)), np.zeros(k)
    for b in batches():
        X, y = design(b), b[outcome].astype(float)
        xtx += X.T @ X
        xty += X.T @ y
    beta = np.linalg.solve(xtx, xty)

    meat = np.zeros((k, k))
    for b in batches():
        X, y = design(b), b[outcome].astype(float)
        Xe = X * (y - X @ beta)[:, None]
        meat += Xe.T @ Xe
    bread = np.linalg.inv(xtx)
    cov = bread @ meat @ bread * n / (n - k)
    return AdjustedEffect(float(beta[1]), float(np.sqrt(cov[1, 1])))


@dataclass(frozen=True)
class ExposedEffect:
    share_exposed: float  # share of the treatment group that saw an ad
    rate_exposed: float  # observed outcome rate of users who saw an ad
    baseline: float  # their rate had they not seen it
    cace: float  # effect of seeing an ad, absolute (rate_exposed - baseline)
    cace_lo: float
    cace_hi: float
    rel: float  # effect relative to baseline
    rel_lo: float
    rel_hi: float
    caused_share: float  # share of exposed users' outcomes caused by the ad (cace / rate_exposed)
    caused_lo: float
    caused_hi: float


def exposed_effect(x_e: float, n_e: int, x_nt: float, n_nt: int, x_c: float, n_c: int) -> ExposedEffect:
    """Effect of actually seeing an ad, from three disjoint groups' success counts:
    e = treated and exposed, nt = treated but never exposed, c = control.

    Equals the instrumental-variables (Wald) estimate ITT / share exposed. Intervals use the delta method treating the
    exposure share as fixed; the 2SLS robust interval (which lets the share vary too) is reported alongside as a check.
    """
    pi = n_e / (n_e + n_nt)
    r_e, r_nt, r_c = x_e / n_e, x_nt / n_nt, x_c / n_c
    v_e, v_nt, v_c = r_e * (1 - r_e) / n_e, r_nt * (1 - r_nt) / n_nt, r_c * (1 - r_c) / n_c

    base = complier_baseline(r_c, r_nt, pi)
    var_base = v_c / pi**2 + ((1 - pi) / pi) ** 2 * v_nt
    cace = r_e - base
    se_cace = np.sqrt(v_e + var_base)
    rel = r_e / base - 1
    se_rel = np.sqrt(v_e / base**2 + (r_e / base**2) ** 2 * var_base)
    caused = 1 - base / r_e
    se_caused = np.sqrt(var_base / r_e**2 + (base / r_e**2) ** 2 * v_e)
    return ExposedEffect(pi, r_e, base,
                         cace, cace - Z95 * se_cace, cace + Z95 * se_cace,
                         rel, rel - Z95 * se_rel, rel + Z95 * se_rel,
                         caused, caused - Z95 * se_caused, caused + Z95 * se_caused)


@dataclass(frozen=True)
class AIPWResult:
    estimate: float
    se: float
    psi: np.ndarray  # per-user influence values; their mean is the estimate
    m1: np.ndarray | None = None  # out-of-fold predicted outcome if treated (kept for sensitivity analysis)
    m0: np.ndarray | None = None  # ... and if control

    @property
    def lo(self) -> float:
        return self.estimate - Z95 * self.se

    @property
    def hi(self) -> float:
        return self.estimate + Z95 * self.se


def aipw(X: np.ndarray, t: np.ndarray, y: np.ndarray, folds: int = 2, seed: int = 0,
         control_outcome_is_zero: bool = False, propensity: np.ndarray | None = None,
         learner: str = "boosting") -> tuple[AIPWResult, np.ndarray]:
    """Doubly robust (augmented inverse-propensity) effect of treatment, with cross-fitting.

    Models, fitted on the other folds and scored on each held-out fold:
      e(x)  = chance of being treated given features (should be about 0.85 everywhere if randomisation is clean)
      m1(x) = outcome rate if treated, m0(x) = outcome rate if control
    psi = m1 - m0 + t (y - m1) / e - (1 - t) (y - m0) / (1 - e). The estimate is mean(psi).
    It is right if either the propensity or the outcome models are right, hence "doubly robust".
    `control_outcome_is_zero` sets m0 = 0 (used for exposure, which control users can never have).
    `propensity` lets callers reuse out-of-fold propensities across outcomes (use the same seed and folds).
    `learner`: "boosting" (gradient boosting, flexible; the headline) or "logistic" (logistic regression on
    standardised features, simple), so results can be checked against a different modelling choice.
    Returns the result and the out-of-fold propensities.
    """
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    def model():
        if learner == "logistic":
            return make_pipeline(StandardScaler(), LogisticRegression(max_iter=500))
        return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1, early_stopping=True, random_state=seed)

    n = len(t)
    fold = np.random.default_rng(seed).integers(0, folds, n)
    e = np.empty(n) if propensity is None else propensity
    m1, m0 = np.empty(n), np.zeros(n)
    for k in range(folds):
        train, test = fold != k, fold == k
        if propensity is None:
            e[test] = model().fit(X[train], t[train]).predict_proba(X[test])[:, 1]
        tr1 = train & (t == 1)
        m1[test] = model().fit(X[tr1], y[tr1]).predict_proba(X[test])[:, 1]
        if not control_outcome_is_zero:
            tr0 = train & (t == 0)
            m0[test] = model().fit(X[tr0], y[tr0]).predict_proba(X[test])[:, 1]
    e = np.clip(e, 0.01, 0.99)
    psi = m1 - m0 + t * (y - m1) / e - (1 - t) * (y - m0) / (1 - e)
    return AIPWResult(float(psi.mean()), float(psi.std(ddof=1) / np.sqrt(n)), psi, m1, m0), e


def ipw_effect(t: np.ndarray, y: np.ndarray, e: np.ndarray) -> AIPWResult:
    """Inverse-propensity-weighted effect (Horvitz-Thompson form): reweights each group by its chance of being in it.
    Uses only the propensity model, so it checks the doubly robust result from a different angle."""
    psi = t * y / e - (1 - t) * y / (1 - e)
    return AIPWResult(float(psi.mean()), float(psi.std(ddof=1) / np.sqrt(len(psi))), psi)


def weighted_smd(X: np.ndarray, t: np.ndarray, e: np.ndarray) -> np.ndarray:
    """Standardised mean differences after inverse-propensity weighting; near zero means the weights balance the
    features, i.e. the propensity model captured how treatment depended on them."""
    w = np.where(t == 1, 1 / e, 1 / (1 - e))
    m1 = np.average(X[t == 1], axis=0, weights=w[t == 1])
    m0 = np.average(X[t == 0], axis=0, weights=w[t == 0])
    sd = np.sqrt((X[t == 1].var(axis=0) + X[t == 0].var(axis=0)) / 2)
    return (m1 - m0) / sd


def ratio_of_effects(num: AIPWResult, den: AIPWResult) -> tuple[float, float]:
    """Effect of seeing an ad, adjusted: effect on the outcome / effect on exposure, with a delta-method SE."""
    r = num.estimate / den.estimate
    phi = (num.psi - r * den.psi) / den.estimate
    return r, float(phi.std(ddof=1) / np.sqrt(len(phi)))


def complier_baseline(rate_control: float, rate_treated_unexposed: float, share_exposed: float) -> float:
    """Outcome rate the exposed users would have had without the ad.

    Random assignment means the control group holds the same mix of "would see an ad" and "would never see an ad"
    users as the treatment group. In the treatment group we observe the never-seers directly (treated, not exposed),
    so we can subtract them out of the control rate:
        control rate = share_exposed x baseline(exposed type) + (1 - share_exposed) x rate(never-seers)
    """
    return (rate_control - (1 - share_exposed) * rate_treated_unexposed) / share_exposed
