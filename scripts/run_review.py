#!/usr/bin/env python
"""Run the PlanIntegrityReviewer against the 2008 Dennis Ln fixture.

Usage (from repo root)::

    uv run scripts/run_review.py

Reads DATABASE_URL from .env at the repo root.
Requires the fixture to have been ingested first (``uv run scripts/ingest_fixture.py``).
Requires the KB to have been seeded first (``uv run scripts/seed_kb.py``).

Prints a summary of every finding emitted and a count by rule_id.
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve paths and load .env before importing service code
# ---------------------------------------------------------------------------

_repo_root = Path(__file__).resolve().parent.parent

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_repo_root / ".env", override=True)

# NOTE: No sys.path surgery — uv workspace resolves app.* as a namespace package
# spanning services/ingestion, services/review, and services/measurement.

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

import psycopg  # noqa: E402
import psycopg.rows  # noqa: E402

from app.reviewers.plan_integrity import PlanIntegrityReviewer  # noqa: E402

# ---------------------------------------------------------------------------
# Fixture constants
# ---------------------------------------------------------------------------

PERMIT_NUMBER = "B25-2734"
JURISDICTION = "santa_rosa"


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    conn = psycopg.connect(database_url, row_factory=psycopg.rows.dict_row)
    try:
        # --- find the fixture project ---
        row = conn.execute(
            "SELECT project_id FROM projects WHERE permit_number = %s AND jurisdiction = %s",
            (PERMIT_NUMBER, JURISDICTION),
        ).fetchone()
        if row is None:
            print(
                f"ERROR: fixture project '{PERMIT_NUMBER}' not found. "
                "Run `uv run scripts/ingest_fixture.py` first.",
                file=sys.stderr,
            )
            sys.exit(1)

        project_id = str(row["project_id"])

        row_s = conn.execute(
            "SELECT submittal_id FROM submittals WHERE project_id = %s AND round_number = 1",
            (project_id,),
        ).fetchone()
        if row_s is None:
            print("ERROR: no round-1 submittal found.", file=sys.stderr)
            sys.exit(1)

        submittal_id = str(row_s["submittal_id"])

        print(f"\n{'='*60}")
        print(f"Project ID   : {project_id}")
        print(f"Submittal ID : {submittal_id}")
        print(f"{'='*60}\n")

        # --- guard: skip if findings already exist for this round ---
        existing = conn.execute(
            """SELECT COUNT(*) AS n FROM findings
                WHERE project_id = %s AND submittal_id = %s
                  AND review_round = 1 AND discipline = 'plan_integrity'""",
            (project_id, submittal_id),
        ).fetchone()
        if existing and existing["n"] > 0:
            print(f"  [skip] {existing['n']} plan_integrity finding(s) already exist for round 1.")
            print("  Delete them manually or re-ingest to re-run.\n")
            return

        # --- run reviewer ---
        reviewer = PlanIntegrityReviewer()
        finding_ids = reviewer.run(
            conn,
            project_id=project_id,
            submittal_id=submittal_id,
            review_round=1,
            database_url=database_url,
        )

        conn.commit()

        print(f"  Emitted {len(finding_ids)} finding(s).\n")

        # --- print summary ---
        if finding_ids:
            rows = conn.execute(
                """SELECT rule_id, severity, sheet_reference, draft_comment_text
                     FROM findings
                    WHERE finding_id = ANY(%s)
                    ORDER BY rule_id, created_at""",
                (finding_ids,),
            ).fetchall()

            counter: Counter[str] = Counter()
            for r in rows:
                rule = r["rule_id"] or "?"
                sev = r["severity"]
                sheet = (r["sheet_reference"] or {}).get("sheet_id") or "(project)"
                detail = (r["sheet_reference"] or {}).get("detail") or ""
                text_snippet = (r["draft_comment_text"] or "")[:90].replace("\n", " ")
                counter[rule] += 1
                print(f"  [{sev:17s}] {rule:20s} — {sheet} | {detail}")
                print(f"      {text_snippet}…")
                print()

            print("Summary by rule:")
            for rule, count in sorted(counter.items()):
                print(f"  {rule:20s} : {count}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
