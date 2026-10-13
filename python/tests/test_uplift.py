import numpy as np
import pytest

from incrementality.lift import aipw
from incrementality.uplift import (area_vs_random, capture, capture_diff, exposure_share, fit_uplift, spend_capture,
                                   spend_curve, top_weights, uplift_curve)


def _persuadable_world(n=120_000, seed=11):
    """Likely buyers (high x0) buy anyway; persuadable users (high x1) only respond to ads."""
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 3))
    t = rng.binomial(1, 0.85, n)
    base = 1 / (1 + np.exp(-(X[:, 0] - 1)))
    effect = 0.12 * (X[:, 1] > 0.8)  # smaller than the spread in baseline intent, as in real retargeting
    y = rng.binomial(1, np.clip(0.6 * base + effect * t, 0, 1))
    return X, t, y, effect


def test_capture_on_known_psi():
    psi = np.array([4.0, 3.0, 2.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    score = np.arange(10)[::-1].astype(float)
    c = capture(score, psi, 0.2)
    assert c.lift_share == pytest.approx(0.7)
    x, y = uplift_curve(score, psi, points=11)
    assert y[0] == 0 and y[-1] == pytest.approx(1) and y[2] == pytest.approx(0.7)

    reverse = -score  # ranks the zero-effect users first
    d, lo, hi = capture_diff(score, reverse, psi, 0.2)
    assert d == pytest.approx(0.7) and lo < d < hi
    exposure = np.array([1, 1, 0, 0, 0, 0, 0, 0, 1, 1])
    assert exposure_share(score, exposure, np.ones(10), 0.2) == pytest.approx(0.5)


def test_ties_count_every_tied_user_equally_regardless_of_file_order():
    psi = np.array([4.0, 3.0, 2.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    flat = np.zeros(10)  # one big tie: any cut must capture exactly its own share
    assert capture(flat, psi, 0.2).lift_share == pytest.approx(0.2)
    x, y = uplift_curve(flat, psi, points=11)
    assert np.allclose(y, x)
    assert top_weights(np.array([3, 2, 2, 2, 1.0]), 0.4).tolist() == pytest.approx([1, 1 / 3, 1 / 3, 1 / 3, 0])


def test_spend_curve_and_capture():
    psi = np.array([5.0, 3.0, 2.0, 0.0])
    score = np.array([4.0, 3.0, 2.0, 1.0])
    cost = np.array([1.0, 0.0, 1.0, 2.0])  # user 2 is free to target (never shown an ad)
    x, y = spend_curve(score, psi, cost, points=5)
    assert y[1] == pytest.approx(0.8)  # 25% of spend buys users 1 and 2: effect 8 of 10
    c = spend_capture(score, psi, cost, 0.5)
    assert c.lift_share == pytest.approx(1.0) and c.top_share == pytest.approx(0.75)


def test_uplift_models_find_persuadables_and_response_model_does_not():
    X, t, y, effect = _persuadable_world()
    tr = np.arange(len(y)) < 80_000
    te = ~tr
    models = fit_uplift(X[tr], t[tr], y[tr], seed=1)
    psi = aipw(X[te], t[te], y[te], seed=1)[0].psi

    t_auc = area_vs_random(models.t_learner(X[te]), psi)
    x_auc = area_vs_random(models.x_learner(X[te]), psi)
    resp_auc = area_vs_random(models.response(X[te]), psi)
    assert t_auc > 0.15 and x_auc > 0.15
    assert resp_auc < t_auc - 0.1  # targeting likely buyers misses the persuadable users
    # About 21% of users are persuadable (x1 > 0.8); the top 25% by X-learner should hold most of the effect
    assert capture(models.x_learner(X[te]), psi, 0.25).lift_share > 0.7
