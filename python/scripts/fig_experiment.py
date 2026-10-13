"""Chart for finding 1: covariate balance between treated and control users.

    py python/scripts/fig_experiment.py

Reads results/experiment_checks.json (written by experiment_checks.py), so every number on the chart is reproducible.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from incrementality.style import PAL, apply, finish

ROOT = Path(__file__).resolve().parents[2]
RESULTS = json.loads((ROOT / "results" / "experiment_checks.json").read_text(encoding="utf-8"))
BALANCED = 0.1


def balance_chart(path: Path) -> None:
    bal = pd.DataFrame(RESULTS["balance"]).sort_values("smd").reset_index(drop=True)
    n = RESULTS["srm"]["n_total"]

    fig, ax = plt.subplots(figsize=(8, 5.2))
    ax.axvspan(-BALANCED, BALANCED, color=PAL["context"], alpha=0.35, lw=0)
    ax.axvline(0, color=PAL["ink_2"], lw=0.8)
    ax.hlines(bal.index, 0, bal["smd"], color=PAL["primary"], lw=2)
    ax.scatter(bal["smd"], bal.index, s=48, color=PAL["primary"], edgecolor=PAL["surface"], linewidth=1.5, zorder=3)

    ax.set_yticks(bal.index, bal["feature"])
    ax.set_xlim(-0.15, 0.15)
    ax.set_xlabel("Standardised mean difference (treated minus control)")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    ax.text(BALANCED - 0.004, len(bal) - 0.6, "Balanced zone\n|SMD| < 0.1", ha="right", va="top",
            fontsize=8.5, color=PAL["ink_2"])

    worst = bal.loc[bal["smd"].abs().idxmax()]
    side = -1 if worst["smd"] < 0 else 1
    ax.text(worst["smd"] + side * 0.006, worst.name, f"Largest gap {worst['smd']:+.3f}",
            ha="right" if side < 0 else "left", va="center", fontsize=8.5, color=PAL["ink_2"])

    finish(fig, ax, "Treated and control users look alike on all 12 features",
           f"Gap between group means in standard deviations, {n:,} users. Every gap is under half the 0.1 line.",
           path, left=0.1)
    plt.close(fig)


if __name__ == "__main__":
    apply()
    balance_chart(ROOT / "figures" / "experiment" / "balance.png")
    print("wrote figures/experiment/balance.png")
