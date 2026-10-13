"""Is it worth the money? Turn "caused vs credited" into return on ad spend and profit.

All figures are per 1 pound of ad spend:
- attributed ROAS:  revenue the dashboard credits to ads / spend. An input: read it off the dashboard.
- incremental ROAS: revenue the ads actually caused / spend = attributed ROAS x caused share.
- profit per pound: incremental ROAS x margin - 1 (margin = profit kept from each pound of revenue).

The data has no prices or costs, so attributed ROAS and margin are stated assumptions with sensitivity tables.
The caused share and how concentrated the effect is come from the experiment.
"""

from __future__ import annotations

import numpy as np


def incremental_roas(attributed_roas: float, caused_share: float) -> float:
    return attributed_roas * caused_share


def profit_per_pound(iroas, margin: float):
    return iroas * margin - 1


def break_even_attributed_roas(margin: float, caused_share: float) -> float:
    """Lowest dashboard ROAS at which the ads pay for themselves."""
    return 1 / (margin * caused_share)


def split_efficiency(effect_share_top: float, spend_share_top: float = 0.5) -> tuple[float, float]:
    """Incremental ROAS of the best part of spend and of the rest, relative to the campaign average.

    E.g. if the best 50% of spend brings 84% of the caused conversions, it works 0.84 / 0.5 = 1.68x as hard as
    the average pound, and the other half 0.16 / 0.5 = 0.32x.
    """
    return effect_share_top / spend_share_top, (1 - effect_share_top) / (1 - spend_share_top)


def draws(estimate: float, lo: float, hi: float, n: int, rng: np.random.Generator) -> np.ndarray:
    """Normal draws matching a reported 95% interval, for propagating uncertainty into money figures."""
    return rng.normal(estimate, (hi - lo) / (2 * 1.959964), n)
