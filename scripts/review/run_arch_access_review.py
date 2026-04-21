#!/usr/bin/env python
"""Run Architectural + Accessibility reviewers on the fixture project.

Usage::
    uv run scripts/run_arch_access_review.py [--project-id <uuid>] [--round <n>]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent.parent
from dotenv import load_dotenv
load_dotenv(_repo_root / ".env", override=True)

import psycopg
import psycopg.rows

from app.reviewers.architectural import ArchitecturalReviewer
from app.reviewers.accessibility import AccessibilityReviewer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--round", type=int, default=1)
    args = parser.parse_args()

    database_url = os.environ["DATABASE_URL"]
    conn = psycopg.connect(database_url, row_factory=psycopg.rows.dict_row)

    try:
        if args.project_id:
            project_id = args.project_id
        else:
            row = conn.execute(
                "SELECT project_id FROM projects WHERE permit_number = 'B25-2734' LIMIT 1"
            ).fetchone()
            if row is None:
                print("ERROR: fixture project B25-2734 not found. Run ingest first.")
                sys.exit(1)
            project_id = str(row["project_id"])

        sub_row = conn.execute(
            "SELECT submittal_id FROM submittals WHERE project_id = %s LIMIT 1",
            (project_id,),
        ).fetchone()
        if sub_row is None:
            print("ERROR: no submittal for project")
            sys.exit(1)
        submittal_id = str(sub_row["submittal_id"])

        print(f"project_id  = {project_id}")
        print(f"submittal_id= {submittal_id}")
        print(f"round       = {args.round}")
        print()

        # Delete old findings for this round + discipline to make idempotent
        for disc in ("architectural", "accessibility"):
            deleted = conn.execute(
                """DELETE FROM findings
                    WHERE project_id = %s AND review_round = %s AND discipline = %s""",
                (project_id, args.round, disc),
            ).rowcount
            if deleted:
                print(f"Deleted {deleted} existing {disc} findings for round {args.round}")

        arch_reviewer = ArchitecturalReviewer()
        arch_ids = arch_reviewer.run(
            conn,
            project_id=project_id,
            submittal_id=submittal_id,
            review_round=args.round,
            database_url=database_url,
        )
        print(f"ArchitecturalReviewer: {len(arch_ids)} findings")

        acc_reviewer = AccessibilityReviewer()
        acc_ids = acc_reviewer.run(
            conn,
            project_id=project_id,
            submittal_id=submittal_id,
            review_round=args.round,
            database_url=database_url,
        )
        print(f"AccessibilityReviewer: {len(acc_ids)} findings")

        conn.commit()
        print(f"\nTotal: {len(arch_ids) + len(acc_ids)} findings committed.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
