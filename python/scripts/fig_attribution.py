"""Chart for finding 5, the headline: of every 100 conversions attribution credits to ads, how many did ads cause?

    py python/scripts/fig_attribution.py

Credited = every conversion by a user who saw an ad (how view-based attribution hands out credit).
Caused   = the effect of seeing an ad (doubly robust, finding 4) as a share of those users' conversion rate.
Reads results/lift_aipw.json and results/lift.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from incrementality.style import PAL, apply, finish

ROOT = Path(__file__).resolve().parents[2]
AIPW = json.loads((ROOT / "results" / "lift_aipw.json").read_text(encoding="utf-8"))
LIFT = json.loads((ROOT / "results" / "lift.json").read_text(encoding="utf-8"))


def waffle(path: Path) -> None:
    c = AIPW["conversion"]
    caused = round(100 * c["caused_share"])
    lo, hi = round(100 * c["caused_share_lo"]), round(100 * c["caused_share_hi"])
    anyway = 100 - caused
    overstatement = 1 / c["caused_share"]
    raw = round(100 * LIFT["conversion"]["exposed"]["caused_share"])

    fig = plt.figure(figsize=(8.5, 5.2))
    ax = fig.add_axes([0.08, 0.14, 0.5, 0.64])
    gap = 0.12
    for i in range(100):
        row, col = divmod(i, 10)
        color = PAL["accent"] if i < caused else PAL["context"]
        ax.add_patch(Rectangle((col + gap / 2, 9 - row + gap / 2), 1 - gap, 1 - gap, color=color, lw=0))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.set_aspect("equal")
    ax.axis("off")

    x = 0.62
    fig.text(x, 0.70, f"{caused}", fontsize=34, fontweight="semibold", color=PAL["accent_text"], va="center")
    fig.text(x + 0.085, 0.70, "caused by the ad", fontsize=11, color=PAL["ink"], va="center")
    fig.text(x, 0.55, f"{anyway}", fontsize=34, fontweight="semibold", color=PAL["muted"], va="center")
    fig.text(x + 0.085, 0.55, "would have happened\nwithout the ad", fontsize=11, color=PAL["ink"], va="center")
    fig.text(x, 0.36, f"95% interval: {lo} to {hi} caused.\n"
                       f"Attribution overstates the ads'\nconversions by about {overstatement:.1f}x.\n"
                       f"Without correcting the leak from\nfinding 1, it would read {raw}.",
             fontsize=9, color=PAL["ink_2"], va="center", linespacing=1.5)

    finish(fig, ax, f"An estimated {caused} of every 100 credited conversions were caused by the ads",
           "View-through attribution credits every conversion after an ad view.\nSplit by the randomised test "
           "(doubly robust, under the test's assumptions).",
           path, top=0.80, left=0.08,
           source="Source: Criteo Uplift v2.1, 13,979,592 users. Shares describe this sub-sampled benchmark file.")
    plt.close(fig)


if __name__ == "__main__":
    apply()
    out = ROOT / "figures" / "attribution" / "credited_vs_caused.png"
    waffle(out)
    print(f"wrote {out.relative_to(ROOT)}")
