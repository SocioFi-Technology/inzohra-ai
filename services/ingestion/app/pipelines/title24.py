"""Title24Pipeline — ingest one Title 24 energy compliance PDF end-to-end.

Responsibilities:
  1. SHA-256 hash + dedupe by content_hash.
  2. Upload raw PDF to ``inzohra-raw/{document_id}/original.pdf``.
  3. Insert ``documents`` row (doc_type='title24_report').
  4. Run Title24FormAgent; insert ONE document-level ``entities`` row.
  5. Persist llm_call_log rows.
  6. Commit.

Invariants upheld:
  - Append-only: re-running with the same file creates no new rows (deduped).
  - Entity carries extractor_version, bbox, confidence, source_track.
  - LLM calls are logged to llm_call_log.
  - sheet_id is explicitly NULL (document-level entity, not sheet-level).
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
import psycopg
import psycopg.rows
from psycopg.types.json import Jsonb

from inzohra_shared.s3 import S3Config, make_s3_client, upload_file
from app.extractors.title24_form import VERSION, extract_title24_form


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class Title24Config:
    database_url: str
    s3: S3Config
    anthropic_api_key: str = ""
    model_primary: str = "claude-sonnet-4-5"
    extractor_version: str = f"title24_form:{VERSION}"


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class Title24PipelineResult:
    document_id: str
    project_id: str
    submittal_id: str
    entity_id: str = ""
    skipped: bool = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _hash_file(path: str) -> str:
    """Return the SHA-256 hex digest of the file at ``path``."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _doc_exists(
    conn: psycopg.Connection,  # type: ignore[type-arg]
    content_hash: str,
) -> str | None:
    """Return the existing document_id if this hash is already in the DB, else None."""
    cur = conn.execute(
        "SELECT document_id FROM documents WHERE content_hash = %s",
        (content_hash,),
    )
    row = cur.fetchone()
    return str(row["document_id"]) if row else None


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_title24_pipeline(
    pdf_path: str,
    *,
    project_id: str,
    submittal_id: str,
    cfg: Title24Config,
) -> Title24PipelineResult:
    """Ingest one Title 24 energy compliance PDF.  Idempotent — safe to re-run.

    Args:
        pdf_path: Absolute path to the Title 24 PDF on disk.
        project_id: Pre-created project UUID.
        submittal_id: Pre-created submittal UUID.
        cfg: Pipeline configuration.

    Returns:
        ``Title24PipelineResult`` with document_id and entity_id populated,
        or ``skipped=True`` if the file was already ingested.
    """
    result = Title24PipelineResult(
        document_id="",
        project_id=project_id,
        submittal_id=submittal_id,
    )

    # --- Step 1: hash + dedup ---
    content_hash = _hash_file(pdf_path)

    with psycopg.connect(cfg.database_url, row_factory=psycopg.rows.dict_row) as conn:

        existing_doc_id = _doc_exists(conn, content_hash)
        if existing_doc_id:
            print(f"[title24_pipeline] PDF already ingested (doc_id={existing_doc_id}). Skipping.")
            result.document_id = existing_doc_id
            result.skipped = True
            return result

        document_id = str(uuid.uuid4())
        result.document_id = document_id

        # --- Step 2: upload raw PDF ---
        s3 = make_s3_client(cfg.s3)
        raw_key = f"{document_id}/original.pdf"
        print(f"[title24_pipeline] Uploading raw PDF -> {cfg.s3.bucket_raw}/{raw_key}")
        upload_file(
            s3,
            cfg.s3.bucket_raw,
            raw_key,
            pdf_path,
            content_type="application/pdf",
        )
        s3_uri = f"s3://{cfg.s3.bucket_raw}/{raw_key}"

        # --- Step 3: insert documents row ---
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        print(f"[title24_pipeline] PDF has {page_count} page(s)")

        conn.execute(
            """INSERT INTO documents
                 (document_id, submittal_id, doc_type, content_hash, s3_uri, filename,
                  page_count, extractor_version)
               VALUES (%s, %s, 'title24_report', %s, %s, %s, %s, %s)""",
            (
                document_id,
                submittal_id,
                content_hash,
                s3_uri,
                Path(pdf_path).name,
                page_count,
                cfg.extractor_version,
            ),
        )

        # --- Step 4: run Title24FormAgent ---
        call_log_rows: list[dict] = []
        print("[title24_pipeline] Running Title24FormAgent …")
        extraction = extract_title24_form(
            doc,
            api_key=cfg.anthropic_api_key,
            model=cfg.model_primary,
            call_log_rows=call_log_rows,
        )
        doc.close()

        print(
            f"[title24_pipeline] Extraction complete: form_type={extraction.form_type!r}, "
            f"compliance={extraction.compliance_result!r}, "
            f"surfaces={len(extraction.envelope_surfaces)}, "
            f"confidence={extraction.confidence:.2f}"
        )

        # --- Step 5: insert entities row (document-level, sheet_id=NULL) ---
        entity_id = str(uuid.uuid4())
        payload = extraction.to_entity_payload()

        conn.execute(
            """INSERT INTO entities
                 (entity_id, project_id, document_id, sheet_id, type, payload,
                  bbox, page, extractor_version, confidence, source_track)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                entity_id,
                project_id,
                document_id,
                None,                          # sheet_id explicitly NULL
                "title24_form",
                Jsonb(payload),
                [0.0, 0.0, 0.0, 0.0],
                1,
                cfg.extractor_version,
                extraction.confidence,
                "merged",
            ),
        )
        result.entity_id = entity_id

        # --- Step 6: persist llm_call_log rows ---
        for log in call_log_rows:
            conn.execute(
                """INSERT INTO llm_call_log
                     (call_id, prompt_hash, model, tokens_in, tokens_out,
                      latency_ms, cost_usd, caller_service)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    log["call_id"],
                    log["prompt_hash"],
                    log["model"],
                    log["tokens_in"],
                    log["tokens_out"],
                    log["latency_ms"],
                    log["cost_usd"],
                    log["caller_service"],
                ),
            )

        # --- Step 7: commit ---
        conn.commit()
        print(f"[title24_pipeline] Committed. entity_id={entity_id}")

    return result
