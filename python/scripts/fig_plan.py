"""Chart for finding 9: how big a holdout must be to detect a given lift.

    py python/scripts/fig_plan.py

Reads results/plan.json (plan_analysis.py). Base rates are the Criteo control group's visit and conversion rates.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

from incrementality.planning import mde_relative, users_needed
from incrementality.style import PAL, apply

ROOT = Path(__file__).resolve().parents[2]
P = json.loads((ROOT / "results" / "plan.json").read_text(encoding="utf-8"))
RAMP = LinearSegmentedColormap.from_list("seq", ["#A9C2DA", "#2F4A6E"])


def sizing(path: Path) -> None:
    shares = P["control_shares"]
    colors = {s: RAMP(i / (len(shares) - 1)) for i, s in enumerate(shares)}
    users = np.logspace(np.log10(2e5), np.log10(3e7), 200)
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2))
    for ax, outcome, ymax in zip(axes, ["conversion", "visit"], [0.6, 0.12]):
        p = P["outcomes"][outcome]["base_rate"]
        for s in shares:
            ax.plot(users, mde_relative(users, s, p), color=colors[s], lw=2.4 if s == 0.10 else 1.6,
                    label=f"{s:.0%} held out" + (" (even split)" if s == 0.5 else ""))
        ax.legend(loc="upper right", title="Share of users held out", title_fontsize=8.5)
        ax.set_xscale("log")
        ax.set_xlim(2e5, 3e7)
        ax.set_ylim(0, ymax)
        ax.set_xticks([1e6, 3e6, 1e7, 3e7], ["1M", "3M", "10M", "30M"])
        ax.xaxis.set_minor_formatter(plt.NullFormatter())
        ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
        ax.set_xlabel("Users in the test")
        ax.grid(axis="x", visible=True, which="major")
        ax.set_axisbelow(True)
        ax.set_title(f"{outcome.capitalize()}s (base rate {p:.2%} without ads)", loc="left", fontsize=11,
                     color=PAL["ink"], pad=8)

    # The headline point: a 10% conversion lift with a 10% holdout
    p_conv = P["outcomes"]["conversion"]["base_rate"]
    n10 = users_needed(0.10, 0.10, p_conv)
    axes[0].scatter([n10], [0.10], s=60, color=PAL["accent"], edgecolor=PAL["surface"], linewidth=1.5, zorder=4)
    axes[0].annotate(f"Detecting a +10% lift with a\n10% holdout takes {n10 / 1e6:.1f}M users", (n10, 0.10),
                     xytext=(n10 * 0.06, 0.03), fontsize=9, color=PAL["accent_text"],
                     arrowprops=dict(arrowstyle="-", color=PAL["accent"], lw=0.8))
    axes[0].set_ylabel("Smallest lift detected 80% of the time")

    fig.subplots_adjust(top=0.78, bottom=0.14, left=0.07, right=0.97, wspace=0.2)
    x0 = axes[0].get_position().x0
    fig.text(x0, 0.95, f"Rare conversions need big tests: {n10 / 1e6:.0f} million users to see a 10% lift "
             "with a 10% holdout", fontsize=14, fontweight="semibold", color=PAL["ink"], va="top")
    fig.text(x0, 0.885, "Smallest detectable lift by test size and share of users held out (5% false-alarm rate, "
             "80% power). Visits need about 20x fewer users.", fontsize=10, color=PAL["ink_2"], va="top")
    fig.text(x0, 0.025, "Base rates: Criteo Uplift v2.1 control group. Formula checked against the Criteo test's own "
             "precision (within 0.2 points).", fontsize=8.5, color=PAL["muted"])
    fig.savefig(path, dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    apply()
    out = ROOT / "figures" / "plan" / "holdout_sizing.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    sizing(out)
    print(f"wrote {out.relative_to(ROOT)}")
