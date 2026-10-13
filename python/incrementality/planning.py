"""Sizing a holdout test: how many users, and how big a control group, to detect a given lift?

Minimum detectable lift (MDE), relative: the smallest % lift a test catches with 80% power at a 5% false-alarm rate.
For a conversion rate p, n_t treated users and n_c control users, the log of the treated/control ratio has
standard error sqrt((1 - p) / (n_t p) + (1 - p) / (n_c p)) when there is no effect, so
    MDE ~= (z_0.975 + z_0.80) x that standard error    (log scale; about the same as % for small lifts)
Rare outcomes (low p) and small control groups both push the MDE up.
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def _z(alpha: float, power: float) -> float:
    return float(stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power))


def mde_relative(users: float, control_share: float, base_rate: float, alpha: float = 0.05, power: float = 0.8):
    """Smallest relative lift (0.05 = +5%) detectable with `users` in the test, `control_share` of them held out."""
    n_t, n_c = users * (1 - control_share), users * control_share
    se = np.sqrt((1 - base_rate) / (n_t * base_rate) + (1 - base_rate) / (n_c * base_rate))
    return np.expm1(_z(alpha, power) * se)


def users_needed(mde: float, control_share: float, base_rate: float, alpha: float = 0.05, power: float = 0.8) -> float:
    """Users needed in the test to detect a relative lift of `mde`."""
    k = (1 / (1 - control_share) + 1 / control_share) * (1 - base_rate) / base_rate
    return float(k * (_z(alpha, power) / np.log1p(mde)) ** 2)
