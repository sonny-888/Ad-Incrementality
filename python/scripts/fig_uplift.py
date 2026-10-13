"""Chart for finding 6: uplift curves, persuadable users vs likely buyers.

    py python/scripts/fig_uplift.py

Reads results/uplift.json (uplift_analysis.py). One panel per outcome, same axes, so they compare directly.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt

from incrementality.style import PAL, apply

ROOT = Path(__file__).resolve().parents[2]
U = json.loads((ROOT / "results" / "uplift.json").read_text(encoding="utf-8"))
NAMES = {"x_learner": "Uplift model (X-learner)", "t_learner": "Uplift model (T-learner)",
         "response": "Likely buyers (response model)"}


def pts(share_diff: float) -> str:
    """A share difference as signed percentage points, without a '-0'."""
    v = round(share_diff * 100)
    return f"{v:+d}" if v else "0"


def at(outcome: str, model: str, cut: float, key: str = "capture") -> dict:
    return next(c for c in U[outcome]["models"][model][key] if abs(c["top_share"] - cut) < 1e-9)


def diff_at(outcome: str, cut: float) -> dict:
    return next(v for v in U[outcome]["vs_response"] if abs(v["top_share"] - cut) < 1e-9)


def curves(path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 5.4), sharey=True)
    for ax, outcome in zip(axes, ["visit", "conversion"]):
        b = U[outcome]
        best = b["best_model"]
        other = "t_learner" if best == "x_learner" else "x_learner"
        ax.plot([0, 1], [0, 1], color=PAL["border"], lw=1.2, ls="--")
        ax.text(0.55, 0.47, "Random targeting", fontsize=8.5, color=PAL["muted"], rotation=0)
        for model, color, lw in [(other, PAL["secondary"], 1.5), ("response", PAL["muted"], 2), (best, PAL["primary"], 2.5)]:
            c = b["models"][model]["curve"]
            ax.plot(c["x"], c["y"], color=color, lw=lw, label=NAMES[model])

        cut = 0.1
        up, resp, d = at(outcome, best, cut)["lift_share"], at(outcome, "response", cut)["lift_share"], diff_at(outcome, cut)
        significant = d["lo"] > 0 or d["hi"] < 0
        ax.vlines(cut, resp, up, color=PAL["accent"] if significant else PAL["muted"], lw=1.2)
        ax.scatter([cut], [up], s=50, color=PAL["accent"] if significant else PAL["primary"],
                   edgecolor=PAL["surface"], linewidth=1.5, zorder=4)
        ax.scatter([cut], [resp], s=40, color=PAL["muted"], edgecolor=PAL["surface"], linewidth=1.2, zorder=4)
        if significant:
            note = (f"Top 10% of users: {up:.0%} vs {resp:.0%}\n"
                    f"uplift model ahead by {pts(d['diff'])} points ({pts(d['lo'])} to {pts(d['hi'])})")
        else:
            note = f"Top 10% of users: {up:.0%} vs {resp:.0%}\nno measurable difference (signal too weak)"
        ax.text(0.17, 0.30, note, fontsize=8.5, color=PAL["accent_text"] if significant else PAL["ink_2"], va="top")
        d20 = diff_at(outcome, U["headline_top"])
        ax.text(0.17, 0.14, f"Top 20% (set in advance): {pts(d20['diff'])} points "
                f"({pts(d20['lo'])} to {pts(d20['hi'])}), level", fontsize=8.5, color=PAL["ink_2"])

        ax.set_title(f"{outcome.capitalize()}s", loc="left", fontsize=11, color=PAL["ink"], pad=8)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1.08)
        ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
        ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
        ax.set_xlabel("Share of users targeted, best first")
        ax.grid(axis="x", visible=True)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Share of the ads' total effect captured")
    handles, labels = axes[0].get_legend_handles_labels()
    order = [labels.index(NAMES[U["visit"]["best_model"]]), labels.index(NAMES["response"])]
    order += [i for i in range(len(labels)) if i not in order]
    fig.legend([handles[i] for i in order], [labels[i] for i in order], loc="lower center", ncol=3,
               bbox_to_anchor=(0.5, 0.07), fontsize=9)

    top = U["headline_top"]
    v_up = at("visit", U["visit"]["best_model"], top)["lift_share"]
    fig.subplots_adjust(top=0.78, bottom=0.26, left=0.08, right=0.97, wspace=0.08)
    x0 = axes[0].get_position().x0
    fig.text(x0, 0.95, f"A fifth of users hold {v_up:.0%} of the ads' effect, and likely buyers find them too",
             fontsize=14, fontweight="semibold", color=PAL["ink"], va="top")
    fig.text(x0, 0.885, "Share of the ads' total effect captured, users ranked best first. 2.8 million held-out users, "
             "corrected for the leak.", fontsize=10, color=PAL["ink_2"], va="top")
    fig.text(x0, 0.025, "Source: Criteo Uplift v2.1, 13,979,592 users (80% train, 20% test). "
             "Shares describe this sub-sampled benchmark file.", fontsize=8.5, color=PAL["muted"])
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


SPEND_NAMES = {"per_ad_view": "Effect per ad view (uplift / chance of seeing an ad)",
               "response": "Likely buyers (response model)", "x_learner": "Uplift model (X-learner)"}


def spend_at(outcome: str, model: str, cut: float) -> dict:
    return next(c for c in U[outcome]["models"][model]["spend_capture"] if abs(c["spend_share"] - cut) < 1e-9)


def spend_curves(path: Path, cut: float = 0.5) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 5.4), sharey=True)
    for ax, outcome in zip(axes, ["visit", "conversion"]):
        b = U[outcome]
        ax.plot([0, 1], [0, 1], color=PAL["border"], lw=1.2, ls="--")
        ax.text(0.55, 0.47, "Random targeting", fontsize=8.5, color=PAL["muted"])
        for model, color, lw in [("x_learner", PAL["muted"], 1.5), ("per_ad_view", PAL["secondary"], 1.8),
                                 ("response", PAL["primary"], 2.5)]:
            c = b["models"][model]["spend_curve"]
            ax.plot(c["x"], c["y"], color=color, lw=lw, label=SPEND_NAMES[model])

        resp = spend_at(outcome, "response", cut)
        ax.vlines(cut, 0.27, resp["lift_share"], color=PAL["accent"], lw=1, ls=":")
        ax.scatter([cut], [resp["lift_share"]], s=60, color=PAL["accent"], edgecolor=PAL["surface"], linewidth=1.5, zorder=4)
        ax.text(cut + 0.03, resp["lift_share"] - 0.04,
                f"Half the spend keeps {resp['lift_share']:.0%}\n(95% interval {resp['lo']:.0%} to {resp['hi']:.0%})",
                fontsize=9, color=PAL["accent_text"], va="top")

        notes = ["Compared with likely buyers:"]
        for m, label in [("per_ad_view", "Per ad view"), ("x_learner", "Uplift model")]:
            for v in b["spend_vs_response"][m]:
                if v["lo"] > 0 or v["hi"] < 0:
                    notes.append(f"{label}, {v['spend_share']:.0%} of spend: {pts(v['diff'])} pts "
                                 f"({pts(v['lo'])} to {pts(v['hi'])})")
        notes.append("otherwise level" if len(notes) > 1 else "no measurable difference")
        ax.text(0.42, 0.25, "\n".join(notes), fontsize=8, color=PAL["ink_2"], va="top", linespacing=1.5)

        ax.set_title(f"{outcome.capitalize()}s", loc="left", fontsize=11, color=PAL["ink"], pad=8)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1.08)
        ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
        ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
        ax.set_xlabel("Share of ad spend used (ad views), best users first")
        ax.grid(axis="x", visible=True)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Share of the ads' total effect captured")
    handles, labels = axes[0].get_legend_handles_labels()
    order = [labels.index(SPEND_NAMES[m]) for m in ["response", "per_ad_view", "x_learner"]]
    fig.legend([handles[i] for i in order], [labels[i] for i in order], loc="lower center", ncol=3,
               bbox_to_anchor=(0.5, 0.07), fontsize=9)

    pv, pc = (spend_at(o, "response", cut)["lift_share"] for o in ["visit", "conversion"])
    fig.subplots_adjust(top=0.78, bottom=0.26, left=0.08, right=0.97, wspace=0.08)
    x0 = axes[0].get_position().x0
    fig.text(x0, 0.95, f"Half the ad spend, aimed at likely buyers, keeps {pc:.0%} of the conversions ads cause",
             fontsize=14, fontweight="semibold", color=PAL["ink"], va="top")
    fig.text(x0, 0.885, f"And {pv:.0%} of the visits. Spend measured as ad views. Effect-per-ad-view ranking is "
             "exploratory (added after first results).", fontsize=10, color=PAL["ink_2"], va="top")
    fig.text(x0, 0.025, "Source: Criteo Uplift v2.1, 13,979,592 users (80% train, 20% test). "
             "Shares describe this sub-sampled benchmark file.", fontsize=8.5, color=PAL["muted"])
    fig.savefig(path, dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    apply()
    out = ROOT / "figures" / "uplift"
    curves(out / "uplift_curves.png")
    spend_curves(out / "spend_curves.png")
    print("wrote figures/uplift/uplift_curves.png, figures/uplift/spend_curves.png")
