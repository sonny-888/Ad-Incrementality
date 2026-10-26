"""Generate the Power BI project (PBIP) from code: a TMDL semantic model + a PBIR report, in the Nordic style.

Everything in the dashboard is defined here: tables, DAX measures, pages and visuals. The data is the small CSVs in
dashboard/data/ (python/scripts/export_dashboard_data.py) and every number in titles and notes comes from
results/headline_facts.json, so the dashboard can't drift from the README, report and deck.

    py dashboard/build_pbip.py              # writes dashboard/AdIncrementality.{pbip,SemanticModel,Report}
    py dashboard/build_pbip.py --validate   # also validates every report file against Microsoft's schemas

Open dashboard/AdIncrementality.pbip in Power BI Desktop, then Home > Refresh to load the data.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import uuid
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PBI_DIR = ROOT / "dashboard"
DATA = PBI_DIR / "data"
NAME = "AdIncrementality"
SM_DIR = PBI_DIR / f"{NAME}.SemanticModel"
RP_DIR = PBI_DIR / f"{NAME}.Report"
NS = uuid.UUID("2f6a3c1d-8b47-4e2a-9c0f-5d1e7b9a4c33")  # fixed namespace -> stable lineage tags across rebuilds

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
VISUAL_SCHEMA = f"{SCHEMA}/item/report/definition/visualContainer/2.7.0/schema.json"
PAGE_SCHEMA = f"{SCHEMA}/item/report/definition/page/2.0.0/schema.json"

TOKENS = json.loads((ROOT / "design" / "tokens.json").read_text(encoding="utf-8"))
FACTS = json.loads((ROOT / "results" / "headline_facts.json").read_text(encoding="utf-8"))
_T = TOKENS["color"]
PRIMARY, PRIMARY_STRONG, SECONDARY = _T["data.primary"], _T["data.primary.strong"], _T["data.secondary"]
CONTEXT, ACCENT, ACCENT_TEXT = _T["data.comparison"], _T["data.highlight"], _T["data.highlight.text"]
INK, INK_2, MUTED, BORDER = _T["text.primary"], _T["text.secondary"], _T["text.muted"], _T["border.subtle"]
HEAT_MIN, HEAT_MAX = _T["sequential.low"], _T["sequential.high"]
CARD, PAGE_BG, SELECTED = _T["background.primary"], _T["background.secondary"], _T["background.selected"]
SIDE_BG, SIDE_TEXT, SIDE_MUTED = _T["sidebar.background"], _T["sidebar.text"], _T["sidebar.muted"]
SIDE_SELECTED, SIDE_SELECTED_TEXT = _T["sidebar.selected"], _T["sidebar.selected.text"]
KPI_ACCENTS = _T["kpi.accents"]
LOSS_TINT, GAIN_TINT = "#F3DDE0", "#DCE5F0"  # light tints of the highlight red and data blue, for profit cells
HEAT_LIGHT_MAX = "#A9BDD6"  # top of the heatmap gradient: light enough that dark text stays readable
SEMIBOLD = "'''Segoe UI Semibold'', wf_segoe-ui_semibold, helvetica, arial, sans-serif'"
REGULAR = "'''Segoe UI'', wf_segoe-ui_normal, helvetica, arial, sans-serif'"

# Grid: 1440x900 canvas, 224px sidebar, content from x=240: 12 columns x 84px, 16px gutters
MARGIN, COL_W, GUTTER, SIDE_W = 240, 84, 16, 224
BAND = {"header": (16, 56), "kpi": (84, 104), "primary": (204, 296), "support": (516, 264),
        "decision": (796, 68), "footer": (872, 20)}


def gx(c: int) -> int:
    return MARGIN + c * (COL_W + GUTTER)


def gw(span: int) -> int:
    return span * COL_W + (span - 1) * GUTTER


def tag(*parts: str) -> str:
    return str(uuid.uuid5(NS, "/".join(parts)))


def q(name: str) -> str:
    """Quote a TMDL object name when needed."""
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else "'" + name.replace("'", "''") + "'"


# =====================================================================================
# SEMANTIC MODEL: one table per CSV, plus a _Measures table
# =====================================================================================

TABLES = ["kpis", "naive_vs_caused", "lift_estimates", "targeting_curves", "money_sensitivity", "break_even",
          "geo_designs", "holdout_users"]
SORT_BY = {  # text labels sorted by their number, so "12 weeks" comes after "4 weeks"
    "geo_designs": {"counties_label": "test_counties", "weeks_label": "test_weeks"},
    "holdout_users": {"target_label": "target_lift", "holdout_label": "holdout_share"},
}
FORMATS = {  # column format strings
    "kpis": {"value": "#,0.00"},
    "naive_vs_caused": {"conversion_rate": "0.00%"},
    "lift_estimates": {"lift": "+0%;-0%;0%", "lo": "+0%;-0%;0%", "hi": "+0%;-0%;0%"},
    "targeting_curves": {"x": "0%", "share_of_effect": "0%"},
    "money_sensitivity": {"margin": "0%", "dashboard_roas": "0"},
    "break_even": {"margin": "0%", "break_even_dashboard_roas": "0.0", "lo": "0.0", "hi": "0.0"},
    "geo_designs": {"false_alarm_rate": "0%", "min_detectable_lift": "0%", "typical_error": "0%"},
    "holdout_users": {"target_lift": "0%", "holdout_share": "0%", "users_millions": "0.0"},
}
PANDAS_TO_TMDL = {"object": ("string", "type text"), "str": ("string", "type text"),
                  "int64": ("int64", "Int64.Type"), "float64": ("double", "type number")}

PCT, PCT2, SIGNED_PCT = "0%", "0.00%", "+0%;-0%;0%"
GBP = "+£0.00;-£0.00;£0.00"


def kpi(name: str) -> str:
    return f'CALCULATE ( SUM ( kpis[value] ), kpis[kpi] = "{name}" )'


def spend_curve(ranking: str) -> str:
    return (f'CALCULATE ( AVERAGE ( targeting_curves[share_of_effect] ), targeting_curves[outcome] = "conversion", '
            f'targeting_curves[x_axis] = "Share of ad spend used", targeting_curves[ranking] = "{ranking}" )')


MEASURES: list[tuple[str, str, str | None, str]] = [  # (name, display folder, format string, DAX)
    # ---- headline KPIs (values from results/, via kpis.csv)
    ("Caused per 100", "KPIs", "0", kpi("Caused per 100 credited conversions")),
    ("Anyway per 100", "KPIs", "0", "100 - [Caused per 100]"),
    ("Naive Multiple", "KPIs", r"0\x", kpi("Naive effect of seeing an ad (multiple)")),
    ("Causal Multiple", "KPIs", r"0.0\x", kpi("Causal effect of seeing an ad (multiple)")),
    ("Conversion Lift Adjusted", "KPIs", SIGNED_PCT, kpi("Conversion lift, whole treated group")),
    ("Top 20 Share", "KPIs", PCT, kpi("Share of effect in top 20% of users")),
    ("Half Spend Keeps", "KPIs", PCT, kpi("Half the spend keeps (conversions caused)")),
    ("Incremental Profit per Pound", "KPIs", GBP, kpi("Incremental profit per £1 of ads")),
    ("Dashboard Profit per Pound", "KPIs", GBP, kpi("Dashboard profit per £1 of ads")),
    ("Weaker Half Profit per Pound", "KPIs", GBP, kpi("Weaker half profit per £1")),
    ("Break Even ROAS", "KPIs", "0.0", kpi("Break-even dashboard ROAS, 30% margin")),
    ("Break Even ROAS Weaker Half", "KPIs", "0.0", kpi("Break-even dashboard ROAS, weaker half")),
    ("Smallest Geo Lift", "KPIs", PCT, kpi("Smallest lift a 20-county, 12-week geo test detects")),
    ("CausalImpact False Alarms", "KPIs", PCT, kpi("CausalImpact-style false alarm rate")),
    ("DiD False Alarms", "KPIs", PCT, kpi("Difference-in-differences false alarm rate")),
    # Power BI ignores ",," thousands scaling in model format strings, so divide explicitly and show "4.9M"
    ("Holdout Users for 10pct Lift", "KPIs", r"0.0\M",
     f"DIVIDE ( {kpi('Users for a +10% conversion lift, 10% holdout')}, 1000000 )"),
    # ---- overview charts
    ("Rate Without Ad Effect", "Lift", PCT2,
     'CALCULATE ( SUM ( naive_vs_caused[conversion_rate] ), naive_vs_caused[component] <> "Caused by the ad" )'),
    ("Rate Caused by Ad", "Lift", PCT2,
     'CALCULATE ( SUM ( naive_vs_caused[conversion_rate] ), naive_vs_caused[component] = "Caused by the ad" )'),
    ("Conversion Lift", "Lift", SIGNED_PCT,
     'CALCULATE ( SUM ( lift_estimates[lift] ), lift_estimates[outcome] = "conversion" )'),
    ("Lift Bar Color", "Formatting", None,
     f'IF ( SELECTEDVALUE ( lift_estimates[estimate] ) = "Adjusted, doubly robust", "{PRIMARY}", "{CONTEXT}" )'),
    # ---- targeting and money
    ("Captured Likely Buyers", "Targeting", PCT, spend_curve("Likely buyers")),
    ("Captured Uplift Model", "Targeting", PCT, spend_curve("Uplift model (X-learner)")),
    ("Captured Per Ad View", "Targeting", PCT, spend_curve("Effect per ad view")),
    ("Random Targeting", "Targeting", PCT,
     "IF ( NOT ISBLANK ( [Captured Likely Buyers] ), AVERAGE ( targeting_curves[x] ) )"),
    ("Profit All Spend", "Money", GBP, "AVERAGE ( money_sensitivity[profit_per_pound_all_spend] )"),
    ("Profit Weaker Half", "Money", GBP, "AVERAGE ( money_sensitivity[profit_per_pound_other_half] )"),
    ("Break Even ROAS Cell", "Money", "0.0", "AVERAGE ( break_even[break_even_dashboard_roas] )"),
    ("Profit All Spend Color", "Formatting", None, f'IF ( [Profit All Spend] < 0, "{LOSS_TINT}", "{GAIN_TINT}" )'),
    ("Profit Weaker Half Color", "Formatting", None, f'IF ( [Profit Weaker Half] < 0, "{LOSS_TINT}", "{GAIN_TINT}" )'),
    # ---- how to measure
    ("False Alarm Rate", "Measurement", PCT, "AVERAGE ( geo_designs[false_alarm_rate] )"),
    ("Method Color", "Formatting", None,
     f'IF ( SELECTEDVALUE ( geo_designs[method] ) = "CausalImpact-style", "{ACCENT}", "{PRIMARY}" )'),
    ("Smallest Lift DiD", "Measurement", PCT,
     'CALCULATE ( AVERAGE ( geo_designs[min_detectable_lift] ), geo_designs[method] = "Difference-in-differences" )'),
    ("Users Needed", "Measurement", r"0.0\M",
     'CALCULATE ( SUM ( holdout_users[users_millions] ), holdout_users[outcome] = "conversion" )'),
]


def csv_columns(table: str) -> list[tuple[str, str, str]]:
    """(column, TMDL type, M type) inferred from the CSV, so the model always matches the exported data."""
    df = pd.read_csv(DATA / f"{table}.csv")
    return [(c, *PANDAS_TO_TMDL[str(df[c].dtype)]) for c in df.columns]


def m_source(lines: list[str]) -> list[str]:
    return ["\t\tsource ="] + [f"\t\t\t\t{line}" for line in lines]


def table_tmdl(name: str) -> str:
    cols = csv_columns(name)
    out = [f"table {q(name)}", f"\tlineageTag: {tag('table', name)}", ""]
    for c, dtype, _ in cols:
        out += [f"\tcolumn {q(c)}", f"\t\tdataType: {dtype}"]
        fmt = FORMATS.get(name, {}).get(c) or {"int64": "0", "double": "#,0.00"}.get(dtype)
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out += [f"\t\tlineageTag: {tag('column', name, c)}", "\t\tsummarizeBy: none", f"\t\tsourceColumn: {c}"]
        if c in SORT_BY.get(name, {}):
            out.append(f"\t\tsortByColumn: {q(SORT_BY[name][c])}")
        out += ["", "\t\tannotation SummarizationSetBy = Automatic", ""]
    types = ", ".join(f'{{"{c}", {mtype}}}' for c, _, mtype in cols)
    out += [f"\tpartition {q(name)} = m", "\t\tmode: import"]
    out += m_source(["let",
                     f'    Source = Csv.Document(File.Contents(DataFolder & "{name}.csv"), '
                     '[Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
                     "    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
                     f'    Typed = Table.TransformColumnTypes(Promoted, {{{types}}}, "en-US")',
                     "in",
                     "    Typed"])
    out += ["", "\tannotation PBI_ResultType = Table", ""]
    return "\n".join(out)


def measures_table_tmdl() -> str:
    out = ["table _Measures", f"\tlineageTag: {tag('table', '_Measures')}", ""]
    for name, folder, fmt, dax in MEASURES:
        out.append(f"\tmeasure {q(name)} = {dax.strip()}")
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out += [f"\t\tdisplayFolder: {folder}", f"\t\tlineageTag: {tag('measure', name)}", ""]
    out += ["\tcolumn Placeholder", "\t\tdataType: string", "\t\tisHidden",
            f"\t\tlineageTag: {tag('column', '_Measures', 'Placeholder')}", "\t\tsummarizeBy: none",
            "\t\tsourceColumn: Placeholder", "", "\t\tannotation SummarizationSetBy = Automatic", "",
            "\tpartition _Measures = m", "\t\tmode: import"]
    out += m_source(["let", "    Source = #table(type table [Placeholder = text], {})", "in", "    Source"])
    out += ["", "\tannotation PBI_ResultType = Table", ""]
    return "\n".join(out)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, obj) -> None:
    write(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def build_semantic_model() -> None:
    d = SM_DIR / "definition"
    write_json(SM_DIR / "definition.pbism", {
        "$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2", "settings": {}})
    write(d / "database.tmdl", f"database {NAME}\n\tcompatibilityLevel: 1600\n")
    all_tables = ["_Measures", *TABLES]
    write(d / "model.tmdl", "\n".join([
        "model Model", "\tculture: en-GB", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tdiscourageImplicitMeasures", "\tsourceQueryCulture: en-GB", "\tdataAccessOptions",
        "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull", "",
        "annotation __PBI_TimeIntelligenceEnabled = 0", "",
        "annotation PBI_QueryOrder = " + json.dumps(["DataFolder", *all_tables]), "",
        *[f"ref table {q(t)}" for t in all_tables], ""]))
    write(d / "expressions.tmdl", "\n".join([
        f'expression DataFolder = "{DATA}\\" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
        f"\tlineageTag: {tag('expression', 'DataFolder')}", "", "\tannotation PBI_ResultType = Text", ""]))
    write(d / "tables" / "_Measures.tmdl", measures_table_tmdl())
    for t in TABLES:
        write(d / "tables" / f"{t}.tmdl", table_tmdl(t))


def write_measures_reference() -> None:
    out = ["// Generated by dashboard/build_pbip.py; edit the MEASURES list there, not this file.", ""]
    folder = None
    for name, fld, fmt, dax in MEASURES:
        if fld != folder:
            out += ["", f"// ---------------------------------------------------------------- {fld.upper()}", ""]
            folder = fld
        out += [f"[{name}] =\n{dax.strip()}", f"// Format: {fmt or 'text'}\n"]
    write(PBI_DIR / "measures.dax", "\n".join(out))


# =====================================================================================
# REPORT: visual building blocks (same conventions as Project 1)
# =====================================================================================

def lit(v) -> dict:
    if isinstance(v, bool):
        return {"expr": {"Literal": {"Value": "true" if v else "false"}}}
    if isinstance(v, (int, float)):
        return {"expr": {"Literal": {"Value": f"{v}D"}}}
    return {"expr": {"Literal": {"Value": "'" + str(v).replace("'", "''") + "'"}}}


def raw(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def solid(hex_color: str) -> dict:
    return {"solid": {"color": lit(hex_color)}}


def measure_color(measure: str) -> dict:
    return {"solid": {"color": {"expr": mea(measure)}}}


def col(entity: str, prop: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def mea(prop: str) -> dict:
    return {"Measure": {"Expression": {"SourceRef": {"Entity": "_Measures"}}, "Property": prop}}


def ref(field: dict) -> tuple[str, str]:
    kind = next(iter(field))
    return field[kind]["Expression"]["SourceRef"]["Entity"], field[kind]["Property"]


def named(field: dict, label: str) -> dict:
    return {**field, "_display": label}


def proj(field: dict, active: bool = False) -> dict:
    field = dict(field)
    display = field.pop("_display", None)
    entity, prop = ref(field)
    p = {"field": field, "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}
    if display:
        p["displayName"] = display
    if active:
        p["active"] = True
    return p


def props(**kw) -> list[dict]:
    return [{"properties": {k: (v if isinstance(v, dict) else lit(v)) for k, v in kw.items()}}]


def all_points(properties: dict) -> dict:
    return {"properties": properties, "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}}


def series_fill(colors: dict[str, str]) -> list[dict]:
    return [{"properties": {"fill": solid(c)}, "selector": {"metadata": f"_Measures.{m}"}} for m, c in colors.items()]


def gradient(measure: str, lo: str = HEAT_MIN, hi: str = HEAT_MAX) -> dict:
    return {"properties": {"backColor": {"solid": {"color": {"expr": {"FillRule": {
        "Input": mea(measure),
        "FillRule": {"linearGradient2": {
            "min": {"color": {"Literal": {"Value": f"'{lo}'"}}},
            "max": {"color": {"Literal": {"Value": f"'{hi}'"}}},
            "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'noColor'"}}}}}}}}}}},
        "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": f"_Measures.{measure}"}}


def cell_color(measure: str, color_measure: str) -> dict:
    """Matrix cell background from a measure that returns a hex code."""
    return {"properties": {"backColor": measure_color(color_measure)},
            "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": f"_Measures.{measure}"}}


def axes(value_axis: bool = True, inner_padding: int | None = None, scalar: bool = False,
         max_margin: int | None = None) -> dict:
    """Quiet axes: no titles, 8pt muted labels, dotted value gridlines only."""
    cat = {"showAxisTitle": False, "labelColor": solid(MUTED), "fontSize": 8, "gridlineShow": False}
    if inner_padding is not None:
        cat["innerPadding"] = inner_padding
    if scalar:
        cat["axisType"] = "Scalar"
    if max_margin is not None:  # % of the visual the category labels may take, so long labels aren't cut
        cat["maxMarginFactor"] = max_margin
    val = {"show": value_axis, "showAxisTitle": False, "labelColor": solid(MUTED), "fontSize": 8,
           "gridlineShow": True, "gridlineColor": solid(BORDER), "gridlineThickness": 1, "gridlineStyle": "dotted"}
    return {"categoryAxis": props(**cat), "valueAxis": props(**val)}


def labels(show: bool = True, precision: int | None = None) -> dict:
    p = {"show": show, "fontSize": 8, "color": solid(INK_2), "labelDisplayUnits": 1}
    if precision is not None:
        p["labelPrecision"] = precision
    return {"labels": props(**p)}


def legend(show: bool = True) -> dict:
    return {"legend": props(show=show, position="Top", fontSize=8, labelColor=solid(INK_2), showTitle=False)}


def table_style(font_size: int = 9, padding: int = 4) -> dict:
    return {
        "grid": props(gridVertical=False, gridHorizontal=True, gridHorizontalColor=solid(BORDER), rowPadding=padding),
        "columnHeaders": props(fontColor=solid(INK_2), fontSize=font_size, fontFamily=raw(SEMIBOLD),
                               backColor=solid(CARD), wordWrap=True, autoSizeColumnWidth=True),
        "rowHeaders": props(fontColor=solid(INK), fontSize=font_size),
        "values": [{"properties": {"fontColor": solid(INK), "fontSize": lit(font_size), "wordWrap": lit(True),
                                   "backColorPrimary": solid(CARD), "backColorSecondary": solid(CARD)}}],
        "total": props(totals=False),
    }


def text_run(value: str, size: int, color: str, bold: bool = False) -> dict:
    return {"value": value, "textStyle": {
        "fontSize": f"{size}pt", "color": color,
        "fontFamily": "'Segoe UI Semibold', wf_segoe-ui_semibold, helvetica, arial, sans-serif" if bold
        else "'Segoe UI', wf_segoe-ui_normal, helvetica, arial, sans-serif"}}


def transparent() -> dict:
    return {"background": props(show=False), "border": props(show=False), "title": props(show=False),
            "dropShadow": props(show=False), "padding": props(top=0, bottom=0, left=0, right=0)}


def paragraphs(*runs: tuple) -> dict:
    """Textbox content: each item is (text, size, colour[, bold])."""
    return {"general": [{"properties": {"paragraphs": [{"textRuns": [text_run(*r)]} for r in runs]}}]}


NAV = [("overview", "Overview"), ("targeting", "Targeting & money"), ("measure", "How to measure")]


def nav_button(label: str, here: bool) -> dict:
    default = {"selector": {"id": "default"}}
    return {
        "text": [{"properties": {"show": lit(True)}},
                 {"properties": {"text": lit(label), "fontSize": lit(10), "horizontalAlignment": lit("left"),
                                 "leftMargin": lit(12), "fontColor": solid(SIDE_SELECTED_TEXT if here else SIDE_MUTED),
                                 "fontFamily": raw(SEMIBOLD if here else REGULAR)}, **default}],
        "icon": [{"properties": {"show": lit(False)}}],
        "fill": [{"properties": {"show": lit(here)}},
                 {"properties": {"fillColor": solid(SIDE_SELECTED), "transparency": lit(0)}, **default}],
        "outline": [{"properties": {"show": lit(False)}}],
        "shape": [{"properties": {"tileShape": lit("rectangleRounded"), "roundEdge": lit(18)}}],
    }


class Page:
    def __init__(self, name: str, display: str, title: str, headline: str, meta: str):
        self.name, self.display, self.width, self.height = name, display, 1440, 900
        self.visuals: list[dict] = []
        self.sidebar()
        self.header(title, headline, meta)

    def add(self, name: str, vtype: str, x, y, w, h, roles: dict | None = None, sort: list | None = None,
            title: str | None = None, subtitle: str | None = None, alt: str | None = None,
            objects: dict | None = None, container: dict | None = None) -> None:
        visual: dict = {"visualType": vtype}
        if roles:
            query: dict = {"queryState": {
                role: {"projections": [proj(f, active=(role in ("Category", "Rows") and i == 0))
                                       for i, f in enumerate(fields)]}
                for role, fields in roles.items()}}
            if sort:
                query["sortDefinition"] = {"sort": [{"field": f, "direction": d} for f, d in sort],
                                           "isDefaultSort": True}
            visual["query"] = query
        if objects:
            visual["objects"] = objects
        vco = dict(container or {})
        if title:
            vco["title"] = props(show=True, text=title)
        if subtitle:
            vco["subTitle"] = props(show=True, text=subtitle)
        if alt:
            vco["general"] = props(altText=alt)
        if vco:
            visual["visualContainerObjects"] = vco
        visual["drillFilterOtherVisuals"] = True
        self.visuals.append({"$schema": VISUAL_SCHEMA, "name": name,
                             "position": {"x": x, "y": y, "z": len(self.visuals) * 100, "height": h, "width": w,
                                          "tabOrder": len(self.visuals) * 100},
                             "visual": visual})

    def text(self, name: str, x, y, w, h, *runs: tuple, container: dict | None = None) -> None:
        self.add(name, "textbox", x, y, w, h, objects=paragraphs(*runs), container=container or transparent())

    def sidebar(self) -> None:
        """Slate sidebar: product name, page buttons, independence note (items on the panel end in _ovl)."""
        self.add(f"{self.name}_side", "textbox", 0, 0, SIDE_W, self.height,
                 objects=paragraphs(("Did the Ads", 16, SIDE_TEXT, True), ("Actually Work?", 16, SIDE_MUTED, True)),
                 container={"background": props(show=True, color=solid(SIDE_BG)), "border": props(show=False, radius=0),
                            "padding": props(top=24, bottom=0, left=20, right=20)})
        self.text(f"{self.name}_nav_label_ovl", 16, 104, SIDE_W - 32, 24, ("Pages", 9, SIDE_MUTED, True))
        for i, (page_name, label) in enumerate(NAV):
            self.add(f"{self.name}_nav_{page_name}_ovl", "actionButton", 16, 132 + i * 44, SIDE_W - 32, 36,
                     objects=nav_button(label, page_name == self.name),
                     container={"background": props(show=False), "border": props(show=False),
                                "padding": props(top=0, bottom=0, left=0, right=0),
                                "visualLink": props(show=True, type="PageNavigation", navigationSection=page_name,
                                                    tooltip=f"Go to {label}")},
                     alt=f"Go to the {label} page")
        self.text(f"{self.name}_note_ovl", 16, self.height - 156, SIDE_W - 32, 140,
                  ("Red marks the one thing to look at; blue carries the data.", 8, SIDE_MUTED),
                  (" ", 4, SIDE_MUTED), (TOKENS["independence_note"], 8, SIDE_MUTED))

    def header(self, title: str, headline: str, meta: str) -> None:
        y, h = BAND["header"]
        self.text(f"{self.name}_header", gx(0), y, gw(9), h, (title, 20, INK, True), (headline, 11, INK_2))
        self.add(f"{self.name}_meta", "textbox", gx(9), y, gw(3), h, objects={"general": [{"properties": {
            "paragraphs": [{"textRuns": [text_run(meta, 8, MUTED)], "horizontalTextAlignment": "right"}]}}]},
            container={**transparent(), "padding": props(top=8, bottom=0, left=0, right=0)})

    def kpi_band(self, items: list[tuple[str, str, str, str]]) -> None:
        """(label, measure, context line, value colour): a card with a thin colour bar, value and context."""
        y, h = BAND["kpi"]
        card_w = (gw(12) - GUTTER * (len(items) - 1)) // len(items)
        for i, (label, measure, context, color) in enumerate(items):
            cx, key = gx(0) + i * (card_w + GUTTER), f"{self.name}_kpi{i}"
            self.text(f"{key}_card", cx, y, card_w, h, (" ", 6, INK), container={"title": props(show=False)})
            self.add(f"{key}_bar_ovl", "textbox", cx, y, card_w, 4, objects=paragraphs((" ", 1, INK)),
                     container={"background": props(show=True, color=solid(KPI_ACCENTS[i % len(KPI_ACCENTS)])),
                                "border": props(show=False, radius=0), "title": props(show=False),
                                "padding": props(top=0, bottom=0, left=0, right=0)})
            self.add(f"{key}_value_ovl", "card", cx, y + 6, card_w, 64, roles={"Values": [mea(measure)]},
                     objects={"labels": props(fontSize=26, color=solid(color), fontFamily=raw(REGULAR),
                                              labelDisplayUnits=1),
                              "categoryLabels": props(show=False)},
                     container={"background": props(show=False), "border": props(show=False),
                                "title": props(show=True, text=label, fontSize=9, fontColor=solid(INK_2),
                                               fontFamily=raw(REGULAR), alignment="left"),
                                "padding": props(top=8, bottom=0, left=16, right=8)},
                     alt=f"{label} KPI")
            self.add(f"{key}_context_ovl", "textbox", cx, y + 70, card_w, 28, objects=paragraphs((context, 8, MUTED)),
                     container={**transparent(), "padding": props(top=0, bottom=0, left=16, right=8)})

    def note(self, name: str, c: int, span: int, band: str, title: str, lines: list[str]) -> None:
        y, h = BAND[band]
        runs = [(title, 11, INK, True), (" ", 4, INK)] + [(line, 9, INK if line.startswith("→") else INK_2)
                                                           for line in lines]
        self.text(name, gx(c), y, gw(span), h, *runs, container={"padding": props(top=16, bottom=16, left=16, right=16)})

    def decision_strip(self, items: list[tuple[str, str]]) -> None:
        y, h = BAND["decision"]
        for i, (heading, body) in enumerate(items):
            self.text(f"{self.name}_decision{i}", gx(i * 3), y, gw(3), h, (heading.upper(), 7, PRIMARY_STRONG, True),
                      (body, 8, INK), container={"background": props(show=True, color=solid(SELECTED)),
                                                 "border": props(show=False, radius=8),
                                                 "padding": props(top=6, bottom=4, left=12, right=12)})

    def footer(self, text: str) -> None:
        y, h = BAND["footer"]
        self.text(f"{self.name}_footer", gx(0), y, gw(12), h, (text, 8, MUTED))


# =====================================================================================
# PAGES (numbers in text come from results/headline_facts.json)
# =====================================================================================

F = FACTS
F2, F3, F4, F5 = (F[k] for k in ["finding_2_naive", "finding_3_itt", "finding_4_effect_of_seeing_an_ad",
                                  "finding_5_credited_vs_caused"])
F6, F7, F8, F9 = (F[k] for k in ["finding_6_who_is_persuaded", "finding_7_money", "finding_8_geo", "finding_9_plan"])
FS, FB = F["sensitivity"], F["budget_test"]
KPI_NOTES = pd.read_csv(DATA / "kpis.csv").set_index("kpi")["note"].to_dict()
CRITEO = (f"Criteo Uplift v2.1 (CC BY-NC-SA 4.0) · randomised test, {F['data']['criteo_users']} users · "
          "levels describe Criteo's sub-sampled benchmark file")


def page_overview() -> Page:
    p = Page("overview", "Overview", "Did the ads actually work?",
             f"An estimated {F5['caused_per_100']} of every 100 conversions credited to retargeting "
             "(view-through) were caused by it.",
             f"Randomised test · {F['data']['criteo_users']} users · adjusted for a small leak")
    p.kpi_band([
        ("Caused per 100 credited (estimated)", "Caused per 100", KPI_NOTES["Caused per 100 credited conversions"],
         ACCENT_TEXT),
        ("Seeing an ad: dashboard view", "Naive Multiple", "Saw an ad vs didn't, as a dashboard shows", INK),
        ("Seeing an ad: estimated causal effect", "Causal Multiple", "From the randomised test (CACE)", INK),
        ("Conversion lift, whole treated group", "Conversion Lift Adjusted",
         KPI_NOTES["Conversion lift, whole treated group"], INK),
    ])
    y, h = BAND["primary"]
    p.add("overview_naive", "barChart", gx(0), y, gw(7), h,
          roles={"Category": [named(col("naive_vs_caused", "group"), "Group")],
                 "Y": [named(mea("Rate Without Ad Effect"), "Would have bought anyway"),
                       named(mea("Rate Caused by Ad"), "Caused by the ad")]},
          objects={**axes(value_axis=False, inner_padding=40), **labels(precision=2), **legend(),
                   "dataPoint": series_fill({"Rate Without Ad Effect": CONTEXT, "Rate Caused by Ad": ACCENT})},
          title=f"Seeing an ad looks like a {F2['naive_multiple']} boost. The estimated causal effect is "
                f"{F4['causal_multiple']}",
          subtitle=f"Conversion rate · users who saw an ad were already {F2['baseline_multiple']} likelier to buy; "
                   "the test separates that from the ad",
          alt=f"Stacked bar: didn't see an ad {F2['unexposed_conversion_rate']}; saw an ad "
              f"{F2['exposed_conversion_rate']}, of which {F2['baseline_conversion_rate']} would have happened anyway.")
    p.add("overview_lift", "clusteredBarChart", gx(7), y, gw(5), h,
          roles={"Category": [named(col("lift_estimates", "estimate"), "Estimate")],
                 "Y": [named(mea("Conversion Lift"), "Conversion lift")]},
          objects={**axes(value_axis=False, inner_padding=40, max_margin=45), **labels(), **legend(show=False),
                   "dataPoint": [all_points({"fill": measure_color("Lift Bar Color")})]},
          title=f"Correcting the leak: conversion lift {F3['conversion_lift_raw']} raw, "
                f"{F3['conversion_lift_adjusted']} adjusted",
          subtitle=f"Whole treatment group vs control · preferred: adjusted for pre-treatment features; "
                   f"{FS['adjusted_specifications']} adjusted specifications give {FS['conversion_adjusted_range']}",
          alt="Bar chart of conversion lift: raw difference, linear adjustment, doubly robust adjustment.")
    y, h = BAND["support"]
    p.add("overview_credited", "donutChart", gx(0), y, gw(5), h,
          roles={"Y": [named(mea("Caused per 100"), "Caused by the ad"),
                       named(mea("Anyway per 100"), "Would have happened anyway")]},
          objects={"legend": props(show=True, position="Bottom", fontSize=8, labelColor=solid(INK_2), showTitle=False),
                   "labels": props(show=True, labelStyle="Data value", color=solid(INK_2), fontSize=9),
                   "slices": props(innerRadiusRatio=65),
                   "dataPoint": series_fill({"Caused per 100": ACCENT, "Anyway per 100": CONTEXT})},
          title=f"Ads caused an estimated {F5['caused_per_100']} of 100 credited conversions",
          subtitle=f"View-through credit · 95% interval {F5['caused_per_100_interval']}; {FS['caused_per_100_adjusted_range']}"
                   f" across adjustment methods · attribution overstates return about "
                   f"{F5['attribution_overstatement']}",
          alt="Donut: of 100 conversions credited to ads, 54 caused by them and 46 that would have happened anyway.")
    p.note("overview_read", 5, 7, "support", "How to read this page", [
        "Criteo randomly blocked ads for 15% of users. Any difference between the groups was caused by the ads.",
        f"Users who saw an ad converted at {F2['exposed_conversion_rate']}; without it they'd have converted at "
        f"about {F2['baseline_conversion_rate']}. So ads work, but far less than a dashboard suggests.",
        "The test had a small leftover imbalance from merging several advertisers' tests. Headline numbers are "
        "adjusted for it, assuming the 12 pre-treatment features capture it; raw figures are shown for comparison.",
        "Estimates describe this benchmark file (Criteo sub-sampled it), not every retargeting campaign.",
        "→ Judge retargeting on what it causes: incremental ROAS = dashboard ROAS × caused share.",
    ])
    p.decision_strip([
        ("Finding", f"An estimated {F5['caused_per_100']} of every 100 credited conversions were caused by the ads."),
        ("Evidence", f"Seeing an ad lifts conversion from {F2['baseline_conversion_rate']} to "
                     f"{F2['exposed_conversion_rate']}: {F4['causal_multiple']}, not {F2['naive_multiple']}."),
        ("Interpretation", f"Attribution credits ads with keen shoppers' sales; return is overstated about "
                           f"{F5['attribution_overstatement']}."),
        ("Next action", "Report incremental ROAS next to attributed ROAS in every campaign review."),
    ])
    p.footer("Source: " + CRITEO)
    return p


def page_targeting() -> Page:
    p = Page("targeting", "Targeting & money", "Who to target, and does it pay?",
             f"Half the spend, aimed at likely buyers, keeps {F6['half_spend_keeps_conversions']} of caused "
             "conversions; in the scenario, the weaker half loses money.",
             "2.8M held-out users · money is scenario analysis (ROAS 8, margin 30%)")
    p.kpi_band([
        ("Effect in the top 20% of users", "Top 20 Share", "Of the ads' effect on conversions", INK),
        ("Half the spend keeps", "Half Spend Keeps", KPI_NOTES["Half the spend keeps (conversions caused)"], INK),
        ("Incremental profit per £1 (scenario)", "Incremental Profit per Pound", KPI_NOTES["Incremental profit per £1 of ads"], INK),
        ("Weaker half: profit per £1 (scenario)", "Weaker Half Profit per Pound",
         "The half of spend on the least likely buyers", ACCENT_TEXT),
    ])
    y, h = BAND["primary"]
    p.add("targeting_curves", "lineChart", gx(0), y, gw(7), h,
          roles={"Category": [named(col("targeting_curves", "x"), "Share of ad spend used")],
                 "Y": [named(mea("Captured Likely Buyers"), "Likely buyers"),
                       named(mea("Captured Uplift Model"), "Uplift model"),
                       named(mea("Captured Per Ad View"), "Effect per ad view"),
                       named(mea("Random Targeting"), "Random")]},
          sort=[(col("targeting_curves", "x"), "Ascending")],
          objects={**axes(scalar=True), **labels(show=False), **legend(),
                   "lineStyles": [{"properties": {"strokeWidth": lit(2), "showMarker": lit(False)}},
                                  {"properties": {"lineStyle": lit("dashed"), "strokeWidth": lit(1)},
                                   "selector": {"metadata": "_Measures.Random Targeting"}}],
                   "dataPoint": series_fill({"Captured Likely Buyers": PRIMARY, "Captured Uplift Model": MUTED,
                                             "Captured Per Ad View": SECONDARY, "Random Targeting": CONTEXT})},
          title=f"Half the ad spend, aimed at likely buyers, keeps {F6['half_spend_keeps_conversions']} of the "
                "conversions ads cause",
          subtitle="Share of the ads' effect on conversions captured vs share of spend (ad views) used, best users first",
          alt="Line chart of effect captured against share of spend for three rankings and random targeting.")
    p.add("targeting_profit", "pivotTable", gx(7), y, gw(5), h,
          roles={"Rows": [named(col("money_sensitivity", "dashboard_roas"), "Dashboard ROAS")],
                 "Columns": [named(col("money_sensitivity", "margin"), "Margin")],
                 "Values": [named(mea("Profit All Spend"), "Profit per £1")]},
          sort=[(col("money_sensitivity", "dashboard_roas"), "Ascending")],
          objects={**table_style(), "values": table_style()["values"] + [cell_color("Profit All Spend",
                                                                                   "Profit All Spend Color")],
                   "subTotals": props(columnSubtotals=False, rowSubtotals=False)},
          title="Scenario: incremental profit per £1 of ads, all spend",
          subtitle="By assumed dashboard ROAS (rows) and margin (columns) · red = loss",
          alt="Matrix of incremental profit per pound (scenario) by dashboard ROAS and margin.")
    y, h = BAND["support"]
    p.add("targeting_weaker", "pivotTable", gx(0), y, gw(7), h,
          roles={"Rows": [named(col("money_sensitivity", "dashboard_roas"), "Dashboard ROAS")],
                 "Columns": [named(col("money_sensitivity", "margin"), "Margin")],
                 "Values": [named(mea("Profit Weaker Half"), "Profit per £1")]},
          sort=[(col("money_sensitivity", "dashboard_roas"), "Ascending")],
          objects={**table_style(padding=2),
                   "values": table_style()["values"] + [cell_color("Profit Weaker Half", "Profit Weaker Half Color")],
                   "subTotals": props(columnSubtotals=False, rowSubtotals=False)},
          title="The weaker half of spend loses money in 21 of 24 combinations",
          subtitle="Scenario: incremental profit per £1 on the half of spend aimed at the least likely buyers · "
                   "red = loss",
          alt="Matrix of profit per pound for the weaker half of spend by dashboard ROAS and margin.")
    p.add("targeting_breakeven", "pivotTable", gx(7), y, gw(5), h,
          roles={"Rows": [named(col("break_even", "margin"), "Margin")],
                 "Columns": [named(col("break_even", "spend"), "Spend")],
                 "Values": [named(mea("Break Even ROAS Cell"), "Break-even ROAS")]},
          sort=[(col("break_even", "margin"), "Ascending")],
          objects={**table_style(font_size=10, padding=3),  # four rows must fit the support band without scrolling
                   "subTotals": props(columnSubtotals=False, rowSubtotals=False)},
          title=f"Break-even dashboard ROAS: {F7['break_even_roas_30pct_margin']} at a 30% margin",
          subtitle=f"The weaker half needs {F7['break_even_roas_other_half_30pct_margin']} · no ROAS assumption needed",
          alt="Table of break-even dashboard ROAS by margin for all spend, the best half and the other half.")
    p.decision_strip([
        ("Finding", f"A fifth of users hold {F6['top20_share_of_conversion_effect']} of the effect; half the spend "
                    f"keeps {F6['half_spend_keeps_conversions']}."),
        ("Evidence", "Uplift models graded on 2.8M held-out users by spend; a simple likely-buyer model matched them."),
        ("Interpretation", f"In the scenario the weaker half makes {F7['other_half_profit_per_pound']} per £1; "
                           "a hypothesis, not a proven saving."),
        ("Next action", f"Test it: a 50/50 holdout in that segment needs about {FB['users_needed']} users."),
    ])
    p.footer("Source: " + CRITEO + " · money uses stated assumptions · spend measured as ad views")
    return p


def page_measure() -> Page:
    p = Page("measure", "How to measure", "How to measure it next time",
             "User-level holdouts see small effects; geo tests on noisy sales only catch big ones.",
             f"Geo: methods benchmark, {F8['simulated_tests']} simulated campaigns on real Iowa sales")
    p.kpi_band([
        ("Users for a +10% conversion lift", "Holdout Users for 10pct Lift",
         KPI_NOTES["Users for a +10% conversion lift, 10% holdout"], INK),
        ("Smallest lift a geo test catches", "Smallest Geo Lift", "Best design: 20 counties for 12 weeks", INK),
        ("Difference-in-differences false alarms", "DiD False Alarms", f"{F8['did_false_alarms']} across designs; "
                                                                      "promised 5%", INK),
        ("CausalImpact-style false alarms", "CausalImpact False Alarms",
         f"{F8['causalimpact_style_false_alarms']}: cries wolf", ACCENT_TEXT),
    ])
    y, h = BAND["primary"]
    p.add("measure_false_alarms", "clusteredBarChart", gx(0), y, gw(6), h,
          roles={"Category": [named(col("geo_designs", "method"), "Method")],
                 "Y": [named(mea("False Alarm Rate"), "False alarm rate")]},
          sort=[(mea("False Alarm Rate"), "Descending")],
          objects={**axes(value_axis=False, inner_padding=40), **labels(), **legend(show=False),
                   "dataPoint": [all_points({"fill": measure_color("Method Color")})]},
          title="The CausalImpact-style model cries wolf 2 to 3.5 times too often",
          subtitle="Share of no-campaign tests flagged as significant, average of 9 designs · promised: 5%",
          alt="Bar chart of false alarm rates: CausalImpact-style highest, difference-in-differences and synthetic "
              "control near 5%.")
    p.add("measure_mde", "pivotTable", gx(6), y, gw(6), h,
          roles={"Rows": [named(col("geo_designs", "counties_label"), "Test design")],
                 "Columns": [named(col("geo_designs", "weeks_label"), "Test length")],
                 "Values": [named(mea("Smallest Lift DiD"), "Smallest lift detected")]},
          sort=[(col("geo_designs", "counties_label"), "Ascending")],
          objects={**table_style(font_size=12, padding=12),
                   "values": table_style(font_size=12)["values"] + [gradient("Smallest Lift DiD", hi=HEAT_LIGHT_MAX)],
                   "subTotals": props(columnSubtotals=False, rowSubtotals=False)},
          title=f"Even 20 counties for 12 weeks only reliably detect about {F8['best_design_min_detectable_lift']}",
          subtitle="Difference-in-differences: smallest lift detected 80% of the time · real Iowa sales, simulated "
                   "campaigns",
          alt="Matrix of the smallest detectable lift by number of test counties and test length.")
    y, h = BAND["support"]
    p.add("measure_holdout", "clusteredColumnChart", gx(0), y, gw(12), h,
          roles={"Category": [named(col("holdout_users", "target_label"), "Lift to detect")],
                 "Series": [named(col("holdout_users", "holdout_label"), "Holdout")],
                 "Y": [named(mea("Users Needed"), "Users needed")]},
          sort=[(col("holdout_users", "target_label"), "Ascending")],
          objects={**axes(inner_padding=30), **labels(precision=1), **legend()},
          title=f"Rare conversions need big holdouts: about {F9['users_for_10pct_conversion_lift_10pct_holdout']} "
                "users to see a +10% lift with a 10% holdout",
          subtitle=f"Users needed to detect a conversion lift 80% of the time (5% false-alarm rate) · "
                   f"{F9['users_for_10pct_conversion_lift_even_split']} with a 50/50 split · base rate from the Criteo "
                   "control group",
          alt="Column chart of users needed to detect a +5%, +10% and +20% conversion lift with 10%, 15% and 50% "
              "of users held out.")
    p.decision_strip([
        ("Finding", "Holdouts see small effects; geo tests on noisy weekly sales only catch big ones."),
        ("Evidence", f"Best geo design detects about {F8['best_design_min_detectable_lift']}; CausalImpact-style "
                     f"raised {F8['causalimpact_style_false_alarms']} false alarms."),
        ("Interpretation", f"Rare conversions need scale: {F9['users_for_10pct_conversion_lift_10pct_holdout']} "
                           "users for a +10% lift."),
        ("Next action", "Keep an always-on holdout; geo tests only where holdouts are impossible, sized by simulation."),
    ])
    p.footer("Sources: Iowa Liquor Sales (BigQuery public data), real sales with simulated campaigns · holdout sizing "
             "from Criteo control-group rates")
    return p


# =====================================================================================
# THEME, REPORT FILES, VALIDATION
# =====================================================================================

def write_theme() -> None:
    font, semibold = TOKENS["font"]["family"], TOKENS["font"]["family.semibold"]
    write_json(PBI_DIR / "theme.json", {
        "$schema": "https://raw.githubusercontent.com/microsoft/powerbi-desktop-samples/main/"
                   "Report%20Theme%20JSON%20Schema/reportThemeSchema-2.157.json",
        "name": TOKENS["name"], "dataColors": _T["categorical"],
        "background": CARD, "secondaryBackground": PAGE_BG, "foreground": INK, "foregroundNeutralSecondary": INK_2,
        "foregroundNeutralTertiary": MUTED, "foregroundSelected": PRIMARY_STRONG, "disabledText": SIDE_MUTED,
        "tableAccent": PRIMARY, "accent": PRIMARY, "good": _T["status.positive.text"],
        "neutral": _T["status.warning.text"], "bad": _T["status.negative.text"],
        "maximum": HEAT_MAX, "center": SECONDARY, "minimum": HEAT_MIN, "null": BORDER,
        "textClasses": {
            "largeTitle": {"fontSize": 20, "fontFace": semibold, "color": INK},
            "callout": {"fontSize": 26, "fontFace": font, "color": INK},
            "title": {"fontSize": 12, "fontFace": semibold, "color": INK},
            "header": {"fontSize": 10, "fontFace": semibold, "color": INK},
            "label": {"fontSize": 9, "fontFace": font, "color": INK_2},
            "smallLabel": {"fontSize": 8, "fontFace": font, "color": MUTED}},
        "visualStyles": {
            "*": {"*": {
                "background": [{"show": True, "color": {"solid": {"color": CARD}}, "transparency": 0}],
                "border": [{"show": True, "color": {"solid": {"color": BORDER}}, "radius": TOKENS["radius"]["card"]}],
                "dropShadow": [{"show": False}],
                "padding": [{"top": 16, "bottom": 16, "left": 16, "right": 16}],
                "title": [{"show": True, "fontFamily": semibold, "fontSize": 12, "fontColor": {"solid": {"color": INK}},
                           "alignment": "left", "titleWrap": True}],
                "subTitle": [{"fontFamily": font, "fontSize": 9, "fontColor": {"solid": {"color": INK_2}},
                              "alignment": "left", "titleWrap": True}],
                "spacing": [{"customizeSpacing": True, "spaceBelowTitle": 4, "spaceBelowSubTitle": 8,
                             "spaceBelowTitleArea": 12}]}},
            "page": {"*": {
                "background": [{"color": {"solid": {"color": PAGE_BG}}, "transparency": 0}],
                "outspace": [{"color": {"solid": {"color": PAGE_BG}}, "transparency": 0}]}}},
    })


def build_report(pages: list[Page]) -> None:
    d = RP_DIR / "definition"
    write_json(RP_DIR / "definition.pbir", {
        "$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json", "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    write_json(d / "version.json", {
        "$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    theme_name = "NordicTheme.json"
    write_json(d / "report.json", {
        "$schema": f"{SCHEMA}/item/report/definition/report/3.0.0/schema.json",
        "themeCollection": {
            "baseTheme": {"name": "CY24SU10", "reportVersionAtImport": {
                "visual": "1.8.95", "report": "2.0.95", "page": "1.3.95"}, "type": "SharedResources"},
            "customTheme": {"name": theme_name, "reportVersionAtImport": {
                "visual": "2.1.0", "report": "2.1.0", "page": "2.0.0"}, "type": "RegisteredResources"}},
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": theme_name, "path": theme_name, "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                     "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True,
                     "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True},
    })
    static = RP_DIR / "StaticResources"
    (static / "SharedResources" / "BaseThemes").mkdir(parents=True, exist_ok=True)
    (static / "RegisteredResources").mkdir(parents=True, exist_ok=True)
    shutil.copy(PBI_DIR / "_base" / "CY24SU10.json", static / "SharedResources" / "BaseThemes" / "CY24SU10.json")
    shutil.copy(PBI_DIR / "theme.json", static / "RegisteredResources" / theme_name)
    write_json(d / "pages" / "pages.json", {
        "$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [p.name for p in pages], "activePageName": pages[0].name})
    for p in pages:
        write_json(d / "pages" / p.name / "page.json", {"$schema": PAGE_SCHEMA, "name": p.name,
                                                       "displayName": p.display, "displayOption": "FitToPage",
                                                       "height": p.height, "width": p.width})
        for v in p.visuals:
            write_json(d / "pages" / p.name / "visuals" / v["name"] / "visual.json", v)
    write_json(PBI_DIR / f"{NAME}.pbip", {
        "$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json", "version": "1.0",
        "artifacts": [{"report": {"path": RP_DIR.name}}], "settings": {"enableAutoRecovery": True}})


def validate_report() -> int:
    """Validate every report JSON file against the Microsoft schema named in its $schema."""
    import jsonschema
    import requests
    from referencing import Registry, Resource

    cache: dict[str, dict] = {}

    def fetch(uri: str) -> dict:
        if uri not in cache:
            url = uri.replace("https://developer.microsoft.com/json-schemas/",
                              "https://raw.githubusercontent.com/microsoft/json-schemas/main/")
            cache[uri] = requests.get(url, timeout=30).json()
        return cache[uri]

    registry = Registry(retrieve=lambda uri: Resource.from_contents(fetch(uri)))
    errors = 0
    files = [*RP_DIR.rglob("*.json"), *RP_DIR.glob("*.pbir"), *PBI_DIR.glob("*.pbip"), SM_DIR / "definition.pbism"]
    for f in files:
        if "StaticResources" in f.parts:
            continue
        doc = json.loads(f.read_text(encoding="utf-8"))
        schema_uri = doc.get("$schema")
        if not schema_uri:
            continue
        schema = fetch(schema_uri)
        validator = jsonschema.validators.validator_for(schema)(schema, registry=registry)
        for err in validator.iter_errors(doc):
            errors += 1
            print(f"  {f.relative_to(PBI_DIR)}: {'/'.join(map(str, err.absolute_path))}: {err.message[:200]}")
    print(f"Validated {len(files)} files: {errors} error(s)")
    return errors


def check_references_and_layout() -> int:
    """Checks the schemas can't do: measures and columns exist, visuals stay on the canvas without overlap."""
    errors = 0
    names = {m[0] for m in MEASURES}
    columns = {(t, c) for t in TABLES for c, _, _ in csv_columns(t)}
    for name, _, _, dax in MEASURES:
        for ref_name in re.findall(r"(?<![\w\]'])\[([^\]]+)\]", dax):
            if ref_name not in names:
                errors += 1
                print(f"  measure [{name}] references unknown measure [{ref_name}]")
        for t, c in re.findall(r"\b([a-z_]+)\[([a-z_]+)\]", dax):
            if (t, c) not in columns:
                errors += 1
                print(f"  measure [{name}] references unknown column {t}[{c}]")
    for vfile in RP_DIR.glob("**/visual.json"):
        text = vfile.read_text(encoding="utf-8")
        for m in re.findall(r'"Entity": "_Measures"\s*},\s*"Property": "([^"]+)"', text):
            if m not in names:
                errors += 1
                print(f"  {vfile.parent.name}: unknown measure [{m}]")
        for t, c in re.findall(r'"Entity": "([a-z_]+)"\s*},\s*"Property": "([^"]+)"', text):
            if (t, c) not in columns:
                errors += 1
                print(f"  {vfile.parent.name}: unknown column {t}[{c}]")
    for page_dir in RP_DIR.glob("definition/pages/*"):
        if not page_dir.is_dir():
            continue
        meta = json.loads((page_dir / "page.json").read_text(encoding="utf-8"))
        boxes = []
        for vfile in page_dir.rglob("visual.json"):
            pos = json.loads(vfile.read_text(encoding="utf-8"))["position"]
            x, y, w, h = pos["x"], pos["y"], pos["width"], pos["height"]
            if x < 0 or y < 0 or x + w > meta["width"] or y + h > meta["height"]:
                errors += 1
                print(f"  {page_dir.name}/{vfile.parent.name}: off canvas ({x},{y},{w},{h})")
            boxes.append((vfile.parent.name, x, y, x + w, y + h))
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                if "_ovl" in a[0] or "_ovl" in b[0]:
                    continue  # deliberate layering (value on its KPI card, items on the sidebar)
                if a[1] < b[3] and b[1] < a[3] and a[2] < b[4] and b[2] < a[4]:
                    errors += 1
                    print(f"  {page_dir.name}: {a[0]} overlaps {b[0]}")
    print(f"Reference & layout checks: {errors} error(s)")
    return errors


def _num(v: dict, default: float = 0) -> float:
    return float(v["expr"]["Literal"]["Value"].rstrip("D")) if v else default


def _wrapped_lines(text: str, size_pt: float, width_px: float, bold: bool = False) -> int:
    """Lines a string wraps to, from average Segoe UI character widths (a rough, slightly cautious estimate)."""
    char = size_pt * 96 / 72 * (0.49 if bold else 0.46)  # measured on this report's screenshots, plus a margin
    lines, used = 1, 0.0
    for word in text.split():
        need = len(word) * char + (char if used else 0)
        if used and used + need > width_px:
            lines, used = lines + 1, len(word) * char
        else:
            used += need
    return lines


def check_text_fit() -> int:
    """Text the schemas can't check: textbox text fits its box, visual titles and KPI labels fit on one line, and
    subtitles (which wrap) take at most two."""
    errors = 0
    for vfile in sorted(RP_DIR.glob("definition/pages/*/visuals/*/visual.json")):
        v = json.loads(vfile.read_text(encoding="utf-8"))
        name, w, h = v["name"], v["position"]["width"], v["position"]["height"]
        vis, vco = v["visual"], v["visual"].get("visualContainerObjects", {})
        pad = vco.get("padding", [{"properties": {}}])[0]["properties"]
        left, right, top, bottom = (_num(pad.get(k), 5) for k in ("left", "right", "top", "bottom"))
        inner_w = w - left - right
        if vis["visualType"] == "textbox" and not name.endswith(("_side", "_card")) and "_bar_" not in name:
            height = 0.0
            for para in vis["objects"]["general"][0]["properties"]["paragraphs"]:
                for run in para["textRuns"]:
                    size = float(run["textStyle"]["fontSize"].rstrip("pt"))
                    bold = "Semibold" in run["textStyle"]["fontFamily"]
                    height += _wrapped_lines(run["value"], size, inner_w, bold) * size * 96 / 72 * 1.36
            if height > h - top - bottom + 1:
                errors += 1
                print(f"  {name}: text needs about {height:.0f}px, box has {h - top - bottom:.0f}px")
        for key, size, bold, max_lines in (("title", 12, True, 1), ("subTitle", 9, False, 2)):
            if key in vco and "text" in vco[key][0]["properties"]:
                text = vco[key][0]["properties"]["text"]["expr"]["Literal"]["Value"][1:-1]
                size = _num(vco[key][0]["properties"].get("fontSize"), size)
                bold = bold and "fontFamily" not in vco[key][0]["properties"]
                if _wrapped_lines(text, size, inner_w, bold) > max_lines:
                    errors += 1
                    print(f"  {name}: {key} needs more than {max_lines} line(s): {text!r}")
    print(f"Text fit checks: {errors} error(s)")
    return errors


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()
    for d in (SM_DIR / "definition", RP_DIR / "definition"):
        if d.exists():
            shutil.rmtree(d)  # regenerate cleanly; .pbi caches and local settings are kept
    build_semantic_model()
    write_theme()
    build_report([page_overview(), page_targeting(), page_measure()])
    write_measures_reference()
    print(f"Wrote {PBI_DIR / (NAME + '.pbip')}  ({len(MEASURES)} measures, {len(TABLES) + 1} tables)")
    if args.validate:
        raise SystemExit(1 if (validate_report() + check_references_and_layout() + check_text_fit()) else 0)


if __name__ == "__main__":
    main()
