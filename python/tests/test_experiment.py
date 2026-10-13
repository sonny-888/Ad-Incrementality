import duckdb
import numpy as np
import pandas as pd
import pytest

from incrementality.experiment import balance, classifier_test, srm


def test_srm_passes_on_designed_split_and_flags_a_skew():
    assert not srm(850_000, 1_000_000, 0.85).mismatch
    skewed = srm(853_000, 1_000_000, 0.85)
    assert skewed.mismatch and skewed.observed_share == pytest.approx(0.853)


def _random_assignment(n=20_000, seed=1, shift=0.0):
    rng = np.random.default_rng(seed)
    t = rng.binomial(1, 0.85, n)
    df = pd.DataFrame({f"f{i}": rng.normal(size=n) for i in range(3)})
    df["f0"] += shift * t  # shift > 0 breaks balance on purpose
    df["treatment"] = t
    return df


def test_balance_smd_near_zero_under_randomisation_and_detects_shift():
    con = duckdb.connect()
    con.register("ok", _random_assignment())
    con.register("bad", _random_assignment(shift=0.3))
    feats = ["f0", "f1", "f2"]
    assert balance(con, "ok", feats)["smd"].abs().max() < 0.05
    assert balance(con, "bad", feats).set_index("feature").loc["f0", "smd"] == pytest.approx(0.3, abs=0.05)


def test_classifier_cannot_beat_coin_flip_when_random_but_can_when_leaky():
    ok, bad = _random_assignment(), _random_assignment(shift=1.0)
    feats = ["f0", "f1", "f2"]
    assert abs(classifier_test(ok[feats], ok["treatment"], folds=3).z) < 4
    assert classifier_test(bad[feats], bad["treatment"], folds=3).auc > 0.65
