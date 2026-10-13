import numpy as np
import pytest

from incrementality.planning import mde_relative, users_needed


def test_users_needed_inverts_mde():
    for share in (0.05, 0.1, 0.5):
        n = users_needed(0.05, share, 0.002)
        assert mde_relative(n, share, 0.002) == pytest.approx(0.05, rel=1e-6)


def test_even_split_needs_fewest_users_and_rare_outcomes_need_more():
    assert users_needed(0.05, 0.5, 0.002) < users_needed(0.05, 0.1, 0.002) < users_needed(0.05, 0.05, 0.002)
    assert users_needed(0.05, 0.1, 0.002) > users_needed(0.05, 0.1, 0.04)


def test_power_by_simulation_matches_the_formula():
    """Simulate many tests at exactly the formula's MDE: about 80% should come out significant."""
    rng = np.random.default_rng(0)
    users, share, p = 2_000_000, 0.1, 0.01
    lift = mde_relative(users, share, p)
    n_c, n_t = int(users * share), int(users * (1 - share))
    x_c, x_t = rng.binomial(n_c, p, 4000), rng.binomial(n_t, p * (1 + lift), 4000)
    pc, pt = x_c / n_c, x_t / n_t
    se_log = np.sqrt((1 - pt) / (n_t * pt) + (1 - pc) / (n_c * pc))
    assert np.mean(np.log(pt / pc) / se_log > 1.959964) == pytest.approx(0.8, abs=0.03)
