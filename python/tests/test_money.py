import numpy as np
import pytest

from incrementality.money import (break_even_attributed_roas, draws, incremental_roas, profit_per_pound,
                                  split_efficiency)


def test_roas_and_profit_arithmetic():
    i = incremental_roas(8, 0.5)
    assert i == 4
    assert profit_per_pound(i, 0.3) == pytest.approx(0.2)
    assert profit_per_pound(incremental_roas(break_even_attributed_roas(0.3, 0.5), 0.5), 0.3) == pytest.approx(0)


def test_split_efficiency_averages_back_to_one():
    top, rest = split_efficiency(0.84, 0.5)
    assert (top, rest) == (pytest.approx(1.68), pytest.approx(0.32))
    assert 0.5 * top + 0.5 * rest == pytest.approx(1)


def test_draws_match_interval():
    x = draws(0.5, 0.4, 0.6, 200_000, np.random.default_rng(0))
    assert np.percentile(x, [2.5, 97.5]) == pytest.approx([0.4, 0.6], abs=0.003)
