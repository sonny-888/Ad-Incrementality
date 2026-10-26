"""sql/criteo_lift.sql must reproduce the Python pipeline's raw headline numbers exactly.

Needs the local Criteo data (data/processed/criteo_uplift.parquet), so it skips where the data isn't present (CI).
"""

import json
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "processed" / "criteo_uplift.parquet"


@pytest.mark.skipif(not DATA.exists(), reason="needs the local Criteo data (see README: Reproduce and verify)")
def test_sql_reproduces_python_headline_numbers():
    con = duckdb.connect()
    con.execute(f"CREATE VIEW criteo AS SELECT * FROM '{DATA.as_posix()}'")
    row = con.execute((ROOT / "sql" / "criteo_lift.sql").read_text(encoding="utf-8")).df().iloc[0]

    lift = json.loads((ROOT / "results" / "lift.json").read_text(encoding="utf-8"))["conversion"]
    checks = json.loads((ROOT / "results" / "experiment_checks.json").read_text(encoding="utf-8"))
    close = lambda a, b: a == pytest.approx(b, rel=1e-6, abs=1e-12)

    assert row["n"] == checks["srm"]["n_total"]
    assert row["n_control_exposed"] == 0
    assert close(row["treated_share"], checks["srm"]["observed_share"])
    assert close(row["srm_chi2"], checks["srm"]["chi2"])
    assert close(row["naive_multiple"], lift["naive"]["rate_t"] / lift["naive"]["rate_c"])
    for sql_col, py_key in [("itt", "diff"), ("itt_lo", "diff_lo"), ("itt_hi", "diff_hi"), ("itt_relative", "rel")]:
        assert close(row[sql_col], lift["itt"][py_key]), sql_col
    for sql_col, py_key in [("exposure_share", "share_exposed"), ("cace", "cace"), ("baseline_exposed", "baseline"),
                            ("r_exposed", "rate_exposed"), ("caused_share", "caused_share")]:
        assert close(row[sql_col], lift["exposed"][py_key]), sql_col
