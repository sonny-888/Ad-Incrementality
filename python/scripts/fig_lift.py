"""Charts for findings 2 to 4: naive view vs the ad's estimated causal effect, raw vs adjusted lift, and how much the
adjusted lift depends on the adjustment method.

    py python/scripts/fig_lift.py

Reads results/lift.json (lift_analysis.py), results/lift_aipw.json (lift_aipw.py) and results/sensitivity.json
(sensitivity_analysis.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from incrementality.style import PAL, apply, finish

ROOT = Path(__file__).resolve().parents[2]
LIFT = json.loads((ROOT / "results" / "lift.json").read_text(encoding="utf-8"))
AIPW = json.loads((ROOT / "results" / "lift_aipw.json").read_text(encoding="utf-8"))
SENS = json.loads((ROOT / "results" / "sensitivity.json").read_text(encoding="utf-8"))
OUT = ROOT / "figures" / "lift"


def pct(v: float, digits: int = 2) -> str:
    return f"{v:.{digits}%}"


def naive_vs_caused(path: Path) -> None:
    """Conversion rate of users who did and didn't see an ad, splitting the exposed rate into baseline and caused."""
    unexposed = LIFT["conversion"]["naive"]["rate_c"]
    a = AIPW["conversion"]
    exposed, baseline, caused = a["rate_exposed"], a["baseline"], a["cace"]["estimate"]
    naive_x = exposed / unexposed
    true_x = exposed / baseline

    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    rows = [1, 0]
    ax.barh(rows[0], unexposed, height=0.5, color=PAL["context"])
    ax.barh(rows[1], baseline, height=0.5, color=PAL["context"])
    ax.barh(rows[1], caused, left=baseline, height=0.5, color=PAL["accent"],
            edgecolor=PAL["surface"], linewidth=2)

    ax.text(unexposed + 0.0008, rows[0], pct(unexposed), va="center", fontsize=9, color=PAL["ink"])
    ax.text(baseline / 2, rows[1], f"Would have bought anyway\n{pct(baseline)}", ha="center", va="center",
            fontsize=8.5, color=PAL["ink"])
    ax.text(baseline + caused / 2, rows[1], f"Caused by the ad\n{pct(caused)}", ha="center", va="center",
            fontsize=8.5, color=PAL["surface"], fontweight="semibold")
    ax.text(exposed + 0.0008, rows[1], pct(exposed), va="center", fontsize=9, color=PAL["ink"])

    ax.set_yticks(rows, ["Didn't see an ad", "Saw an ad"])
    ax.set_xlim(0, exposed * 1.15)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_xlabel("Conversion rate")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    ax.set_ylim(-0.6, 1.6)
    ax.set_axisbelow(True)

    finish(fig, ax, f"Seeing an ad looks like a {naive_x:.0f}x boost. The estimated causal effect is {true_x:.1f}x",
           f"Users who saw an ad were already {baseline / unexposed:.0f}x more likely to buy. "
           "The test separates that from the ad.",
           path, left=0.17, top=0.78,
           source="Source: Criteo Uplift v2.1, 13,979,592 users. Rates describe this sub-sampled benchmark file, "
                  "not Criteo's live results.")
    plt.close(fig)


def raw_vs_adjusted(path: Path) -> None:
    """Relative intent-to-treat lift for visits and conversions: raw, linear-adjusted and AIPW, with 95% intervals."""
    fig, ax = plt.subplots(figsize=(8.5, 5))
    labels, ys, y = [], [], 0
    for outcome in ["visit", "conversion"]:
        L = LIFT[outcome]
        p_c, n_c = L["itt"]["rate_c"], L["itt"]["n_c"]
        var_pc = p_c * (1 - p_c) / n_c

        def rel_ci(est, se):
            rel = est / p_c
            se_rel = np.sqrt(se**2 / p_c**2 + est**2 * var_pc / p_c**4)
            return rel, rel - 1.959964 * se_rel, rel + 1.959964 * se_rel

        raw = (L["itt"]["rel"], L["itt"]["rel_lo"], L["itt"]["rel_hi"])
        lin = rel_ci(L["itt_adjusted"]["estimate"], L["itt_adjusted"]["se"])
        dr = rel_ci(AIPW[outcome]["itt"]["estimate"], AIPW[outcome]["itt"]["se"])
        for name, (est, lo, hi), color in [("Raw difference", raw, PAL["muted"]),
                                           ("Adjusted, linear", lin, PAL["muted"]),
                                           ("Adjusted, doubly robust", dr, PAL["primary"])]:
            ax.hlines(y, lo, hi, color=color, lw=2)
            ax.scatter(est, y, s=48, color=color, edgecolor=PAL["surface"], linewidth=1.5, zorder=3)
            ax.text(hi + 0.01, y, f"{est:+.0%}", va="center", fontsize=9,
                    color=PAL["ink"] if color == PAL["primary"] else PAL["ink_2"])
            labels.append(f"{outcome.capitalize()}s: {name.lower()}" if name == "Raw difference" else name)
            ys.append(y)
            y -= 1
        y -= 0.6

    ax.set_yticks(ys, labels)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_xlim(0, max(LIFT["conversion"]["itt"]["rel_hi"], 0.7) + 0.08)
    ax.set_xlabel("Lift for the whole treatment group vs control (relative), with 95% interval")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)

    v_raw, v_dr = LIFT["visit"]["itt"]["rel"], AIPW["visit"]["itt"]["estimate"] / LIFT["visit"]["itt"]["rate_c"]
    ax.set_axisbelow(True)
    fig.subplots_adjust(right=0.95)
    finish(fig, ax, f"Correcting for the leak cuts visit lift from {v_raw:+.0%} to {v_dr:+.0%}",
           "Treatment vs control, raw and adjusted for 12 features logged at assignment.",
           path, left=0.27, top=0.8)
    plt.close(fig)


def sensitivity(path: Path) -> None:
    """Conversion lift under every specification in results/sensitivity.json; the preferred estimate highlighted."""
    rows = [r for r in SENS["rows"] if r["outcome"] == "conversion"][::-1]
    preferred = "Doubly robust, gradient boosting"
    short = lambda spec: spec.replace("gradient boosting", "boosting").replace("logistic regression", "logistic")
    fig, ax = plt.subplots(figsize=(10, 5.4))
    for y, r in enumerate(rows):
        color = PAL["primary"] if r["specification"] == preferred else (
            PAL["context"] if r["specification"] == "Raw difference" else PAL["muted"])
        if r["lo"] is not None:
            ax.hlines(y, r["lo"], r["hi"], color=color, lw=2)
        ax.scatter(r["lift"], y, s=48, color=color, edgecolor=PAL["surface"], linewidth=1.5, zorder=3)
        ax.text((r["hi"] if r["lo"] is not None else r["lift"]) + 0.01, y, f"{r['lift']:+.0%}", va="center",
                fontsize=9, color=PAL["ink"] if r["specification"] == preferred else PAL["ink_2"])
    ax.set_yticks(range(len(rows)), [short(r["specification"]) + (" (preferred)" if r["specification"] == preferred
                                                                   else "") for r in rows])
    ss = SENS["summary"]["conversion"]
    ax.axvspan(ss["adjusted_min"], ss["adjusted_max"], color=PAL["primary"], alpha=0.08, lw=0)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_xlim(0, max(r["hi"] or r["lift"] for r in rows) + 0.1)
    ax.set_xlabel("Conversion lift for the whole treatment group vs control (relative), with 95% interval")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    ax.set_axisbelow(True)
    fig.subplots_adjust(right=0.95)
    b = SENS["balance"]
    n = len(rows) - 1
    finish(fig, ax, f"Any of {n} adjustment methods puts conversion lift at {ss['adjusted_min']:+.0%} to "
           f"{ss['adjusted_max']:+.0%}",
           f"The raw difference reads {ss['raw']:+.0%}. Weighting by the fitted chance of treatment shrinks the largest "
           f"feature gap\nfrom {b['raw_max_abs_smd']:.3f} to "
           f"{max(b['boosting_weighted_max_abs_smd'], b['logistic_weighted_max_abs_smd']):.3f} standard deviations. "
           "Outcome-only models have no interval here.",
           path, left=0.28, top=0.76)
    plt.close(fig)


if __name__ == "__main__":
    apply()
    naive_vs_caused(OUT / "naive_vs_caused.png")
    raw_vs_adjusted(OUT / "raw_vs_adjusted.png")
    sensitivity(OUT / "sensitivity.png")
    print("wrote figures/lift/naive_vs_caused.png, figures/lift/raw_vs_adjusted.png, figures/lift/sensitivity.png")
