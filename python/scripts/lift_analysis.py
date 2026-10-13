"""Findings 2 to 4 on the full Criteo data: naive view, intent-to-treat lift, and the effect of seeing an ad.

    py python/scripts/lift_analysis.py

Reads data/processed/criteo_uplift.parquet and writes results/lift.json.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import duckdb
import numpy as np
import pyarrow.parquet as pq
from linearmodels.iv import IV2SLS

from incrementality.experiment import FEATURES
from incrementality.lift import exposed_effect, lin_ate, rate_diff

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "processed" / "criteo_uplift.parquet"
OUT = ROOT / "results" / "lift.json"
OUTCOMES = ["visit", "conversion"]


def batches():
    for b in pq.ParquetFile(DATA).iter_batches(batch_size=1_000_000, columns=FEATURES + ["treatment"] + OUTCOMES):
        yield {name: b.column(name).to_numpy() for name in b.schema.names}


def main() -> None:
    cells = duckdb.sql(f"""
        SELECT treatment, exposure, count(*) AS n, sum(visit) AS visit, sum(conversion) AS conversion
        FROM '{DATA.as_posix()}' GROUP BY ALL
    """).df().set_index(["treatment", "exposure"])
    e, nt, c = cells.loc[(1, 1)], cells.loc[(1, 0)], cells.loc[(0, 0)]
    assert (0, 1) not in cells.index, "control users should never be exposed"
    unexposed = nt + c

    results = {"cells": {f"t{t}_e{x}": row.to_dict() for (t, x), row in cells.iterrows()}}
    cols = pq.read_table(DATA, columns=["treatment", "exposure"] + OUTCOMES).to_pandas()
    const = np.ones(len(cols))

    for y in OUTCOMES:
        print(f"\n=== {y} ===")
        naive = rate_diff(e[y], e["n"], unexposed[y], unexposed["n"])
        print(f"F2 naive, saw ad vs didn't: {naive.rate_t:.4%} vs {naive.rate_c:.4%}, "
              f"relative {naive.rel:+.0%} [{naive.rel_lo:+.0%}, {naive.rel_hi:+.0%}]")

        t_x, t_n = e[y] + nt[y], e["n"] + nt["n"]
        itt = rate_diff(t_x, t_n, c[y], c["n"])
        adj = lin_ate(batches, y, FEATURES)
        print(f"F3 ITT raw: {itt.rate_t:.4%} vs {itt.rate_c:.4%}, diff {itt.diff:+.5f} "
              f"[{itt.diff_lo:+.5f}, {itt.diff_hi:+.5f}], relative {itt.rel:+.1%} [{itt.rel_lo:+.1%}, {itt.rel_hi:+.1%}]")
        print(f"F3 ITT adjusted for f0-f11: diff {adj.estimate:+.5f} [{adj.lo:+.5f}, {adj.hi:+.5f}], "
              f"relative {adj.estimate / itt.rate_c:+.1%}")

        ex = exposed_effect(e[y], e["n"], nt[y], nt["n"], c[y], c["n"])
        iv = IV2SLS(cols[y].astype(float), const, cols["exposure"].astype(float), cols["treatment"].astype(float)
                    ).fit(cov_type="robust")
        iv_ci = iv.conf_int().loc["exposure"]
        print(f"F4 effect of seeing an ad: {ex.rate_exposed:.4%} observed vs {ex.baseline:.4%} without the ad, "
              f"+{ex.cace:.5f} [{ex.cace_lo:+.5f}, {ex.cace_hi:+.5f}] (2SLS {iv.params['exposure']:+.5f} "
              f"[{iv_ci['lower']:+.5f}, {iv_ci['upper']:+.5f}]), relative {ex.rel:+.0%} [{ex.rel_lo:+.0%}, {ex.rel_hi:+.0%}]")
        print(f"   share of exposed users' {y}s caused by the ad: {ex.caused_share:.1%} "
              f"[{ex.caused_lo:.1%}, {ex.caused_hi:.1%}]; selection gap (no-ad rate of exposed vs unexposed) "
              f"{ex.baseline / naive.rate_c:.1f}x")

        results[y] = {
            "naive": asdict(naive),
            "itt": asdict(itt),
            "itt_adjusted": {**asdict(adj), "lo": adj.lo, "hi": adj.hi, "rel": adj.estimate / itt.rate_c},
            "exposed": asdict(ex),
            "iv_2sls": {"estimate": float(iv.params["exposure"]), "se": float(iv.std_errors["exposure"]),
                        "lo": float(iv_ci["lower"]), "hi": float(iv_ci["upper"])},
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, default=float), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
