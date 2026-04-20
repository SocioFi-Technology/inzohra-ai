"""PlanSetPipeline - ingest a plan-set PDF end-to-end.

Responsibilities (Phase 00):
  1. Hash (SHA-256) + dedupe by content_hash.
  2. Upload raw PDF to ``inzohra-raw``.
  3. Rasterize every page at two DPIs; upload to ``inzohra-raster``.
  4. Insert ``documents`` + ``sheets`` rows.
  5. Run ``TitleBlockAgent`` on every page; persist entities.
  6. Append llm_call_log rows.

Invariants upheld:
  - Append-only: re-running with the same file creates no new rows (deduped).
  - Every entity carries extractor_version, bbox, confidence, source_track.
  - LLM calls are logged to llm_call_log.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import psycopg
from psycopg.types.json import Jsonb

from inzohra_shared.s3 import S3Config, make_s3_client, upload_bytes, upload_file
from app.extractors.title_block import (
    VERSION as TB_VERSION,
    extract_title_block,
)
from app.extractors.sheet_identifier import (
    VERSION as SID_VERSION,
    extract_sheet_identifier,
)
from app.extractors.sheet_index import (
    VERSION as SIX_VERSION,
    extract_sheet_index,
)
from app.extractors.schedule import (
    VERSION as SCH_VERSION,
    extract_schedules,
)
from app.extractors.code_note import (
    VERSION as CN_VERSION,
    extract_code_notes,
)


# ---------------------------------------------------------------------------
# Config dataclass (all values injected by caller)
# ---------------------------------------------------------------------------

@dataclass
class PipelineConfig:
    database_url: str
    s3: S3Config
    anthropic_api_key: str = ""
    model_primary: str = "claude-sonnet-4-5"
    thumb_dpi: int = 144
    extract_dpi: int = 300
    extractor_version: str = f"title_block:{TB_VERSION}+sid:{SID_VERSION}+six:{SIX_VERSION}+sch:{SCH_VERSION}+cn:{CN_VERSION}"


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    document_id: str
    project_id: str
    submittal_id: str
    sheets: list[dict[str, Any]] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)
    skipped: bool = False  # True if deduped


# ---------------------------------------------------------------------------
# DB helpers (synchronous psycopg3)
# ---------------------------------------------------------------------------

def _get_sync_conn(database_url: str) -> psycopg.Connection:  # type: ignore[type-arg]
    return psycopg.connect(database_url, row_factory=psycopg.rows.dict_row)


def _ensure_bootstrap_tenant(conn: psycopg.Connection) -> str:  # type: ignore[type-arg]
    """Return the ID of the bootstrap tenant, creating it if absent."""
    BOOTSTRAP_TENANT_ID = "00000000-0000-0000-0000-000000000001"
    cur = conn.execute(
        "SELECT tenant_id FROM tenants WHERE tenant_id = %s",
        (BOOTSTRAP_TENANT_ID,),
    )
    if cur.fetchone() is None:
        conn.execute(
            "INSERT INTO tenants (tenant_id, name, kind) VALUES (%s, %s, %s)",
            (BOOTSTRAP_TENANT_ID, "Bootstrap Tenant", "reviewer_firm"),
        )
    return BOOTSTRAP_TENANT_ID


def _ensure_project(
    conn: psycopg.Connection,  # type: ignore[type-arg]
    tenant_id: str,
    *,
    address: str,
    permit_number: str,
    jurisdiction: str,
    effective_date: str,
    apn: str | None = None,
) -> str:
    cur = conn.execute(
        "SELECT project_id FROM projects WHERE permit_number = %s AND jurisdiction = %s",
        (permit_number, jurisdiction),
    )
    row = cur.fetchone()
    if row:
        return str(row["project_id"])

    project_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO projects
             (project_id, tenant_id, address, apn, permit_number, jurisdiction, effective_date)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (project_id, tenant_id, address, apn, permit_number, jurisdiction, effective_date),
    )
    return project_id


def _ensure_submittal(
    conn: psycopg.Connection,  # type: ignore[type-arg]
    project_id: str,
    *,
    received_at: str,
) -> str:
    cur = conn.execute(
        "SELECT submittal_id FROM submittals WHERE project_id = %s AND round_number = 1 AND kind = 'initial'",
        (project_id,),
    )
    row = cur.fetchone()
    if row:
        return str(row["submittal_id"])

    submittal_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO submittals (submittal_id, project_id, round_number, kind, received_at)
           VALUES (%s, %s, 1, 'initial', %s)""",
        (submittal_id, project_id, received_at),
    )
    return submittal_id


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _doc_exists(conn: psycopg.Connection, content_hash: str) -> str | None:  # type: ignore[type-arg]
    cur = conn.execute(
        "SELECT document_id FROM documents WHERE content_hash = %s",
        (content_hash,),
    )
    row = cur.fetchone()
    return str(row["document_id"]) if row else None


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_plan_set_pipeline(
    pdf_path: str,
    *,
    project_id: str,
    submittal_id: str,
    cfg: PipelineConfig,
    canonical_address: str,
) -> PipelineResult:
    """Ingest one plan-set PDF.  Idempotent - safe to re-run.

    Args:
        pdf_path: Absolute path to the plan-set PDF on disk.
        project_id: Pre-created project UUID.
        submittal_id: Pre-created submittal UUID.
        cfg: Pipeline configuration.
        canonical_address: The project's canonical address string (used for
            title-block address-mismatch detection).

    Returns:
        ``PipelineResult`` with all created rows.
    """
    s3 = make_s3_client(cfg.s3)
    result = PipelineResult(
        document_id="",
        project_id=project_id,
        submittal_id=submittal_id,
    )

    content_hash = _hash_file(pdf_path)

    with _get_sync_conn(cfg.database_url) as conn:
        # --- dedupe ---
        existing_doc_id = _doc_exists(conn, content_hash)
        if existing_doc_id:
            print(f"[pipeline] PDF already ingested (doc_id={existing_doc_id}). Skipping.")
            result.document_id = existing_doc_id
            result.skipped = True
            return result

        document_id = str(uuid.uuid4())
        result.document_id = document_id

        # --- upload raw PDF ---
        raw_key = f"{document_id}/original.pdf"
        print(f"[pipeline] Uploading raw PDF -> {cfg.s3.bucket_raw}/{raw_key}")
        upload_file(s3, cfg.s3.bucket_raw, raw_key, pdf_path, content_type="application/pdf")
        s3_uri = f"s3://{cfg.s3.bucket_raw}/{raw_key}"

        # --- open PDF ---
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        print(f"[pipeline] PDF has {page_count} pages")

        # --- insert document row ---
        conn.execute(
            """INSERT INTO documents
                 (document_id, submittal_id, doc_type, content_hash, s3_uri, filename,
                  page_count, extractor_version)
               VALUES (%s, %s, 'plan_set', %s, %s, %s, %s, %s)""",
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

        # --- per-page rasterisation + sheet rows ---
        all_call_logs: list[dict[str, Any]] = []

        for page_index in range(page_count):
            page_number = page_index + 1  # 1-indexed in DB
            page = doc[page_index]
            print(f"[pipeline] Processing page {page_number}/{page_count} …")

            # Rasterize thumb
            thumb_mat = fitz.Matrix(cfg.thumb_dpi / 72, cfg.thumb_dpi / 72)
            thumb_pix = page.get_pixmap(matrix=thumb_mat, alpha=False)
            thumb_png = thumb_pix.tobytes("png")
            thumb_key = f"{document_id}/p{page_number:03d}/thumb.png"
            thumb_uri = upload_bytes(s3, cfg.s3.bucket_raster, thumb_key, thumb_png, "image/png")

            # Rasterize extract
            extract_mat = fitz.Matrix(cfg.extract_dpi / 72, cfg.extract_dpi / 72)
            extract_pix = page.get_pixmap(matrix=extract_mat, alpha=False)
            extract_png = extract_pix.tobytes("png")
            extract_key = f"{document_id}/p{page_number:03d}/extract.png"
            extract_uri = upload_bytes(
                s3, cfg.s3.bucket_raster, extract_key, extract_png, "image/png"
            )

            sheet_id = f"{document_id}:p{page_number:03d}"
            page_w = page.rect.width
            page_h = page.rect.height

            conn.execute(
                """INSERT INTO sheets
                     (sheet_id, project_id, document_id, page, thumb_uri, extract_raster_uri,
                      page_width_pts, page_height_pts)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (sheet_id) DO NOTHING""",
                (
                    sheet_id,
                    project_id,
                    document_id,
                    page_number,
                    thumb_uri,
                    extract_uri,
                    page_w,
                    page_h,
                ),
            )

            result.sheets.append(
                {
                    "sheet_id": sheet_id,
                    "page": page_number,
                    "page_width_pts": page_w,
                    "page_height_pts": page_h,
                    "thumb_uri": thumb_uri,
                    "extract_uri": extract_uri,
                }
            )

            # --- TitleBlockAgent ---
            call_logs: list[dict[str, Any]] = []
            tb = extract_title_block(
                page,
                api_key=cfg.anthropic_api_key,
                model=cfg.model_primary,
                canonical_address=canonical_address,
                call_log_rows=call_logs,
            )
            all_call_logs.extend(call_logs)

            entity_id = str(uuid.uuid4())
            payload = Jsonb(tb.to_entity_payload())

            # Compute overall entity confidence = mean of non-zero field confidences
            field_confidences = [
                f.confidence
                for f in [
                    tb.project_name, tb.project_address, tb.apn, tb.permit_number,
                    tb.sheet_identifier_raw, tb.sheet_title,
                ]
                if f.confidence > 0
            ]
            entity_confidence = (
                sum(field_confidences) / len(field_confidences) if field_confidences else 0.0
            )

            # Composite bbox = union of all non-zero field bboxes
            all_bboxes = [
                f.bbox
                for f in [
                    tb.project_name, tb.project_address, tb.apn, tb.permit_number,
                    tb.sheet_identifier_raw, tb.sheet_title,
                ]
                if f.bbox and f.bbox != [0.0, 0.0, 0.0, 0.0]
            ]
            if all_bboxes:
                entity_bbox = [
                    min(b[0] for b in all_bboxes),
                    min(b[1] for b in all_bboxes),
                    max(b[2] for b in all_bboxes),
                    max(b[3] for b in all_bboxes),
                ]
            else:
                entity_bbox = [0.0, 0.0, page_w, page_h * 0.35]

            conn.execute(
                """INSERT INTO entities
                     (entity_id, project_id, document_id, sheet_id, type, payload,
                      bbox, page, extractor_version, confidence, source_track)
                   VALUES (%s, %s, %s, %s, 'title_block', %s, %s, %s, %s, %s, %s)""",
                (
                    entity_id,
                    project_id,
                    document_id,
                    sheet_id,
                    payload,
                    entity_bbox,
                    page_number,
                    cfg.extractor_version,
                    entity_confidence,
                    "merged" if cfg.anthropic_api_key and not cfg.anthropic_api_key.startswith("sk-ant-xxx") else "text",
                ),
            )

            result.entities.append(
                {
                    "entity_id": entity_id,
                    "sheet_id": sheet_id,
                    "page": page_number,
                    "title_block": tb.model_dump(),
                }
            )

            # --- SheetIdentifierParser (deterministic) ---
            sid = extract_sheet_identifier(tb)
            sid_payload = Jsonb(sid.to_entity_payload())
            sid_entity_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO entities
                     (entity_id, project_id, document_id, sheet_id, type, payload,
                      bbox, page, extractor_version, confidence, source_track)
                   VALUES (%s, %s, %s, %s, 'sheet_identifier', %s, %s, %s, %s, %s, 'merged')""",
                (
                    sid_entity_id,
                    project_id,
                    document_id,
                    sheet_id,
                    sid_payload,
                    sid.bbox if sid.bbox and sid.bbox != [0.0, 0.0, 0.0, 0.0] else entity_bbox,
                    page_number,
                    f"sheet_identifier:{SID_VERSION}",
                    sid.confidence,
                ),
            )

            # Update sheets row with the canonical identity + declared scale
            declared_scale = tb.scale_declared.value if tb.scale_declared else None
            conn.execute(
                """UPDATE sheets
                      SET discipline_letter = %s,
                          sheet_number      = %s,
                          canonical_id      = %s,
                          sheet_type        = %s,
                          canonical_title   = %s,
                          declared_scale    = %s,
                          sheet_identifier_confidence = %s
                    WHERE sheet_id = %s""",
                (
                    sid.discipline_letter,
                    sid.sheet_number,
                    sid.canonical_id,
                    sid.sheet_type,
                    sid.sheet_title,
                    declared_scale,
                    sid.confidence,
                    sheet_id,
                ),
            )

            # --- SheetIndexAgent (cover sheets only) ---
            six_call_logs: list[dict[str, Any]] = []
            six = extract_sheet_index(
                page,
                source_sheet_id=sheet_id,
                canonical_id=sid.canonical_id,
                discipline_letter=sid.discipline_letter,
                sheet_title=sid.sheet_title,
                api_key=cfg.anthropic_api_key,
                model=cfg.model_primary,
                call_log_rows=six_call_logs,
            )
            all_call_logs.extend(six_call_logs)

            if six is not None and six.entries:
                # One entity per index + per-row sheet_index_entries rows for
                # easy SQL joins in rules.
                six_entity_id = str(uuid.uuid4())
                six_payload = Jsonb(six.to_entity_payload())
                # Index bbox = union of all entry bboxes
                idx_bboxes = [
                    e.bbox for e in six.entries
                    if e.bbox and e.bbox != [0.0, 0.0, 0.0, 0.0]
                ]
                if idx_bboxes:
                    index_bbox = [
                        min(b[0] for b in idx_bboxes),
                        min(b[1] for b in idx_bboxes),
                        max(b[2] for b in idx_bboxes),
                        max(b[3] for b in idx_bboxes),
                    ]
                else:
                    index_bbox = [0.0, 0.0, page_w, page_h]

                conn.execute(
                    """INSERT INTO entities
                         (entity_id, project_id, document_id, sheet_id, type, payload,
                          bbox, page, extractor_version, confidence, source_track)
                       VALUES (%s, %s, %s, %s, 'sheet_index', %s, %s, %s, %s, %s, 'vision')""",
                    (
                        six_entity_id,
                        project_id,
                        document_id,
                        sheet_id,
                        six_payload,
                        index_bbox,
                        page_number,
                        f"sheet_index:{SIX_VERSION}",
                        six.confidence,
                    ),
                )

                for entry in six.entries:
                    conn.execute(
                        """INSERT INTO sheet_index_entries
                             (project_id, document_id, source_sheet_id,
                              declared_id, declared_title, bbox,
                              extractor_version, confidence)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                        (
                            project_id,
                            document_id,
                            sheet_id,
                            entry.declared_id,
                            entry.declared_title,
                            entry.bbox,
                            f"sheet_index:{SIX_VERSION}",
                            entry.confidence,
                        ),
                    )

                result.entities.append({
                    "entity_id": six_entity_id,
                    "sheet_id": sheet_id,
                    "page": page_number,
                    "sheet_index": six.model_dump(),
                })

            # --- ScheduleAgent ---
            sch_call_logs: list[dict[str, Any]] = []
            schedules = extract_schedules(
                page,
                sheet_id=sheet_id,
                api_key=cfg.anthropic_api_key,
                model=cfg.model_primary,
                call_log_rows=sch_call_logs,
            )
            all_call_logs.extend(sch_call_logs)

            for sch in schedules:
                sch_entity_id = str(uuid.uuid4())
                sch_payload = Jsonb(sch.to_entity_payload())
                # Entity bbox = union of all row bboxes
                row_bboxes = [r.bbox for r in sch.rows if r.bbox and r.bbox != [0.0, 0.0, 0.0, 0.0]]
                if row_bboxes:
                    sch_bbox = [
                        min(b[0] for b in row_bboxes), min(b[1] for b in row_bboxes),
                        max(b[2] for b in row_bboxes), max(b[3] for b in row_bboxes),
                    ]
                else:
                    sch_bbox = [0.0, 0.0, page_w, page_h]

                conn.execute(
                    """INSERT INTO entities
                         (entity_id, project_id, document_id, sheet_id, type, payload,
                          bbox, page, extractor_version, confidence, source_track)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (sch_entity_id, project_id, document_id, sheet_id,
                     sch.schedule_type, sch_payload,
                     sch_bbox, page_number,
                     f"schedule:{SCH_VERSION}+{sch.extraction_method}",
                     sch.confidence,
                     "vision" if sch.extraction_method == "vision" else "text"),
                )

                # Insert individual schedule_rows
                for row in sch.rows:
                    conn.execute(
                        """INSERT INTO schedule_rows
                             (entity_id, project_id, schedule_type, row_index, tag,
                              payload, bbox, confidence, extractor_version)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (sch_entity_id, project_id, sch.schedule_type,
                         row.row_index, row.tag,
                         Jsonb(row.model_dump()),
                         row.bbox, row.confidence,
                         f"schedule:{SCH_VERSION}"),
                    )

                result.entities.append({
                    "entity_id": sch_entity_id,
                    "sheet_id": sheet_id,
                    "page": page_number,
                    "schedule": sch.model_dump(),
                })

            # --- CodeNoteAgent ---
            cn_call_logs: list[dict[str, Any]] = []
            code_notes = extract_code_notes(
                page,
                sheet_id=sheet_id,
                api_key=cfg.anthropic_api_key,
                model=cfg.model_primary,
                call_log_rows=cn_call_logs,
            )
            all_call_logs.extend(cn_call_logs)

            for cn in code_notes:
                cn_entity_id = str(uuid.uuid4())
                cn_payload = Jsonb(cn.to_entity_payload())
                conn.execute(
                    """INSERT INTO entities
                         (entity_id, project_id, document_id, sheet_id, type, payload,
                          bbox, page, extractor_version, confidence, source_track)
                       VALUES (%s, %s, %s, %s, 'code_note', %s, %s, %s, %s, %s, 'text')""",
                    (cn_entity_id, project_id, document_id, sheet_id,
                     cn_payload, [0.0, 0.0, page_w, page_h],
                     page_number, f"code_note:{CN_VERSION}", cn.confidence),
                )
                result.entities.append({
                    "entity_id": cn_entity_id,
                    "sheet_id": sheet_id,
                    "page": page_number,
                    "code_note": cn.model_dump(),
                })

        # --- persist llm_call_log rows ---
        for log in all_call_logs:
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

    return result
