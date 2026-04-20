"""ReviewLetterPipeline — ingest a plan-check letter PDF end-to-end.

Responsibilities:
  1. Hash (SHA-256) + dedupe by content_hash.
  2. Upload raw PDF to ``inzohra-raw``.
  3. Insert ``documents`` row with doc_type='plan_check_letter'.
  4. Run ReviewLetterAgent; persist external_review_comments rows.
  5. Insert review_letter_summary entity into ``entities``.
  6. Persist llm_call_log rows.

Invariants upheld:
  - Append-only: re-running with the same file creates no new rows (deduped).
  - Every comment carries provenance: source_document_id, bbox, extractor_version.
  - LLM calls are logged to llm_call_log.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
import psycopg
import psycopg.rows
from psycopg.types.json import Jsonb

from inzohra_shared.s3 import S3Config, make_s3_client, upload_file

from app.extractors.review_letter import VERSION, extract_review_letter


# ---------------------------------------------------------------------------
# Config + Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ReviewLetterConfig:
    database_url: str
    s3: S3Config
    anthropic_api_key: str = ""
    model_primary: str = "claude-sonnet-4-5"
    extractor_version: str = f"review_letter:{VERSION}"


@dataclass
class ReviewLetterPipelineResult:
    document_id: str
    project_id: str
    submittal_id: str
    comment_count: int = 0
    skipped: bool = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _hash_file(path: str) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _doc_exists(
    conn: psycopg.Connection,  # type: ignore[type-arg]
    content_hash: str,
) -> str | None:
    """Return existing document_id if this content_hash is already in documents."""
    cur = conn.execute(
        "SELECT document_id FROM documents WHERE content_hash = %s",
        (content_hash,),
    )
    row = cur.fetchone()
    return str(row["document_id"]) if row else None


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_review_letter_pipeline(
    pdf_path: str,
    *,
    project_id: str,
    submittal_id: str,
    cfg: ReviewLetterConfig,
) -> ReviewLetterPipelineResult:
    """Ingest one plan-check letter PDF.  Idempotent — safe to re-run.

    Args:
        pdf_path: Absolute path to the plan-check letter PDF on disk.
        project_id: Pre-created project UUID.
        submittal_id: Pre-created submittal UUID.
        cfg: Pipeline configuration.

    Returns:
        ReviewLetterPipelineResult with document_id and comment_count.
    """
    s3 = make_s3_client(cfg.s3)

    content_hash = _hash_file(pdf_path)

    with psycopg.connect(cfg.database_url, row_factory=psycopg.rows.dict_row) as conn:

        # --- Dedup: if content_hash already exists, skip ---
        existing_doc_id = _doc_exists(conn, content_hash)
        if existing_doc_id:
            print(
                f"[ReviewLetterPipeline] PDF already ingested "
                f"(doc_id={existing_doc_id}). Skipping."
            )
            return ReviewLetterPipelineResult(
                document_id=existing_doc_id,
                project_id=project_id,
                submittal_id=submittal_id,
                skipped=True,
            )

        document_id = str(uuid.uuid4())

        # --- Upload raw PDF ---
        raw_key = f"{document_id}/original.pdf"
        print(f"[ReviewLetterPipeline] Uploading raw PDF -> {cfg.s3.bucket_raw}/{raw_key}")
        upload_file(
            s3,
            cfg.s3.bucket_raw,
            raw_key,
            pdf_path,
            content_type="application/pdf",
        )
        s3_uri = f"s3://{cfg.s3.bucket_raw}/{raw_key}"

        # --- Open PDF with PyMuPDF ---
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        print(f"[ReviewLetterPipeline] PDF has {page_count} pages")

        # --- Insert documents row ---
        conn.execute(
            """INSERT INTO documents
                 (document_id, submittal_id, doc_type, content_hash,
                  s3_uri, filename, page_count, extractor_version)
               VALUES (%s, %s, 'plan_check_letter', %s, %s, %s, %s, %s)""",
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

        # --- Run ReviewLetterAgent ---
        call_log_rows: list[dict[str, object]] = []
        extraction = extract_review_letter(
            doc,
            api_key=cfg.anthropic_api_key,
            model=cfg.model_primary,
            call_log_rows=call_log_rows,
        )
        print(
            f"[ReviewLetterPipeline] Extraction complete: "
            f"{extraction.total_comment_count} comments, "
            f"confidence={extraction.confidence:.2f}"
        )

        # --- Insert external_review_comments rows ---
        for comment in extraction.comments:
            external_comment_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO external_review_comments
                     (external_comment_id, project_id, submittal_id,
                      review_round, discipline, discipline_group,
                      comment_number, comment_text, citation_text,
                      sheet_reference, typography, source_document_id,
                      is_resolved)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false)""",
                (
                    external_comment_id,
                    project_id,
                    submittal_id,
                    comment.review_round,
                    comment.discipline,
                    comment.discipline_group,
                    comment.comment_number,
                    comment.comment_text,
                    comment.citation_text,
                    comment.sheet_reference,
                    comment.typography,
                    document_id,
                ),
            )

        # --- Insert review_letter_summary entity ---
        entity_id = str(uuid.uuid4())
        payload = Jsonb(extraction.to_entity_payload())
        conn.execute(
            """INSERT INTO entities
                 (entity_id, project_id, document_id, sheet_id, type,
                  payload, bbox, page, extractor_version, confidence,
                  source_track)
               VALUES (%s, %s, %s, NULL, 'review_letter_summary',
                       %s, %s, 1, %s, %s, 'text')""",
            (
                entity_id,
                project_id,
                document_id,
                payload,
                [0.0, 0.0, 0.0, 0.0],
                cfg.extractor_version,
                extraction.confidence,
            ),
        )

        # --- Persist llm_call_log rows ---
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

        conn.commit()

    return ReviewLetterPipelineResult(
        document_id=document_id,
        project_id=project_id,
        submittal_id=submittal_id,
        comment_count=extraction.total_comment_count,
        skipped=False,
    )
