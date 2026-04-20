#!/usr/bin/env python
"""Run the ComparisonAgent against the fixture project and print P/R/F1.

Usage::
    uv run scripts/run_compare.py [--project-id <uuid>] [--round <n>]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo_root / "services" / "review"))

from dotenv import load_dotenv

load_dotenv(_repo_root / ".env", override=True)

import psycopg
import psycopg.rows

from app.comparison.compare import compare, ACCEPTED_GENERAL_RULES


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run ComparisonAgent and print precision/recall for the fixture."
    )
    parser.add_argument("--project-id", default=None, help="Override fixture project UUID")
    parser.add_argument("--round", type=int, default=1, help="Review round number (default: 1)")
    parser.add_argument(
        "--disciplines", nargs="*", default=None,
        help="Filter to specific disciplines (e.g. architectural accessibility)"
    )
    args = parser.parse_args()

    database_url = os.environ["DATABASE_URL"]

    with psycopg.connect(database_url, row_factory=psycopg.rows.dict_row) as conn:
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

    print(f"project_id = {project_id}")
    print(f"round      = {args.round}")
    if args.disciplines:
        print(f"disciplines= {args.disciplines}")
    print()

    result = compare(
        database_url,
        project_id=project_id,
        review_round=args.round,
        disciplines=args.disciplines,
    )

    # ── Summary ────────────────────────────────────────────────────────────────
    print(f"Total findings      : {result.total_findings}")
    print(f"Total BV comments   : {result.total_bv_comments}  (unique comment_numbers)")
    print(f"Matched findings    : {result.matched_findings}")
    print(f"Matched BV comments : {result.matched_bv_comments}")
    print(f"Accepted-general    : {result.accepted_general_count}  (not FPs — extra-value findings)")
    print(f"True false positives: {len(result.unmatched_finding_ids)}")
    print()
    print(f"Precision : {result.precision:.3f}  (need ≥0.85)")
    print(f"Recall    : {result.recall:.3f}  (need ≥0.80)")
    print(f"F1        : {result.f1:.3f}")
    print()

    p_ok = result.precision >= 0.85
    r_ok = result.recall >= 0.80
    print(f"[{'PASS' if p_ok else 'FAIL'}] Precision ≥ 0.85")
    print(f"[{'PASS' if r_ok else 'FAIL'}] Recall    ≥ 0.80")
    print()

    if result.unmatched_bv_numbers:
        print(f"Missed BV comments ({len(result.unmatched_bv_numbers)}): {result.unmatched_bv_numbers}")
    else:
        print("No missed BV comments.")

    if result.unmatched_finding_ids:
        # Fetch rule_ids for the true FPs so we can see what they are
        with psycopg.connect(database_url, row_factory=psycopg.rows.dict_row) as conn:
            fp_rows = conn.execute(
                f"""SELECT rule_id, discipline, confidence
                      FROM findings
                     WHERE finding_id = ANY(%s)
                     ORDER BY confidence""",
                (result.unmatched_finding_ids,),
            ).fetchall()
        print(f"\nTrue false positives ({len(result.unmatched_finding_ids)}):")
        for row in fp_rows:
            print(f"  {row['discipline']:<20} {row['rule_id']:<35} conf={row['confidence']:.2f}")
    else:
        print("No true false positives.")


if __name__ == "__main__":
    main()
