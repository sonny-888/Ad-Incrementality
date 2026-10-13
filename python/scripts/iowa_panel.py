"""Finding 8, step 1: turn the BigQuery export into a clean weeks x counties panel of log sales.

    py python/scripts/iowa_panel.py

Input:  the BigQuery export of sql/iowa_county_week.sql in data/raw/ (iowa_county_week.csv, or BigQuery's own
        bq-results-*.csv name; the newest is used)
Output: data/processed/iowa_log_sales.parquet, and a short data-quality summary in results/iowa_panel.json

Counties missing sales in more than 5% of weeks are left out rather than filled in: filling long gaps would invent
a smooth series that never existed. Remaining odd weeks (no orders, or a non-positive total) are filled from
neighbouring weeks. Most such gaps are holiday weeks (Labor Day, Memorial Day, Thanksgiving), when state sales fall
to about half a normal week and small counties often place no order. The threshold was first 2%; it was raised to 5%
after seeing that the gaps are holiday weeks, not broken counties (2% would have dropped 19 counties for that).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
MAX_MISSING_SHARE = 0.05
OUT = ROOT / "data" / "processed" / "iowa_log_sales.parquet"
SUMMARY = ROOT / "results" / "iowa_panel.json"

_NAMES = """Adair Adams Allamakee Appanoose Audubon Benton Black_Hawk Boone Bremer Buchanan Buena_Vista Butler Calhoun
Carroll Cass Cedar Cerro_Gordo Cherokee Chickasaw Clarke Clay Clayton Clinton Crawford Dallas Davis Decatur Delaware
Des_Moines Dickinson Dubuque Emmet Fayette Floyd Franklin Fremont Greene Grundy Guthrie Hamilton Hancock Hardin Harrison
Henry Howard Humboldt Ida Iowa Jackson Jasper Jefferson Johnson Jones Keokuk Kossuth Lee Linn Louisa Lucas Lyon Madison
Mahaska Marion Marshall Mills Mitchell Monona Monroe Montgomery Muscatine O'Brien Osceola Page Palo_Alto Plymouth
Pocahontas Polk Pottawattamie Poweshiek Ringgold Sac Scott Shelby Sioux Story Tama Taylor Union Van_Buren Wapello Warren
Washington Wayne Webster Winnebago Winneshiek Woodbury Worth Wright"""
COUNTIES = [c.replace("_", " ") for c in _NAMES.split()]  # underscores keep two-word names together when splitting
assert len(COUNTIES) == 99


def _key(name: str) -> str:
    return re.sub(r"[^A-Z]", "", str(name).upper())


CANON = {_key(c): c for c in COUNTIES}


def canonical(raw: str) -> str | None:
    """Map a raw county string to one of Iowa's 99 counties; handles case, punctuation and truncated names."""
    k = _key(raw)
    if not k:
        return None
    if k in CANON:
        return CANON[k]
    hits = [c for ck, c in CANON.items() if len(k) >= 5 and ck.startswith(k)]
    return hits[0] if len(hits) == 1 else None


def raw_file() -> Path:
    named = RAW_DIR / "iowa_county_week.csv"
    if named.exists():
        return named
    found = sorted(RAW_DIR.glob("bq-results-*.csv"), key=lambda p: p.stat().st_mtime)
    if not found:
        raise FileNotFoundError(f"No BigQuery export in {RAW_DIR}; run sql/iowa_county_week.sql first")
    return found[-1]


def main() -> None:
    raw = raw_file()
    df = pd.read_csv(raw, parse_dates=["week"])
    df["county_clean"] = df["county"].map(canonical)
    unmatched = df.loc[df["county_clean"].isna()].groupby("county", dropna=False)["sales_dollars"].sum()
    clean = df.dropna(subset=["county_clean"])
    panel = clean.pivot_table(index="week", columns="county_clean", values="sales_dollars", aggfunc="sum").sort_index()

    # Drop the first and last week if partial (the export starts and ends mid-week)
    full = panel.index[(panel.index > panel.index.min()) & (panel.index < panel.index.max())]
    panel = panel.loc[full]
    missing = panel.isna() | (panel <= 0)
    share_missing = missing.mean()
    dropped = share_missing[share_missing > MAX_MISSING_SHARE].sort_values(ascending=False)
    panel, missing = panel.drop(columns=dropped.index), missing.drop(columns=dropped.index)
    summary = {
        "source_file": raw.name,
        "rows_in_export": len(df),
        "counties_left_out_for_gaps": {c: round(float(s), 3) for c, s in dropped.items()},
        "weeks": len(panel), "first_week": str(panel.index.min().date()), "last_week": str(panel.index.max().date()),
        "counties": int(panel.shape[1]),
        "unmatched_county_values": {str(k): round(float(v), 2) for k, v in unmatched.items()},
        "unmatched_sales_share": float(unmatched.sum() / df["sales_dollars"].sum()),
        "county_weeks_missing_or_zero": int(missing.values.sum()),
        "counties_with_gaps": {c: int(n) for c, n in missing.sum().items() if n > 0},
    }
    # A missing or zero week is filled from the county's neighbouring weeks, so logs stay defined
    panel = panel.mask(missing).interpolate(limit_direction="both")
    np.log(panel).to_parquet(OUT)
    SUMMARY.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "counties_with_gaps"}, indent=1))
    print(f"counties with gaps: {len(summary['counties_with_gaps'])}; wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
