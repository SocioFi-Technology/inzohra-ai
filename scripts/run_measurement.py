#!/usr/bin/env python
"""Run the MeasurementPipeline against the 2008 Dennis Ln fixture.

Usage:
    uv run python scripts/run_measurement.py
    uv run python scripts/run_measurement.py --dry-run

Reads DATABASE_URL, ANTHROPIC_API_KEY, S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY from .env.

Requires:
    - Fixture ingested: uv run scripts/ingest_all_fixture.py
    - Migration 0007 applied: psql $DATABASE_URL -f db/migrations/0007_measurements_provenance.sql
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_repo_root = Path(__file__).resolve().parent.parent
load_dotenv(_repo_root / ".env", override=True)

# NOTE: No sys.path surgery — uv workspace resolves app.* as a namespace package
# spanning services/ingestion, services/review, and services/measurement.

import argparse  # noqa: E402
import logging  # noqa: E402

import psycopg  # noqa: E402
import psycopg.rows  # noqa: E402

from app.pipelines.measurement import run_measurement_pipeline  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fixture constants
# ---------------------------------------------------------------------------

PERMIT_NUMBER = "B25-2734"
JURISDICTION = "santa_rosa"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the MeasurementPipeline against the Dennis Ln fixture."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute everything but skip all DB writes and S3 downloads.",
    )
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    # Look up project and submittal IDs from the fixture
    conn = psycopg.connect(database_url, row_factory=psycopg.rows.dict_row)
    try:
        row = conn.execute(
            "SELECT project_id FROM projects WHERE permit_number = %s AND jurisdiction = %s",
            (PERMIT_NUMBER, JURISDICTION),
        ).fetchone()
        if row is None:
            print(
                "ERROR: project not found. Run ingest_all_fixture.py first.",
                file=sys.stderr,
            )
            sys.exit(1)
        project_id = str(row["project_id"])

        row_s = conn.execute(
            "SELECT submittal_id FROM submittals WHERE project_id = %s AND round_number = 1",
            (project_id,),
        ).fetchone()
        if row_s is None:
            print(
                "ERROR: round-1 submittal not found for project. Re-run ingest_all_fixture.py.",
                file=sys.stderr,
            )
            sys.exit(1)
        submittal_id = str(row_s["submittal_id"])
    finally:
        conn.close()

    print(f"Project:   {project_id}")
    print(f"Submittal: {submittal_id}")
    print(f"Dry-run:   {args.dry_run}")
    print()

    result = run_measurement_pipeline(
        database_url,
        project_id,
        submittal_id,
        api_key,
        dry_run=args.dry_run,
    )

    print("Results:")
    print(f"  Sheets processed   : {result.sheets_processed}")
    print(f"  Entities inserted  : {result.entities_inserted}")
    print(f"  Measurements       : {result.measurements_inserted}")
    print(f"  Skipped sheets     : {result.skipped_sheets}")

    if result.errors:
        print(f"  Errors ({len(result.errors)}):")
        for err in result.errors[:10]:
            print(f"    - {err}")
        if len(result.errors) > 10:
            print(f"    ... and {len(result.errors) - 10} more")

    print()
    if result.errors:
        print("[WARN] Measurement pipeline completed with errors (see above)")
        sys.exit(1)
    else:
        print("[OK] Measurement pipeline complete")


if __name__ == "__main__":
    main()
