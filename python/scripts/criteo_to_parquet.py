"""Convert the Criteo Uplift v2.1 CSV (gzipped, about 3 GB unpacked) to Parquet and check it.

DuckDB streams the gzipped CSV, so the full file never has to sit in memory.

    py python/scripts/criteo_to_parquet.py

Input:  data/raw/criteo-research-uplift-v2.1.csv.gz
        (https://huggingface.co/datasets/criteo/criteo-uplift, Criteo's official mirror; CC BY-NC-SA 4.0)
Output: data/processed/criteo_uplift.parquet
"""

from __future__ import annotations

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "criteo-research-uplift-v2.1.csv.gz"
OUT = ROOT / "data" / "processed" / "criteo_uplift.parquet"

FEATURES = [f"f{i}" for i in range(12)]
FLAGS = ["treatment", "conversion", "visit", "exposure"]
EXPECTED_ROWS = 13_979_592  # Diemert et al. (2018), v2.1 release notes


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    columns = {**{f: "DOUBLE" for f in FEATURES}, **{f: "TINYINT" for f in FLAGS}}
    con.execute(f"""
        COPY (SELECT * FROM read_csv('{RAW.as_posix()}', header = true, columns = {columns!r}))
        TO '{OUT.as_posix()}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 1000000)
    """)

    rows, treated, visit, conversion, exposure, bad_flags, nulls = con.execute(f"""
        SELECT count(*), avg(treatment), avg(visit), avg(conversion), avg(exposure),
               count(*) FILTER (WHERE {" OR ".join(f"{f} NOT IN (0, 1)" for f in FLAGS)}),
               count(*) FILTER (WHERE {" OR ".join(f"{c} IS NULL" for c in columns)})
        FROM '{OUT.as_posix()}'
    """).fetchone()
    print(f"rows {rows:,} | treated {treated:.2%} | visit {visit:.2%} | conversion {conversion:.3%} "
          f"| exposure {exposure:.2%} | non 0/1 flags {bad_flags} | rows with nulls {nulls}")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:,.0f} MB)")
    assert rows == EXPECTED_ROWS, f"expected {EXPECTED_ROWS:,} rows, got {rows:,}"
    assert bad_flags == 0 and nulls == 0


if __name__ == "__main__":
    main()
