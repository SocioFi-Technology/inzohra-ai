#!/usr/bin/env python
"""Run MEP, Structural, Energy, Fire/Life Safety, CalGreen reviewers on fixture.

Usage::
    uv run scripts/run_mep_structural_review.py [--project-id <uuid>] [--round <n>]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent
from dotenv import load_dotenv

load_dotenv(_repo_root / ".env", override=True)

import psycopg
import psycopg.rows

from app.reviewers.mechanical import MechanicalReviewer
from app.reviewers.electrical import ElectricalReviewer
from app.reviewers.plumbing import PlumbingReviewer
from app.reviewers.structural import StructuralReviewer
from app.reviewers.energy import EnergyReviewer
from app.reviewers.fire_life_safety import FireLifeSafetyReviewer
from app.reviewers.calgreen import CalGreenReviewer

DISCIPLINES = [
    "mechanical",
    "electrical",
    "plumbing",
    "structural",
    "energy",
    "fire_life_safety",
    "calgreen",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Phase 05 MEP/Structural/Energy/Fire/CalGreen reviewers on fixture."
    )
    parser.add_argument("--project-id", default=None, help="Override fixture project UUID")
    parser.add_argument("--round", type=int, default=1, help="Review round number (default: 1)")
    args = parser.parse_args()

    database_url = os.environ["DATABASE_URL"]
    anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")

    conn = psycopg.connect(database_url, row_factory=psycopg.rows.dict_row)

    try:
        # ------------------------------------------------------------------
        # Resolve project / submittal
        # ------------------------------------------------------------------
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
            print("ERROR: no submittal found for project")
            sys.exit(1)
        submittal_id = str(sub_row["submittal_id"])

        print(f"project_id  = {project_id}")
        print(f"submittal_id= {submittal_id}")
        print(f"round       = {args.round}")
        print()

        # ------------------------------------------------------------------
        # Delete existing round-N findings for all Phase 05 disciplines
        # (idempotent re-run support)
        # ------------------------------------------------------------------
        for disc in DISCIPLINES:
            deleted = conn.execute(
                """DELETE FROM findings
                    WHERE project_id = %s AND review_round = %s AND discipline = %s""",
                (project_id, args.round, disc),
            ).rowcount
            if deleted:
                print(f"Deleted {deleted} existing {disc} findings for round {args.round}")

        # ------------------------------------------------------------------
        # Run each reviewer and collect finding IDs
        # ------------------------------------------------------------------
        totals: dict[str, int] = {}

        # Reviewers that are purely deterministic (no LLM, no anthropic_api_key)
        _det_reviewers: list[tuple[str, object]] = [
            ("mechanical",       MechanicalReviewer()),
            ("electrical",       ElectricalReviewer()),
            ("plumbing",         PlumbingReviewer()),
            ("structural",       StructuralReviewer()),
            ("fire_life_safety", FireLifeSafetyReviewer()),
            ("calgreen",         CalGreenReviewer()),
        ]
        for disc, reviewer in _det_reviewers:
            ids = reviewer.run(  # type: ignore[union-attr]
                conn,
                project_id=project_id,
                submittal_id=submittal_id,
                review_round=args.round,
                database_url=database_url,
            )
            totals[disc] = len(ids)
            print(f"{disc:<24}  {len(ids)} findings")

        # EnergyReviewer supports an optional LLM residue pass
        en_reviewer = EnergyReviewer()
        en_ids = en_reviewer.run(
            conn,
            project_id=project_id,
            submittal_id=submittal_id,
            review_round=args.round,
            database_url=database_url,
            anthropic_api_key=anthropic_api_key,
        )
        totals["energy"] = len(en_ids)
        print(f"{'energy':<24}  {len(en_ids)} findings")

        # ------------------------------------------------------------------
        # Commit and report
        # ------------------------------------------------------------------
        conn.commit()

        grand_total = sum(totals.values())
        print()
        print("Per-discipline summary:")
        for disc, count in totals.items():
            print(f"  {disc:<20} {count:>4} findings")
        print(f"  {'TOTAL':<20} {grand_total:>4} findings committed.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
