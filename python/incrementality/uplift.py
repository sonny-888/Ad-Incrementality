"""Uplift models: who is persuaded by an ad?

An uplift model predicts, for each user, how much being targeted changes their chance of visiting or buying:
    uplift(x) = P(outcome | targeted, x) - P(outcome | not targeted, x)
Ranking users by it says who to target first.

- T-learner: two models, one fitted on treated users and one on control users; uplift is the difference.
- X-learner (Kunzel et al. 2019): starts from the T-learner, imputes each user's individual effect, then fits a second
  pair of models to those imputed effects. Often better when one group is much smaller (control here is 15%).
- Response score: the treated-user model alone, P(outcome | targeted, x). This is "target likely buyers", what
  retargeting usually optimises, and the comparison that shows why uplift modelling matters.

Evaluation uses doubly robust pseudo-outcomes (psi, from lift.aipw) on held-out users: the mean of psi over any group
defined by features estimates that group's average effect, corrected for the small leak found in finding 1.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

Z95 = 1.959964


def _clf(seed: int) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1, early_stopping=True, random_state=seed)


def _reg(seed: int) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.1, early_stopping=True, random_state=seed)


@dataclass
class UpliftModels:
    m1: HistGradientBoostingClassifier  # outcome model on treated users
    m0: HistGradientBoostingClassifier  # outcome model on control users
    tau1: HistGradientBoostingRegressor | None = None  # X-learner: effect model fitted on treated users
    tau0: HistGradientBoostingRegressor | None = None  # X-learner: effect model fitted on control users
    g: float = 0.85  # X-learner weight on tau0, the share treated

    def response(self, X: np.ndarray) -> np.ndarray:
        return self.m1.predict_proba(X)[:, 1]

    def t_learner(self, X: np.ndarray) -> np.ndarray:
        return self.m1.predict_proba(X)[:, 1] - self.m0.predict_proba(X)[:, 1]

    def x_learner(self, X: np.ndarray) -> np.ndarray:
        # Weight the control-fitted effect model by the treated share, as Kunzel et al. suggest: the model built on
        # the larger group's outcomes (via m1) deserves more weight.
        return self.g * self.tau0.predict(X) + (1 - self.g) * self.tau1.predict(X)


def fit_uplift(X: np.ndarray, t: np.ndarray, y: np.ndarray, seed: int = 0, x_learner: bool = True) -> UpliftModels:
    treated, control = t == 1, t == 0
    m1 = _clf(seed).fit(X[treated], y[treated])
    m0 = _clf(seed).fit(X[control], y[control])
    models = UpliftModels(m1, m0, g=float(treated.mean()))
    if x_learner:
        d1 = y[treated] - m0.predict_proba(X[treated])[:, 1]  # treated: actual outcome minus predicted no-ad outcome
        d0 = m1.predict_proba(X[control])[:, 1] - y[control]  # control: predicted ad outcome minus actual outcome
        models.tau1 = _reg(seed).fit(X[treated], d1)
        models.tau0 = _reg(seed).fit(X[control], d0)
    return models



# Grading. Models often give big blocks of users the same score; a plain sort would then order those users by
# their position in the file, which here is linked to treatment. Every function below instead treats tied users
# as interchangeable: a cut-off that falls inside a tied block takes the same fraction of each of them, which is
# the average result of breaking ties at random.


def top_weights(score: np.ndarray, top_share: float) -> np.ndarray:
    """Weight 1 for users clearly inside the top `top_share`, a common fraction for users tied at the cut, else 0."""
    k = top_share * len(score)
    if k <= 0:
        return np.zeros(len(score))
    threshold = np.sort(score)[::-1][min(int(np.ceil(k)), len(score)) - 1]
    w = (score > threshold).astype(float)
    tied = score == threshold
    w[tied] = (k - w.sum()) / tied.sum()
    return w


@dataclass(frozen=True)
class Capture:
    top_share: float  # share of users targeted, ranked by score
    lift_share: float  # share of all incremental outcomes they account for
    lo: float
    hi: float


def _ratio_ci(psi: np.ndarray, w: np.ndarray) -> tuple[float, float, float]:
    """sum(w psi) / sum(psi) with a 95% interval from its influence function (w held fixed)."""
    b = psi.mean()
    r = (psi * w).mean() / b
    se = ((psi * w - r * psi) / b).std(ddof=1) / np.sqrt(len(psi))
    return float(r), float(r - Z95 * se), float(r + Z95 * se)


def capture(score: np.ndarray, psi: np.ndarray, top_share: float) -> Capture:
    """Share of the total effect held by the top `top_share` of users ranked by `score`, with a 95% interval."""
    return Capture(top_share, *_ratio_ci(psi, top_weights(score, top_share)))


def capture_diff(score_a: np.ndarray, score_b: np.ndarray, psi: np.ndarray, top_share: float
                 ) -> tuple[float, float, float]:
    """Paired difference in capture share (a minus b) on the same users, with a 95% interval."""
    return _ratio_ci(psi, top_weights(score_a, top_share) - top_weights(score_b, top_share))


def overlap(score_a: np.ndarray, score_b: np.ndarray, top_share: float) -> float:
    """Share of the top group chosen by a that b also chooses."""
    wa, wb = top_weights(score_a, top_share), top_weights(score_b, top_share)
    return float((wa * wb).sum() / wa.sum())


def exposure_share(score: np.ndarray, exposure: np.ndarray, treatment: np.ndarray, top_share: float) -> float:
    """Share of treated users' ad exposures (a proxy for spend) that fall in the top `top_share` of users."""
    exposed = ((exposure == 1) & (treatment == 1)).astype(float)
    return float((top_weights(score, top_share) * exposed).sum() / exposed.sum())


def _grouped_path(score: np.ndarray, *values: np.ndarray) -> list[np.ndarray]:
    """Cumulative sums of each value array at the end of every tied-score block, best block first, starting at 0."""
    order = np.argsort(-score, kind="stable")
    s = score[order]
    starts = np.concatenate([[0], np.flatnonzero(np.diff(s) != 0) + 1])
    out = [np.concatenate([[0.0], np.cumsum(np.add.reduceat(np.ones(len(s)), starts))])]
    out += [np.concatenate([[0.0], np.cumsum(np.add.reduceat(v[order].astype(float), starts))]) for v in values]
    return out


def uplift_curve(score: np.ndarray, psi: np.ndarray, points: int = 101) -> tuple[np.ndarray, np.ndarray]:
    """Share of users targeted (x) against share of total effect captured (y), ranking by `score`.

    Within a tied block both quantities grow in step, so interpolating between block ends is exact.
    """
    count, cum_psi = _grouped_path(score, psi)
    x = np.linspace(0, 1, points)
    return x, np.interp(x * len(psi), count, cum_psi) / psi.sum()


def spend_curve(score: np.ndarray, psi: np.ndarray, cost: np.ndarray, points: int = 101
                ) -> tuple[np.ndarray, np.ndarray]:
    """Share of spend (x) against share of total effect captured (y), targeting users best first.

    `cost` is each user's spend if targeted; here 1 for treated users who saw an ad, else 0.
    """
    _, cum_cost, cum_psi = _grouped_path(score, cost, psi)
    keep = _last_of_flat(cum_cost)
    x = np.linspace(0, 1, points)
    return x, np.interp(x * cost.sum(), cum_cost[keep], cum_psi[keep]) / psi.sum()


def _last_of_flat(cum_cost: np.ndarray) -> np.ndarray:
    """Where spend stays flat (users who cost nothing), keep the last point: free users are always worth taking."""
    return np.concatenate([np.diff(cum_cost) > 0, [True]])


def spend_capture(score: np.ndarray, psi: np.ndarray, cost: np.ndarray, spend_share: float) -> Capture:
    """Share of the total effect captured when targeting best-first until `spend_share` of spend is used.

    Reported `top_share` is the share of users targeted at that point.
    """
    count, cum_cost = _grouped_path(score, cost)
    keep = _last_of_flat(cum_cost)
    users = float(np.interp(spend_share * cost.sum(), cum_cost[keep], count[keep]))
    share = users / len(score)
    return Capture(share, *_ratio_ci(psi, top_weights(score, share)))


def spend_capture_diff(score_a: np.ndarray, score_b: np.ndarray, psi: np.ndarray, cost: np.ndarray,
                       spend_share: float) -> tuple[float, float, float]:
    """Paired difference (a minus b) in effect captured at the same share of spend, with a 95% interval."""
    wa = top_weights(score_a, spend_capture(score_a, psi, cost, spend_share).top_share)
    wb = top_weights(score_b, spend_capture(score_b, psi, cost, spend_share).top_share)
    return _ratio_ci(psi, wa - wb)


def area_vs_random(score: np.ndarray, psi: np.ndarray) -> float:
    """Area between the uplift curve and the random-targeting diagonal (0 = no better than random)."""
    x, y = uplift_curve(score, psi, points=1001)
    return float(np.trapezoid(y - x, x))
