import numpy as np
import pandas as pd
import pytest

from incrementality.geo import did, inject_lift, structural_ts, synth_weights, synthetic_control


def _panel(counties=60, weeks=160, seed=5):
    """Log sales with shared seasonality and trend, county-specific loadings, and autocorrelated noise."""
    rng = np.random.default_rng(seed)
    t = np.arange(weeks)
    season = np.sin(2 * np.pi * t / 52)
    trend = 0.002 * t
    loading = rng.uniform(0.5, 1.5, counties)
    level = rng.normal(10, 1, counties)
    noise = np.zeros((weeks, counties))
    for i in range(1, weeks):
        noise[i] = 0.5 * noise[i - 1] + rng.normal(0, 0.03, counties)
    y = level + np.outer(season, loading) * 0.2 + trend[:, None] + noise
    return pd.DataFrame(y, columns=[f"C{i:02d}" for i in range(counties)])


START, WEEKS, PRE = 120, 8, 104
TEST = [f"C{i:02d}" for i in range(0, 60, 6)]  # 10 test counties


def test_synth_weights_recover_an_exact_mix():
    rng = np.random.default_rng(0)
    donors = rng.normal(size=(100, 5))
    w_true = np.array([0.5, 0.3, 0.2, 0, 0])
    assert synth_weights(donors @ w_true, donors) == pytest.approx(w_true, abs=1e-3)


@pytest.mark.parametrize("method", [did, synthetic_control, structural_ts])
def test_each_method_recovers_a_known_10pct_lift(method):
    panel = inject_lift(_panel(), TEST, START, WEEKS, 0.10)
    est = method(panel, TEST, START, WEEKS, PRE)
    assert est.lift == pytest.approx(0.10, abs=0.03)
    assert est.lo < 0.10 < est.hi and est.significant


@pytest.mark.parametrize("method", [did, synthetic_control, structural_ts])
def test_injected_lift_shifts_estimate_and_interval_exactly(method):
    """All three learn only from pre-campaign weeks, so a lift moves the estimate by exactly that lift (in logs).
    This lets the simulation study run each test once without a campaign and read off every lift size."""
    base = _panel(seed=9)
    e0 = method(base, TEST, START, WEEKS, PRE)
    e5 = method(inject_lift(base, TEST, START, WEEKS, 0.05), TEST, START, WEEKS, PRE)
    for a, b in [(e0.lift, e5.lift), (e0.lo, e5.lo), (e0.hi, e5.hi)]:
        assert np.log1p(b) - np.log1p(a) == pytest.approx(np.log1p(0.05), abs=1e-6)


def test_did_false_alarm_rate_is_near_5pct_without_a_campaign():
    alarms = 0
    for seed in range(200):
        rng = np.random.default_rng(1000 + seed)
        panel = _panel(seed=seed)
        test = list(rng.choice(panel.columns, 10, replace=False))
        alarms += did(panel, test, START, WEEKS, PRE).significant
    assert alarms / 200 < 0.10
