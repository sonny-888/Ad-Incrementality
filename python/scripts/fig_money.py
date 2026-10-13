"""Chart for finding 7: profit per pound of ad spend, dashboard view vs real, best half vs other half of spend.

    py python/scripts/fig_money.py

Reads results/money.json (money_analysis.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt

from incrementality.style import PAL, apply, finish

ROOT = Path(__file__).resolve().parents[2]
M = json.loads((ROOT / "results" / "money.json").read_text(encoding="utf-8"))


def money(v: float) -> str:
    return f"{'+' if v >= 0 else '-'}£{abs(v):.2f}"


def profit_bars(path: Path) -> None:
    b, a = M["base"], M["assumptions"]
    rows = [
        ("Dashboard view", b["dashboard_profit_per_pound"], None, PAL["context"]),
        ("Real, all spend", b["real_profit_per_pound"]["estimate"], b["real_profit_per_pound"], PAL["primary"]),
        ("Real, best half", b["best_half_profit_per_pound"]["estimate"], b["best_half_profit_per_pound"], PAL["primary"]),
        ("Real, other half", b["other_half_profit_per_pound"]["estimate"], b["other_half_profit_per_pound"], PAL["accent"]),
    ]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ys = list(range(len(rows)))[::-1]
    for y, (label, v, ci, color) in zip(ys, rows):
        ax.barh(y, v, height=0.55, color=color)
        if ci:
            ax.hlines(y, ci["lo"], ci["hi"], color=PAL["ink_2"], lw=1.2)
        end = max(v, ci["hi"]) if (ci and v >= 0) else (min(v, ci["lo"]) if ci else v)
        ax.text(end + (0.04 if v >= 0 else -0.04), y, money(v), va="center", ha="left" if v >= 0 else "right",
                fontsize=10, color=PAL["accent_text"] if v < 0 else PAL["ink"], fontweight="semibold")
    ax.axvline(0, color=PAL["ink_2"], lw=0.9)
    ax.set_yticks(ys, [r[0] for r in rows])
    ax.set_xlim(-1.0, 1.8)
    ax.xaxis.set_major_formatter(lambda v, _: "£0" if abs(v) < 1e-9 else money(v).replace(".00", ""))
    ax.set_xlabel("Profit per £1 of ad spend (lines: 95% interval from the test)")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    ax.set_axisbelow(True)

    real, rest = b["real_profit_per_pound"]["estimate"], b["other_half_profit_per_pound"]["estimate"]
    finish(fig, ax, f"Each £1 of ads looks like {money(b['dashboard_profit_per_pound'])[1:]} profit. "
           f"Really it's {money(real)[1:]}, and half the spend loses money",
           f"Illustrative: assumes a dashboard ROAS of {a['attributed_roas']:.0f} and a {a['margin']:.0%} margin. "
           "Caused shares and the spend split come from the test.",
           path, left=0.15, top=0.80,
           source="Source: Criteo Uplift v2.1, 13,979,592 users; money figures use stated assumptions. "
                  "Spend measured as ad views.")
    plt.close(fig)


if __name__ == "__main__":
    apply()
    out = ROOT / "figures" / "money" / "profit_per_pound.png"
    profit_bars(out)
    print(f"wrote {out.relative_to(ROOT)}")
