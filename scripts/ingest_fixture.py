#!/usr/bin/env python
"""Fixture ingestion smoke script.

Usage::

    uv run scripts/ingest_fixture.py

Uploads ``fixtures/2008-dennis-ln/plan-set.pdf``, creates the project if it
does not exist, runs the plan-set pipeline, and prints a summary of extracted
sheet identifiers and title-block bboxes.

Reads all config from environment / .env at repo root.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Load .env before any other imports that read env vars
# ---------------------------------------------------------------------------
from dotenv import load_dotenv

_repo_root = Path(__file__).resolve().parent.parent
load_dotenv(_repo_root / ".env")

# ---------------------------------------------------------------------------
# Now safe to import project code
# ---------------------------------------------------------------------------
import psycopg
import psycopg.rows

from inzohra_shared.s3 import S3Config
from app.pipelines.plan_set import (
    PipelineConfig,
    _ensure_bootstrap_tenant,
    _ensure_project,
    _ensure_submittal,
    run_plan_set_pipeline,
)

# ---------------------------------------------------------------------------
# Fixture constants
# ---------------------------------------------------------------------------
FIXTURE_PDF = _repo_root / "fixtures" / "2008-dennis-ln" / "plan-set.pdf"
CANONICAL_ADDRESS = "2008 Dennis Ln, Santa Rosa, CA"
PERMIT_NUMBER = "B25-2734"
JURISDICTION = "santa_rosa"
EFFECTIVE_DATE = "2025-01-01"  # Project permitted 2025-03-15; use start of year


def main() -> None:
    # --- validate fixture exists ---
    if not FIXTURE_PDF.exists():
        print(f"ERROR: fixture not found at {FIXTURE_PDF}")
        sys.exit(1)

    database_url = os.environ["DATABASE_URL"]
    s3_cfg = S3Config(
        endpoint=os.environ["S3_ENDPOINT"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    # --- ensure project hierarchy ---
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

    print(f"\n{'='*60}")
    print(f"Project ID   : {project_id}")
    print(f"Submittal ID : {submittal_id}")
    print(f"PDF          : {FIXTURE_PDF}")
    print(f"{'='*60}\n")

    cfg = PipelineConfig(
        database_url=database_url,
        s3=s3_cfg,
        anthropic_api_key=api_key,
    )

    # --- run pipeline ---
    result = run_plan_set_pipeline(
        str(FIXTURE_PDF),
        project_id=project_id,
        submittal_id=submittal_id,
        cfg=cfg,
        canonical_address=CANONICAL_ADDRESS,
    )

    if result.skipped:
        print("Document already ingested. No-op.")
        _print_existing_results(database_url, result.document_id)
        return

    # --- print results ---
    print(f"\n[OK] Ingested {len(result.sheets)} sheets, {len(result.entities)} title-block entities")
    print(f"  Document ID: {result.document_id}\n")

    address_ok = 0
    address_mismatch_sheets: list[str] = []

    for ent in result.entities:
        tb = ent["title_block"]
        sheet_id = ent["sheet_id"]
        page = ent["page"]
        addr = tb.get("project_address", {}).get("value") or "(none)"
        sheet_raw = tb.get("sheet_identifier_raw", {}).get("value") or "(none)"
        addr_conf = tb.get("project_address", {}).get("confidence", 0)
        mismatch = tb.get("address_mismatch", False)

        flag = "[MISMATCH]" if mismatch else "[OK]"
        print(f"  p{page:02d} [{sheet_raw:12s}]  addr={addr!r:40s}  conf={addr_conf:.2f}  {flag}")

        if not mismatch and addr and "dennis" in addr.lower():
            address_ok += 1
        elif mismatch:
            address_mismatch_sheets.append(f"p{page} ({addr!r})")

    print(f"\n  Address OK : {address_ok}/{len(result.entities)}")
    if address_mismatch_sheets:
        print(f"  Mismatches : {', '.join(address_mismatch_sheets)}")

    print(f"\n  Sheet viewer: http://localhost:3000/projects/{project_id}/sheets/")
    print(f"  First sheet : http://localhost:3000/projects/{project_id}/sheets/{result.document_id}:p001\n")


def _print_existing_results(database_url: str, document_id: str) -> None:
    """Print a summary from the DB when the document was already ingested."""
    conn = psycopg.connect(database_url, row_factory=psycopg.rows.dict_row)
    try:
        rows = conn.execute(
            """SELECT e.page, e.confidence,
                      e.payload->>'project_address' as addr_json,
                      e.payload->>'sheet_identifier_raw' as sid_json
               FROM entities e
               WHERE e.document_id = %s AND e.type = 'title_block'
               ORDER BY e.page""",
            (document_id,),
        ).fetchall()
        print(f"  Found {len(rows)} entities in DB for doc {document_id}")
        for r in rows:
            print(f"  p{r['page']:02d}  conf={r['confidence']:.2f}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
