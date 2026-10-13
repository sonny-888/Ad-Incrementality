"""Charts for finding 8: a worked geo-test example, and what each test design can detect.

    py python/scripts/fig_geo.py

Methods demonstration: real Iowa county sales, simulated campaign.
Reads data/processed/iowa_log_sales.parquet (example) and results/geo.json (design results).
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from incrementality.geo import inject_lift, synth_series, synthetic_control
from incrementality.style import PAL, SOURCE_IOWA, apply, finish

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "processed" / "iowa_log_sales.parquet"
OUT = ROOT / "figures" / "geo"
EXAMPLE = {"n_test": 10, "weeks": 8, "lift": 0.10, "pre": 104, "seed": 11}


def example(path: Path) -> None:
    panel = pd.read_parquet(PANEL)
    rng = np.random.default_rng(EXAMPLE["seed"])
    start = len(panel) - 30  # a recent campaign, with some weeks after it
    test = list(rng.choice(panel.columns, EXAMPLE["n_test"], replace=False))
    lifted = inject_lift(panel, test, start, EXAMPLE["weeks"], EXAMPLE["lift"])
    est = synthetic_control(lifted, test, start, EXAMPLE["weeks"], EXAMPLE["pre"])
    target, synth = synth_series(lifted, test, start, EXAMPLE["pre"])

    show = slice(start - 52, start + EXAMPLE["weeks"] + 8)
    weeks = panel.index[show]
    # Index both lines to the synthetic twin's pre-period average, so the y axis reads as % above or below normal
    base = synth[start - 52:start].mean()
    t_idx, s_idx = np.expm1(target[show] - base), np.expm1(synth[show] - base)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.axvspan(panel.index[start], panel.index[start + EXAMPLE["weeks"] - 1], color=PAL["accent"], alpha=0.08, lw=0)
    ax.plot(weeks, s_idx, color=PAL["muted"], lw=1.6, ls="--", label="Synthetic twin (weighted mix of other counties)")
    ax.plot(weeks, t_idx, color=PAL["primary"], lw=2, label=f"Test counties (average of {EXAMPLE['n_test']})")
    top = max(t_idx.max(), s_idx.max()) + 0.12
    ax.text(panel.index[start + 1], top, f"Simulated campaign\n+{EXAMPLE['lift']:.0%} for "
            f"{EXAMPLE['weeks']} weeks", fontsize=9, color=PAL["accent_text"], va="top")
    ax.set_ylim(top=top + 0.02)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:+.0%}")
    ax.set_ylabel("Weekly sales vs normal")
    lo = min(t_idx.min(), s_idx.min())
    ax.set_ylim(lo - 0.35, ax.get_ylim()[1])  # room for the legend below the lines
    ax.legend(loc="lower left", ncol=2)
    ax.set_axisbelow(True)

    finish(fig, ax, f"Synthetic control estimates the +{EXAMPLE['lift']:.0%} campaign at {est.lift:+.0%} "
           f"({est.lo:+.0%} to {est.hi:+.0%})",
           "Methods demonstration: real Iowa liquor sales, simulated campaign. Weekly sales swing a lot, so the "
           "interval is wide.", path, source=SOURCE_IOWA, left=0.09)
    plt.close(fig)


NAMES = {"did": "Difference-in-differences", "synthetic_control": "Synthetic control",
         "structural_ts": "CausalImpact-style time series"}


def mde_chart(path: Path) -> None:
    """Smallest lift each design detects 80% of the time, size-adjusted so every method has a 5% false-alarm rate."""
    g = json.loads((ROOT / "results" / "geo.json").read_text(encoding="utf-8"))
    weeks, counts = g["design"]["weeks"], g["design"]["n_test"]
    colors = dict(zip(counts, [PAL["secondary"], PAL["primary"], PAL["primary_strong"]]))
    fig, axes = plt.subplots(1, 3, figsize=(11, 5), sharey=True)
    for ax, method in zip(axes, ["did", "synthetic_control", "structural_ts"]):
        cells = g["methods"][method]
        for n in counts:
            ys = [cells[f"{n}c_{w}w"]["min_detectable_lift_size_adjusted"] for w in weeks]
            ax.plot(weeks, ys, color=colors[n], lw=2.2, marker="o", ms=6, mec=PAL["surface"], mew=1.2)
            ax.text(weeks[-1] + 0.4, ys[-1], f"{n} counties", va="center", fontsize=8.5, color=PAL["ink_2"])
        fa = np.mean([c["false_alarm_rate"] for c in cells.values()])
        ax.set_title(f"{NAMES[method]}\nfalse alarms {fa:.0%} on average (target 5%)", loc="left", fontsize=10,
                     color=PAL["accent_text"] if fa > 0.08 else PAL["ink"], pad=8)
        ax.set_xticks(weeks, [f"{w} wk" for w in weeks])
        ax.set_xlim(weeks[0] - 0.8, weeks[-1] + 3.6)
        ax.set_ylim(0, 0.32)
        ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
        ax.axhspan(0.02, 0.05, color=PAL["accent"], alpha=0.07, lw=0)
        ax.set_xlabel("Test length")
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Smallest lift detected 80% of the time")
    axes[0].text(weeks[0] - 0.6, 0.035, "Typical ad lift (2 to 5%)", fontsize=8.5, color=PAL["accent_text"], va="center")

    best = min(min(g["methods"][m][f"{counts[-1]}c_{weeks[-1]}w"]["min_detectable_lift_size_adjusted"]
                   for m in ("did", "synthetic_control")), 1)
    fig.subplots_adjust(top=0.74, bottom=0.17, left=0.07, right=0.97, wspace=0.12)
    x0 = axes[0].get_position().x0
    fig.text(x0, 0.95, f"Even {counts[-1]} counties for {weeks[-1]} weeks only reliably detect a lift of about {best:.0%}",
             fontsize=14, fontweight="semibold", color=PAL["ink"], va="top")
    fig.text(x0, 0.885, f"Methods demonstration: real Iowa liquor sales, simulated campaigns. "
             f"{g['design']['runs_per_design']} runs per design, all methods held to a 5% false-alarm rate.",
             fontsize=10, color=PAL["ink_2"], va="top")
    fig.text(x0, 0.03, SOURCE_IOWA, fontsize=8.5, color=PAL["muted"])
    fig.savefig(path, dpi=180)
    plt.close(fig)


def false_alarm_chart(path: Path) -> None:
    """False-alarm rate of each method's own 95% interval, across the 9 designs."""
    g = json.loads((ROOT / "results" / "geo.json").read_text(encoding="utf-8"))
    order = ["did", "synthetic_control", "structural_ts"]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for y, method in zip([2, 1, 0], order):
        rates = [c["false_alarm_rate"] for c in g["methods"][method].values()]
        bad = np.mean(rates) > 0.08
        color = PAL["accent"] if bad else PAL["primary"]
        ax.scatter(rates, [y] * len(rates), s=44, color=color, alpha=0.75, edgecolor=PAL["surface"], linewidth=1, zorder=3)
        ax.text(max(rates) + 0.008, y, f"{min(rates):.0%} to {max(rates):.0%}", va="center", fontsize=9,
                color=PAL["accent_text"] if bad else PAL["ink_2"])
    ax.axvline(0.05, color=PAL["ink_2"], lw=1, ls="--")
    ax.text(0.052, 2.45, "Promised 5%", fontsize=8.5, color=PAL["ink_2"])
    ax.set_yticks([2, 1, 0], [NAMES[m] for m in order])
    ax.set_ylim(-0.6, 2.7)
    ax.set_xlim(0, 0.25)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_xlabel("Share of no-campaign tests flagged as significant (each dot is one design, 300 runs)")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    ax.set_axisbelow(True)
    sts = [c["false_alarm_rate"] for c in g["methods"]["structural_ts"].values()]
    finish(fig, ax, f"The CausalImpact-style model cries wolf {min(sts) / 0.05:.0f} to {max(sts) / 0.05:.1f} times too often",
           "False alarms when there was no campaign, using each method's own 95% interval.",
           path, source=SOURCE_IOWA, left=0.27, top=0.78)
    plt.close(fig)


if __name__ == "__main__":
    apply()
    OUT.mkdir(parents=True, exist_ok=True)
    example(OUT / "example_test.png")
    mde_chart(OUT / "min_detectable_lift.png")
    false_alarm_chart(OUT / "false_alarms.png")
    print("wrote figures/geo/example_test.png, min_detectable_lift.png, false_alarms.png")
