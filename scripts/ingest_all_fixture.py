#!/usr/bin/env python
"""Ingest ALL fixture documents for 2008 Dennis Ln (B25-2734).

Runs in order:
  1. plan-set.pdf       → PlanSetPipeline
  2. title24-report.pdf → Title24Pipeline
  3. expected-bv-letter.pdf → ReviewLetterPipeline
  4. fire-review.pdf    → ReviewLetterPipeline (fire review doc)

Usage:
    uv run scripts/ingest_all_fixture.py
    uv run scripts/ingest_all_fixture.py --skip-planset  # if plan-set already ingested

Reads config from .env at repo root.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_repo_root = Path(__file__).resolve().parent.parent
load_dotenv(_repo_root / ".env", override=True)

sys.path.insert(0, str(_repo_root / "services" / "ingestion"))
sys.path.insert(0, str(_repo_root / "services" / "review"))
sys.path.insert(0, str(_repo_root / "packages" / "shared-py"))

import psycopg
import psycopg.rows

from inzohra_shared.s3 import S3Config
from app.pipelines.plan_set import (
    PipelineConfig as PlanSetConfig,
    _ensure_bootstrap_tenant,
    _ensure_project,
    _ensure_submittal,
    run_plan_set_pipeline,
)
from app.pipelines.title24 import Title24Config, run_title24_pipeline
from app.pipelines.review_letter import ReviewLetterConfig, run_review_letter_pipeline

# ---------------------------------------------------------------------------
# Fixture constants
# ---------------------------------------------------------------------------

FIXTURE_DIR = _repo_root / "fixtures" / "2008-dennis-ln"
CANONICAL_ADDRESS = "2008 Dennis Ln, Santa Rosa, CA"
PERMIT_NUMBER = "B25-2734"
JURISDICTION = "santa_rosa"
EFFECTIVE_DATE = "2025-01-01"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest all fixture documents for 2008 Dennis Ln (B25-2734)."
    )
    parser.add_argument(
        "--skip-planset",
        action="store_true",
        help="Skip plan-set ingestion (use when it was already ingested in a prior run).",
    )
    args = parser.parse_args()

    # Validate fixture files
    fixture_files = {
        "plan-set": FIXTURE_DIR / "plan-set.pdf",
        "title24": FIXTURE_DIR / "title24-report.pdf",
        "bv-letter": FIXTURE_DIR / "expected-bv-letter.pdf",
        "fire-review": FIXTURE_DIR / "fire-review.pdf",
    }
    missing = [name for name, path in fixture_files.items() if not path.exists()]
    if missing:
        print(f"ERROR: Missing fixture files: {', '.join(missing)}")
        print(f"  Expected under: {FIXTURE_DIR}")
        sys.exit(1)

    # Read config from env
    database_url = os.environ["DATABASE_URL"]
    s3_cfg = S3Config(
        endpoint=os.environ["S3_ENDPOINT"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    # Ensure project hierarchy
    print(f"\n{'='*60}")
    print("Ingest All Fixture — 2008 Dennis Ln (B25-2734)")
    print(f"{'='*60}")
    print("Setting up project hierarchy...")

    conn = psycopg.connect(database_url, row_factory=psycopg.rows.dict_row)
    try:
        tenant_id = _ensure_bootstrap_tenant(conn)
        project_id = _ensure_project(
            conn,
            tenant_id,
            address=CANONICAL_ADDRESS,
            permit_number=PERMIT_NUMBER,
            jurisdiction=JURISDICTION,
            effective_date=EFFECTIVE_DATE,
            apn="022-211-012",
        )
        submittal_id = _ensure_submittal(
            conn, project_id, received_at="2025-03-15T00:00:00Z"
        )
        conn.commit()
    finally:
        conn.close()

    print(f"  Project ID   : {project_id}")
    print(f"  Submittal ID : {submittal_id}")
    print()

    # Shared configs
    planset_cfg = PlanSetConfig(
        database_url=database_url,
        s3=s3_cfg,
        anthropic_api_key=api_key,
    )
    title24_cfg = Title24Config(
        database_url=database_url,
        s3=s3_cfg,
        anthropic_api_key=api_key,
    )
    review_letter_cfg = ReviewLetterConfig(
        database_url=database_url,
        s3=s3_cfg,
        anthropic_api_key=api_key,
    )

    # -----------------------------------------------------------------------
    # Step 1: Plan set
    # -----------------------------------------------------------------------
    if args.skip_planset:
        print("[1/4] plan-set.pdf — SKIPPED (--skip-planset)")
    else:
        print("[1/4] plan-set.pdf — ingesting...")
        ps_result = run_plan_set_pipeline(
            str(fixture_files["plan-set"]),
            project_id=project_id,
            submittal_id=submittal_id,
            cfg=planset_cfg,
            canonical_address=CANONICAL_ADDRESS,
        )
        if ps_result.skipped:
            print("       Already ingested — no-op.")
        else:
            print(
                f"       OK: {len(ps_result.sheets)} sheets, "
                f"{len(ps_result.entities)} title-block entities  "
                f"(doc={ps_result.document_id})"
            )

    # -----------------------------------------------------------------------
    # Step 2: Title 24 report
    # -----------------------------------------------------------------------
    print("[2/4] title24-report.pdf — ingesting...")
    t24_result = run_title24_pipeline(
        str(fixture_files["title24"]),
        project_id=project_id,
        submittal_id=submittal_id,
        cfg=title24_cfg,
    )
    if t24_result.skipped:
        print("       Already ingested — no-op.")
    else:
        print(
            f"       OK: entity_id={t24_result.entity_id}  "
            f"(doc={t24_result.document_id})"
        )

    # -----------------------------------------------------------------------
    # Step 3: BV plan-check letter
    # -----------------------------------------------------------------------
    print("[3/4] expected-bv-letter.pdf — ingesting...")
    bv_result = run_review_letter_pipeline(
        str(fixture_files["bv-letter"]),
        project_id=project_id,
        submittal_id=submittal_id,
        cfg=review_letter_cfg,
    )
    if bv_result.skipped:
        print("       Already ingested — no-op.")
    else:
        print(
            f"       OK: {bv_result.comment_count} comments inserted  "
            f"(doc={bv_result.document_id})"
        )

    # -----------------------------------------------------------------------
    # Step 4: Fire review memo
    # -----------------------------------------------------------------------
    print("[4/4] fire-review.pdf — ingesting...")
    fire_result = run_review_letter_pipeline(
        str(fixture_files["fire-review"]),
        project_id=project_id,
        submittal_id=submittal_id,
        cfg=review_letter_cfg,
    )
    if fire_result.skipped:
        print("       Already ingested — no-op.")
    else:
        print(
            f"       OK: {fire_result.comment_count} comments inserted  "
            f"(doc={fire_result.document_id})"
        )

    # -----------------------------------------------------------------------
    # Step 5: Cross-doc claims
    # -----------------------------------------------------------------------
    print("[5/5] Building cross-doc claims...")
    # Import here so the services/review sys.path is already set up above
    from app.reconciliation.cross_doc import run_cross_doc_claims  # noqa: PLC0415

    xd = run_cross_doc_claims(database_url, project_id)
    print(
        f"       Claims inserted: {xd.claims_inserted}, "
        f"conflicts found: {xd.conflicts_found}"
    )

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("Summary")
    print(f"{'='*60}")
    print(f"  Project ID   : {project_id}")
    print(f"  Submittal ID : {submittal_id}")
    if not args.skip_planset:
        plan_sheets = getattr(ps_result, "sheets", [])
        plan_skipped = getattr(ps_result, "skipped", False)
        print(f"  Plan sheets  : {'(skipped — already ingested)' if plan_skipped else len(plan_sheets)}")
    t24_skipped = getattr(t24_result, "skipped", False)
    print(f"  T24 entity   : {'(skipped)' if t24_skipped else t24_result.entity_id}")
    bv_comments = getattr(bv_result, "comment_count", 0)
    fire_comments = getattr(fire_result, "comment_count", 0)
    print(f"  BV comments  : {bv_comments}")
    print(f"  Fire comments: {fire_comments}")
    print(f"  Cross-doc    : {xd.claims_inserted} claims, {xd.conflicts_found} conflicts")
    print()
    print(f"  Viewer: http://localhost:3000/projects/{project_id}/sheets/")
    print()


if __name__ == "__main__":
    main()
