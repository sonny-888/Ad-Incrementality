"""Rebuild every result, chart and headline number, in order, stopping at the first failure.

    py python/scripts/run_all.py                    # everything (about 60 minutes)
    py python/scripts/run_all.py --skip-slow        # reuse the four slow steps' saved results (about 12 minutes)
    py python/scripts/run_all.py --skip-notebooks

Data comes first and is a separate step:
- Criteo: data/raw/criteo-research-uplift-v2.1.csv.gz from https://huggingface.co/datasets/criteo/criteo-uplift
- Iowa: run sql/iowa_county_week.sql in the BigQuery console and save the CSV into data/raw/
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
S = "python/scripts/"
SLOW = {"lift_aipw.py", "sensitivity_analysis.py", "uplift_analysis.py", "geo_simulation.py"}
NOTEBOOKS = ["01_data.ipynb", "02_experiment_checks.ipynb", "03_lift.ipynb", "04_uplift.ipynb", "05_geo_tests.ipynb"]


def run(label: str, args: list[str]) -> None:
    print(f"\n==> {label}", flush=True)
    start = time.time()
    subprocess.run(args, cwd=ROOT, check=True)  # list arguments, no shell
    print(f"    done in {time.time() - start:.0f}s", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-slow", action="store_true", help="reuse saved results of the four slow steps")
    ap.add_argument("--skip-notebooks", action="store_true", help="skip re-running the notebooks")
    args = ap.parse_args()

    raw = ROOT / "data" / "raw"
    if not (raw / "criteo-research-uplift-v2.1.csv.gz").exists():
        sys.exit("Criteo file missing from data/raw/. See the README for the download link.")
    if not (list(raw.glob("bq-results-*.csv")) or (raw / "iowa_county_week.csv").exists()):
        sys.exit("Iowa export missing from data/raw/. Run sql/iowa_county_week.sql in BigQuery and save the CSV there.")

    run("Unit tests", [PY, "-m", "pytest", "-q"])
    if not (ROOT / "data" / "processed" / "criteo_uplift.parquet").exists():
        run("Criteo CSV to Parquet, with integrity checks", [PY, S + "criteo_to_parquet.py"])
    steps = [
        ("Finding 1: experiment health", "experiment_checks.py"),
        ("Findings 2 to 4: naive view, lift, effect of seeing an ad", "lift_analysis.py"),
        ("Findings 3 to 5: doubly robust lift (slow)", "lift_aipw.py"),
        ("Findings 3 to 5: sensitivity of the leak correction (slow)", "sensitivity_analysis.py"),
        ("Finding 6: train uplift models and score held-out users (slow)", "uplift_analysis.py"),
        ("Finding 6: grade the rankings", "uplift_evaluate.py"),
        ("Finding 7: money", "money_analysis.py"),
        ("Finding 8: Iowa county-week panel", "iowa_panel.py"),
        ("Finding 8: simulated geo tests (slow)", "geo_simulation.py"),
        ("Finding 9: holdout sizing", "plan_analysis.py"),
        ("Finding 9: budget-cut test proposal", "budget_test_plan.py"),
    ]
    for label, script in steps:
        if args.skip_slow and script in SLOW:
            print(f"\n==> {label}: skipped, reusing saved results", flush=True)
            continue
        run(label, [PY, S + script])
    if args.skip_slow:  # the geo summary is cheap to refresh from the saved runs
        run("Finding 8: re-summarise saved geo runs", [PY, S + "geo_simulation.py", "--summarise-only"])

    for fig in ["fig_experiment", "fig_lift", "fig_attribution", "fig_uplift", "fig_money", "fig_geo", "fig_plan"]:
        run(f"Charts: {fig}", [PY, S + fig + ".py"])

    if not args.skip_notebooks:
        run("Write the notebooks", [PY, S + "build_notebooks.py"])
        for nb in NOTEBOOKS:
            run(f"Notebook {nb}", [PY, "-m", "nbconvert", "--to", "notebook", "--execute", "--inplace",
                                   f"notebooks/{nb}"])

    run("Headline facts (every number quoted in the README, report and deck)", [PY, S + "headline_facts.py"])
    run("Dashboard data files", [PY, S + "export_dashboard_data.py"])
    run("Power BI project, validated against Microsoft's schemas", [PY, "dashboard/build_pbip.py", "--validate"])
    run("Report and deck PDFs", [PY, S + "build_documents.py"])
    run("README, report and deck text match the results", [PY, "-m", "pytest", "-q",
                                                          "python/tests/test_headline_facts.py"])
    print("\nAll done.")


if __name__ == "__main__":
    main()
