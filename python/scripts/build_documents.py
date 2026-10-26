"""Build report/report.pdf and presentation/deck.pdf in the Nordic style.

    py python/scripts/build_documents.py

- Report: report/report_content.md (the content pack, checked against results/ by the tests) -> styled HTML ->
  PDF. A small Markdown converter covers what the content pack uses: headings, paragraphs, lists, tables, bold,
  italics, code and [Figure N: path] markers.
- Deck: 16:9 slides built here, seven core slides on three decisions plus an appendix; every number
  comes from results/ (headline_facts.json and money.json).
- PDFs are printed by Microsoft Edge in headless mode (a background process; nothing opens on screen).
The HTML sources stay local (gitignored); only the PDFs are published.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOKENS = json.loads((ROOT / "design" / "tokens.json").read_text(encoding="utf-8"))
FACTS = json.loads((ROOT / "results" / "headline_facts.json").read_text(encoding="utf-8"))
MONEY = json.loads((ROOT / "results" / "money.json").read_text(encoding="utf-8"))
C = TOKENS["color"]
EDGE = next(p for p in [Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
                        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")] if p.exists())
AUTHOR, DATE = "Sharath Sista", "October 2026"

ROOT_CSS = f"""
:root {{
  --ink: {C['text.primary']}; --ink-2: {C['text.secondary']}; --muted: {C['text.muted']};
  --page: {C['background.secondary']}; --card: {C['background.primary']}; --border: {C['border.subtle']};
  --blue: {C['data.primary']}; --blue-strong: {C['data.primary.strong']}; --red: {C['data.highlight']};
  --red-text: {C['data.highlight.text']}; --slate: {C['sidebar.background']}; --slate-2: {C['sidebar.selected']};
  --frost: {C['sidebar.selected.text']}; --side-muted: {C['sidebar.muted']}; --selected: {C['background.selected']};
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: 'Segoe UI', Roboto, Arial, sans-serif; color: var(--ink);
        -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
.accent-bar {{ display: flex; height: 6px; }}
.accent-bar span {{ flex: 1; }}
"""
ACCENT_BAR = '<div class="accent-bar">' + "".join(f'<span style="background:{c}"></span>'
                                                  for c in C["kpi.accents"][:4]) + "</div>"


# ---------------------------------------------------------------------------------------------- markdown

def inline(text: str) -> str:
    s = html.escape(text, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*([^*]+)\*(?![*\w])", r"<em>\1</em>", s)
    return s


def md_to_html(md: str) -> str:
    """Convert the content pack's Markdown subset to HTML."""
    lines, out, i = md.strip("\n").splitlines(), [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if m := re.match(r"^(#{1,3}) (.*)", line):
            level = len(m.group(1))  # ## sections, ### subsections (the document title is the cover)
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            i += 1
        elif m := re.match(r"^\[Figure (\d+): ([^\]]+)\]$", line.strip()):
            out.append(f'<figure><img src="../{m.group(2)}" alt="Figure {m.group(1)}">'
                       f"<figcaption>Figure {m.group(1)}</figcaption></figure>")
            i += 1
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.match(r"^\|[\s:|-]+\|$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            head, *body = rows
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
                       + "</tbody></table>")
        elif re.match(r"^(- |\d+\. )", line):
            ordered = bool(re.match(r"^\d+\. ", line))
            start = int(line.split(".")[0]) if ordered else 1
            items: list[str] = []
            while i < len(lines) and (re.match(r"^(- |\d+\. )", lines[i]) or
                                      (lines[i].startswith("  ") and lines[i].strip() and items)):
                if re.match(r"^(- |\d+\. )", lines[i]):
                    items.append(re.sub(r"^(- |\d+\. )", "", lines[i]))
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            tag = "ol" if ordered else "ul"
            attr = f' start="{start}"' if ordered and start != 1 else ""
            out.append(f"<{tag}{attr}>" + "".join(f"<li>{inline(it)}</li>" for it in items) + f"</{tag}>")
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||- |\d+\. |\[Figure)", lines[i]):
                para.append(lines[i].strip())
                i += 1
            out.append(f"<p>{inline(' '.join(para))}</p>")
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------- report

REPORT_CSS = ROOT_CSS + """
@page { size: A4; margin: 18mm 18mm 20mm 18mm;
        @bottom-left { content: "Did the Ads Actually Work? · Sharath Sista"; font: 8pt 'Segoe UI'; color: #5C667A; }
        @bottom-right { content: counter(page); font: 8pt 'Segoe UI'; color: #5C667A; } }
@page :first { margin: 0; @bottom-left { content: none; } @bottom-right { content: none; } }
body { font-size: 10pt; line-height: 1.5; }
.cover { height: 297mm; background: var(--slate); color: var(--page); padding: 70mm 22mm 0; position: relative;
         break-after: page; }
.cover .kicker { color: var(--frost); font-size: 11pt; letter-spacing: 0.08em; text-transform: uppercase; }
.cover h1 { font-size: 34pt; line-height: 1.15; margin: 8mm 0 6mm; font-weight: 600; }
.cover .sub { font-size: 15pt; color: var(--side-muted); max-width: 150mm; }
.cover .author { margin-top: 18mm; font-size: 11pt; }
.cover .accent-bar { width: 60mm; margin-top: 10mm; }
.cover .note { position: absolute; bottom: 18mm; left: 22mm; right: 22mm; font-size: 8pt; color: var(--side-muted); }
h2 { font-size: 17pt; font-weight: 600; margin: 0 0 3mm; padding-top: 2mm; color: var(--ink); break-after: avoid; }
h2::after { content: ""; display: block; width: 18mm; height: 2px; background: var(--blue); margin-top: 2mm; }
h3 { font-size: 11.5pt; font-weight: 600; color: var(--blue-strong); margin: 5mm 0 1mm; break-after: avoid; }
h4 { font-size: 10.5pt; font-weight: 600; margin: 4mm 0 1mm; break-after: avoid; }
section { margin-bottom: 8mm; }
section.break { break-before: page; }
p, li { margin: 0 0 2.2mm; }
ul, ol { padding-left: 6mm; margin: 0 0 3mm; }
strong { font-weight: 600; }
code { font-family: Consolas, monospace; font-size: 8.8pt; background: var(--page); padding: 0 1mm; border-radius: 2px; }
figure { margin: 4mm 0 5mm; break-inside: avoid; }
figure img { width: 100%; max-height: 118mm; object-fit: contain; border: 1px solid var(--border); border-radius: 6px; }
figcaption { font-size: 8pt; color: var(--muted); margin-top: 1mm; }
table { width: 100%; border-collapse: collapse; font-size: 8.8pt; margin: 2mm 0 4mm; break-inside: avoid; }
th { text-align: left; font-weight: 600; color: var(--ink-2); background: var(--page); border-bottom: 1px solid var(--border);
     padding: 1.6mm 2mm; }
td { border-bottom: 1px solid var(--border); padding: 1.6mm 2mm; vertical-align: top; }
section.summary { background: var(--selected); border-radius: 8px; padding: 6mm 7mm 3mm; }
"""


def build_report() -> Path:
    md = (ROOT / "report" / "report_content.md").read_text(encoding="utf-8")
    _preamble, cover, *sections = re.split(r"\n---\n", md)
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", cover) if p.strip() and not p.strip().startswith("#")]
    title = paras[0].split("**")[1]  # **Did the Ads Actually Work?** then the subtitle on the next line
    subtitle = paras[0].split("**")[2].strip()
    note = next(p for p in paras if p.startswith("*Independent")).strip("*")
    body = []
    for n, s in enumerate(sections):
        heading = re.match(r"^## (.*)", s.strip())
        cls = ["summary"] if heading and heading.group(1).startswith("Executive summary") else []
        if heading and (heading.group(1).startswith("1. ") or heading.group(1).startswith("Appendix A")):
            cls.append("break")
        body.append(f'<section class="{" ".join(cls)}">{md_to_html(s)}</section>')
    doc = f"""<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><title>{title}</title>
<style>{REPORT_CSS}</style></head><body>
<div class="cover"><div class="kicker">Incrementality study · Portfolio project 2</div><h1>{inline(title)}</h1>
<div class="sub">{inline(subtitle)}</div>{ACCENT_BAR}<div class="author">{AUTHOR} · {DATE}</div>
<div class="note">{inline(note)}</div></div>
{''.join(body)}
</body></html>"""
    out = ROOT / "report" / "report.html"
    out.write_text(doc, encoding="utf-8")
    return out


# ---------------------------------------------------------------------------------------------- deck

DECK_CSS = ROOT_CSS + """
@page { size: 1280px 720px; margin: 0; }
.slide { width: 1280px; height: 720px; position: relative; overflow: hidden; break-after: page; background: #FFFFFF;
         padding: 52px 64px 40px; }
.slide.dark { background: var(--slate); color: var(--page); }
.kicker { font-size: 14px; color: var(--blue-strong); letter-spacing: 0.08em; text-transform: uppercase; font-weight: 600; }
.dark .kicker { color: var(--frost); }
h1 { font-size: 34px; line-height: 1.2; font-weight: 600; margin: 10px 0 0; max-width: 1120px; }
.big h1 { font-size: 54px; max-width: 980px; margin-top: 150px; }
.sub { font-size: 22px; color: var(--side-muted); margin-top: 18px; }
.accent-bar { width: 220px; margin-top: 28px; }
.foot { position: absolute; left: 64px; right: 64px; bottom: 22px; display: flex; justify-content: space-between;
        font-size: 12px; color: var(--muted); }
.dark .foot { color: var(--side-muted); }
.chart-row { display: flex; gap: 32px; margin-top: 22px; height: 540px; }
.chart-row img { width: 850px; height: 540px; object-fit: contain; object-position: top left; }
.chart-row.only img { width: 1152px; }
.side { flex: 1; padding-top: 8px; }
.side li { font-size: 19px; line-height: 1.4; margin-bottom: 18px; }
.side ul { padding-left: 22px; margin: 0; }
.side .num { font-size: 56px; font-weight: 600; color: var(--red-text); line-height: 1; }
.side .num-label { font-size: 15px; color: var(--ink-2); margin: 6px 0 22px; }
.grid4 { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; margin-top: 46px; }
.qcard { background: var(--page); border-radius: 10px; padding: 26px 30px; font-size: 26px; font-weight: 600; }
.qcard span { display: block; font-size: 15px; font-weight: 400; color: var(--ink-2); margin-top: 8px; }
.kpis { display: flex; gap: 24px; margin-top: 56px; }
.kpi { flex: 1; background: var(--page); border-radius: 10px; overflow: hidden; }
.kpi .bar { height: 6px; }
.kpi .v { font-size: 68px; font-weight: 600; padding: 22px 28px 0; }
.kpi .l { font-size: 18px; color: var(--ink-2); padding: 4px 28px 26px; }
.formula { margin-top: 40px; font-size: 26px; }
.formula b { color: var(--red-text); }
.split { margin-top: 60px; }
.split .row { display: flex; height: 70px; border-radius: 8px; overflow: hidden; font-size: 20px; font-weight: 600; }
.split .row div { display: flex; align-items: center; padding-left: 20px; }
.split .legend { font-size: 18px; color: var(--ink-2); margin-top: 14px; }
.split .exposed { margin-top: 26px; display: flex; height: 26px; width: 85%; border-radius: 6px; overflow: hidden; }
.points { margin-top: 44px; font-size: 21px; line-height: 1.5; }
.points li { margin-bottom: 14px; }
.plan { margin-top: 30px; counter-reset: n; }
.plan .item { display: flex; gap: 22px; align-items: baseline; padding: 15px 0; border-bottom: 1px solid var(--border); }
.plan .item::before { counter-increment: n; content: counter(n); font-size: 30px; font-weight: 600; color: var(--blue);
                      width: 34px; }
.plan .a { font-size: 22px; font-weight: 600; width: 520px; }
.plan .e { font-size: 17px; color: var(--ink-2); flex: 1; }
.links { margin-top: 36px; font-size: 22px; line-height: 1.8; color: var(--page); }
.grid3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 24px; margin-top: 48px; }
.dcard { background: var(--page); border-radius: 10px; padding: 28px 28px 30px; border-top: 6px solid var(--blue); }
.dcard .q { font-size: 17px; color: var(--ink-2); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
.dcard .a { font-size: 30px; font-weight: 600; margin: 14px 0 16px; line-height: 1.2; }
.dcard .e { font-size: 19px; line-height: 1.5; color: var(--ink); }
.caveats { display: flex; gap: 24px; margin-top: 30px; }
.caveats div { flex: 1; font-size: 16px; line-height: 1.45; color: var(--ink-2); border-left: 3px solid var(--border);
               padding-left: 14px; }
.caveats b { color: var(--ink); font-weight: 600; }
.nb { white-space: nowrap; }
"""


def slide(body: str, n: int, source: str = "", dark: bool = False, cls: str = "") -> str:
    classes = " ".join(c for c in ["slide", "dark" if dark else "", cls] if c)
    body = re.sub(r"([+-]£[\d.]+)", r'<span class="nb">\1</span>', body)  # keep "+£0.29" on one line
    foot = f'<div class="foot"><span>{source}</span><span>{n}</span></div>'
    return f'<div class="{classes}">{body}{foot}</div>'


def chart_slide(n: int, kicker: str, image: str, points: list[str], source: str, number: tuple[str, str] | None = None,
                ) -> str:
    side = ""
    if number:
        side += f'<div class="num">{number[0]}</div><div class="num-label">{number[1]}</div>'
    side += "<ul>" + "".join(f"<li>{p}</li>" for p in points) + "</ul>"
    return slide(f'<div class="kicker">{kicker}</div><div class="chart-row"><img src="../{image}">'
                 f'<div class="side">{side}</div></div>', n, source)


def build_deck() -> Path:
    d, f1, f2, f3, f4, f5, f6, f7, f8, f9, fs, fb = (FACTS[k] for k in [
        "data", "finding_1_experiment_health", "finding_2_naive", "finding_3_itt", "finding_4_effect_of_seeing_an_ad",
        "finding_5_credited_vs_caused", "finding_6_who_is_persuaded", "finding_7_money", "finding_8_geo",
        "finding_9_plan", "sensitivity", "budget_test"])
    be_best = f"{MONEY['break_even_attributed_roas']['30pct']['best_half']['estimate']:.1f}"
    criteo = "Source: Criteo Uplift v2.1 (Diemert et al.), CC BY-NC-SA 4.0 · levels describe the sub-sampled benchmark"
    iowa = "Source: Iowa Liquor Sales (BigQuery public data) · real sales, simulated campaigns"
    scenario = f"scenario: dashboard ROAS {f7['assumed_roas']}, margin {f7['assumed_margin']}"
    s = []
    # ---- core: seven slides on three decisions
    s.append(slide(f'<div class="kicker">Incrementality study</div><h1>Did the Ads Actually Work?</h1>'
                   f'<div class="sub">What retargeting caused in a randomised test of {d["criteo_users"]} users, '
                   f'and what to do about it</div>{ACCENT_BAR}'
                   f'<div class="sub" style="font-size:18px;margin-top:34px">{AUTHOR} · {DATE}</div>',
                   1, TOKENS["independence_note"], dark=True, cls="big"))
    decisions = [
        ("Should we trust attribution?", "Not on its own",
         f"An estimated {f5['caused_per_100']} of every 100 view-through-credited conversions were caused by the ads "
         f"({f5['caused_per_100_interval']}). Attributed ROAS overstates incremental ROAS by about "
         f"{f5['attribution_overstatement']}."),
        ("Should we move budget?", "Probably, but test first",
         f"In the {scenario}, the weaker half of spend makes {f7['other_half_profit_per_pound']} per £1. "
         "That comes from a model, so it is a hypothesis."),
        ("Which experiment next?", "A holdout in the weaker half",
         f"A 50/50 test inside that segment settles it with about {fb['users_needed']} users. Then keep an "
         "always-on holdout."),
    ]
    s.append(slide('<div class="kicker">The answer first</div><h1>Three decisions this test can inform</h1>'
                   '<div class="grid3">' + "".join(
                       f'<div class="dcard"><div class="q">{q}</div><div class="a">{a}</div><div class="e">{e}</div>'
                       f'</div>' for q, a, e in decisions) + "</div>"
                   '<div class="caveats">'
                   f'<div><b>How robust?</b> {fs["adjusted_specifications"]} adjustment methods give '
                   f'{fs["caused_per_100_adjusted_range"]} caused per 100, about as wide as the statistical interval</div>'
                   '<div><b>Money is a scenario.</b> The data has no prices; ROAS and margin are assumed and varied, and '
                   'the break-even rule needs neither</div>'
                   '<div><b>Benchmark levels.</b> Criteo sub-sampled the file; the methods carry over, the numbers must '
                   'be measured again</div></div>', 2, criteo))
    s.append(slide(f'<div class="kicker">The evidence</div><h1>A randomised test on {d["criteo_users"]} users, '
                   'checked before trusting it</h1>'
                   '<div class="split"><div class="row">'
                   f'<div style="width:85%;background:{C["data.primary"]};color:#fff">85% allowed to see ads</div>'
                   f'<div style="width:15%;background:{C["data.comparison"]}">15% blocked</div></div>'
                   f'<div class="exposed"><div style="width:4.2%;background:{C["data.highlight"]}"></div>'
                   f'<div style="flex:1;background:{C["background.selected"]}"></div></div>'
                   '<div class="legend">Only 3.6% of the allowed group actually saw an ad (red). Because the split is '
                   'random, the difference between the groups estimates what the ads caused.</div></div>'
                   f'<ul class="points"><li>A small leak from merged advertiser tests (classifier AUC '
                   f'{f1["classifier_auc"]}, placebo {f1["placebo_auc"]}), corrected by adjusting for features logged '
                   f'before any ad</li><li>{fs["adjusted_specifications"]} adjustment methods put conversion lift at '
                   f'{fs["conversion_adjusted_range"]}; the raw difference reads {f3["conversion_lift_raw"]}</li>'
                   '<li>Criteo sub-sampled the data, so levels describe this benchmark; the methods transfer</li></ul>',
                   3, criteo))
    s.append(chart_slide(4, "The evidence · Dashboard view vs the test", "figures/lift/naive_vs_caused.png", [
        f"Saw an ad vs didn't looks like {f2['naive_multiple']}",
        f"Those users were already {f2['baseline_multiple']} likelier to buy",
        f"Seeing an ad: {f2['baseline_conversion_rate']} to {f2['exposed_conversion_rate']} "
        f"({f4['conversion_effect_points']})"], criteo,
        number=(f4["causal_multiple"], "estimated causal effect of seeing an ad (CACE)")))
    s.append(chart_slide(5, "Decision 1 · Should we trust attribution?", "figures/attribution/credited_vs_caused.png", [
        f"95% interval {f5['caused_per_100_interval']}; across the adjustment methods, "
        f"{fs['caused_per_100_adjusted_range']}",
        f"Incremental ROAS = dashboard ROAS × 0.{f5['caused_per_100']}: about {f5['attribution_overstatement']} lower",
        "Assumes the leak runs through the recorded features, and that ads are the only difference between groups"],
        criteo, number=(f5["caused_per_100"], "of every 100 view-through-credited conversions were caused by the ads "
                                               "(estimated)")))
    s.append(chart_slide(6, f"Decision 2 · Should we move budget? ({scenario})", "figures/money/profit_per_pound.png", [
        f"Top 20% of users hold {f6['top20_share_of_conversion_effect']} of the effect; half the spend, aimed at "
        f"likely buyers, keeps {f6['half_spend_keeps_conversions']}",
        f"£1 looks like {f7['dashboard_profit_per_pound']} but makes an incremental "
        f"{f7['incremental_profit_per_pound']}; the weaker half makes {f7['other_half_profit_per_pound']}",
        "A hypothesis: auction prices, ad frequency and audience mix can shift once targeting changes"], criteo))
    actions = [
        ("A 50/50 holdout inside the weaker half",
         f"{fb['segment_share_of_users']} of users, half the ad views. Predicted lift {fb['predicted_lift']}; cut if "
         f"the upper bound is below the {fb['break_even_lift']} break-even. About {fb['users_needed']} users"),
        ("An always-on 10% holdout",
         f"{f9['users_for_10pct_conversion_lift_10pct_holdout']} users to see a +10% conversion lift; visits read "
         f"early with {f9['users_for_5pct_visit_lift_10pct_holdout']}"),
        ("Report incremental ROAS next to attributed ROAS",
         f"Break-even dashboard ROAS {f7['break_even_roas_30pct_margin']} at a 30% margin"),
        ("Geo tests only where holdouts are impossible",
         f"Methods benchmark: even 20 counties for 12 weeks detect only about {f8['best_design_min_detectable_lift']}"),
    ]
    s.append(slide('<div class="kicker">Decision 3 · Which experiment next?</div>'
                   '<h1>Test the cut first, then keep an always-on holdout</h1>'
                   '<div class="plan">' + "".join(f'<div class="item"><div class="a">{a}</div><div class="e">{e}</div>'
                                                  f'</div>' for a, e in actions) + "</div>", 7,
                   "And a marketing mix model for cross-channel budgets, anchored by these experiments"))
    s.append(slide('<div class="kicker">Thank you</div><h1>Code, notebooks, dashboard and report</h1>'
                   '<div class="links">github.com/sonny-888<br>linkedin.com/in/sharath-chandra-2bb604377</div>'
                   f'<div class="sub" style="font-size:18px">{AUTHOR} · Data Analyst</div>', 8, dark=True, cls="big"))
    # ---- appendix
    s.append(slide('<div class="kicker">Appendix</div><h1>The detail behind the decisions</h1>'
                   '<div class="sub">Experiment checks · sensitivity · break-even rule · targeting · geo methods '
                   'benchmark · holdout sizing · methods and limits</div>', 9, dark=True, cls="big"))
    s.append(chart_slide(10, "A1 · Experiment health", "figures/experiment/balance.png", [
        f"Split exactly {d['treated_share']} treated, as designed",
        f"No feature differs by more than {f1['max_abs_smd']} standard deviations",
        f"Yet a classifier tells the groups apart slightly: AUC {f1['classifier_auc']} (placebo {f1['placebo_auc']})",
        "Cause: several advertisers' tests merged with different treated shares"], criteo))
    s.append(chart_slide(11, "A2 · How much does the correction depend on the method?", "figures/lift/sensitivity.png", [
        f"{fs['adjusted_specifications']} adjusted specifications: conversion lift {fs['conversion_adjusted_range']}, "
        f"visits {fs['visit_adjusted_range']}",
        f"Caused per 100 credited: {fs['caused_per_100_adjusted_range']}",
        f"Weighting shrinks the largest feature gap to {fs['weighted_max_abs_smd']} standard deviations",
        "Untestable: a leak through something the file doesn't record"], criteo))
    s.append(slide('<div class="kicker">A3 · A break-even rule anyone can use</div>'
                   f'<h1>At a 30% margin, retargeting needs a dashboard ROAS above {f7["break_even_roas_30pct_margin"]} '
                   'to pay</h1><div class="kpis">'
                   + "".join(f'<div class="kpi"><div class="bar" style="background:{c}"></div><div class="v">{v}</div>'
                             f'<div class="l">{l}</div></div>' for v, l, c in [
                                 (f7["break_even_roas_30pct_margin"], "Break-even ROAS, all spend", C["kpi.accents"][0]),
                                 (be_best, "Best half of spend", C["kpi.accents"][3]),
                                 (f7["break_even_roas_other_half_30pct_margin"], "Weaker half of spend",
                                  C["kpi.accents"][1])])
                   + f'</div><div class="formula">Incremental ROAS = dashboard ROAS × <b>0.{f5["caused_per_100"]}</b>, '
                   'the caused share from a holdout. Break-even needs no ROAS assumption.</div>', 12, criteo))
    s.append(chart_slide(13, "A4 · Who is persuaded", "figures/uplift/spend_curves.png", [
        f"The top 20% of users hold {f6['top20_share_of_conversion_effect']} of the effect",
        f"Half the spend, aimed at likely buyers, keeps {f6['half_spend_keeps_conversions']} of conversions caused "
        f"({f6['half_spend_keeps_conversions_interval']})",
        "A simple likely-buyer model matched T- and X-learner uplift models on conversions"], criteo))
    s.append(chart_slide(14, "A5 · Geo methods benchmark: only big effects show", "figures/geo/min_detectable_lift.png", [
        f"{f8['simulated_tests']} simulated campaigns on real Iowa county sales, so the true answer is known",
        f"Best design (20 counties, 12 weeks) reliably detects about {f8['best_design_min_detectable_lift']}",
        "Assumes a uniform lift, random counties and no spillover: a best case",
        "More regions help faster than more weeks"], iowa))
    s.append(chart_slide(15, "A6 · Geo methods benchmark: check the method too", "figures/geo/false_alarms.png", [
        f"Difference-in-differences: {f8['did_false_alarms']} false alarms",
        f"Synthetic control: {f8['synthetic_control_false_alarms']}",
        f"CausalImpact-style: {f8['causalimpact_style_false_alarms']}, promised 5%",
        "Placebo-test any model before trusting its intervals"], iowa))
    s.append(chart_slide(16, "A7 · Sizing the always-on holdout", "figures/plan/holdout_sizing.png", [
        f"About {f9['users_for_10pct_conversion_lift_10pct_holdout']} users to see a +10% conversion lift with a 10% "
        "holdout",
        f"{f9['users_for_10pct_conversion_lift_even_split']} with a 50/50 split",
        f"Visits read early with about {f9['users_for_5pct_visit_lift_10pct_holdout']}"],
        "Base rates: Criteo control group · formula checked against the test's own precision"))
    s.append(slide('<div class="kicker">A8 · Methods and limits</div><h1>What this does and doesn&#39;t show</h1>'
                   '<ul class="points">'
                   "<li>Methods: intent-to-treat; Lin and doubly robust (AIPW, cross-fitted) adjustment; two-stage "
                   "least squares (CACE); T- and X-learner uplift on 2.8M held-out users; DiD, synthetic control, "
                   "structural time series</li>"
                   "<li>Criteo sub-sampled the file: levels describe this benchmark; the methods transfer</li>"
                   "<li>No prices or costs: money figures are scenarios, with sensitivity tables and a break-even "
                   "rule</li>"
                   "<li>Spend is proxied by ad views; real cost depends on frequency and auction prices</li>"
                   "<li>Geo results are a methods benchmark on one lumpy dataset, not a measured campaign</li></ul>",
                   17))
    doc = (f'<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><title>Did the Ads Actually Work? Deck'
           f'</title><style>{DECK_CSS}</style></head><body>{"".join(s)}</body></html>')
    out = ROOT / "presentation" / "deck.html"
    out.write_text(doc, encoding="utf-8")
    return out


def print_pdf(src: Path, dest: Path) -> None:
    subprocess.run([str(EDGE), "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--no-first-run",
                    f"--print-to-pdf={dest}", src.as_uri()], check=True, capture_output=True, timeout=180)
    print(f"wrote {dest.relative_to(ROOT)} ({dest.stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    print_pdf(build_report(), ROOT / "report" / "report.pdf")
    print_pdf(build_deck(), ROOT / "presentation" / "deck.pdf")


if __name__ == "__main__":
    main()
