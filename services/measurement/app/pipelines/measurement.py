"""MeasurementPipeline — orchestrates all measurement sub-agents for a submittal.

Runs per-project, per-submittal:
  1. Load all plan_set sheets for the project.
  2. For each sheet: classify PDF quality → update sheets.pdf_quality_class.
  3. Resolve scale per sheet → update sheets.calibrated_scale_ratio.
  4. Run FloorPlanGeometryAgent on architectural floor plan sheets.
  5. Insert extracted entities into the entities table.
  6. Compute DerivedMetrics (door width, window NCO, room area, egress distances).
  7. Insert measurements into the measurements table.
  8. Log LLM calls to llm_call_log.

Layer: 4 — Measurement (reads L1 storage, writes measurement rows back to L1).
Temperature: 0 on all LLM calls (enforced in FloorPlanGeometryAgent).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass, field

import fitz  # PyMuPDF
import psycopg
import psycopg.rows

from inzohra_shared.s3 import S3Config, make_s3_client
from inzohra_shared.schemas.measurement import FloorPlanEntity

from app.derived_metrics import (
    VERSION as DM_VERSION,
    compute_door_clear_width,
    compute_egress_distance,
    compute_room_area,
    compute_window_nco,
)
from app.floor_plan_geometry_agent import extract_floor_plan
from app.floor_plan_geometry_agent import VERSION as FP_VERSION
from app.pdf_quality import classify_page
from app.pdf_quality import VERSION as PQ_VERSION
from app.scale_resolver import SheetScaleResult, resolve_sheet_scale
from app.scale_resolver import VERSION as SR_VERSION

VERSION = "1.0.0"

logger = logging.getLogger(__name__)

# Sheet types that carry floor plan geometry useful for measurement.
_FLOOR_PLAN_SHEET_TYPES: frozenset[str] = frozenset(
    {"floor_plan", "site_plan", "elevation", "foundation", "reflected_ceiling"}
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class MeasurementPipelineResult:
    project_id: str
    submittal_id: str
    sheets_processed: int = 0
    entities_inserted: int = 0
    measurements_inserted: int = 0
    skipped_sheets: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Parse 's3://bucket/key' → (bucket, key)."""
    without_prefix = uri.removeprefix("s3://")
    bucket, _, key = without_prefix.partition("/")
    return bucket, key


def _insert_entity(
    conn: psycopg.Connection[dict[str, object]],
    *,
    project_id: str,
    document_id: str,
    sheet_id: str,
    entity: FloorPlanEntity,
    extractor_version: str,
    dry_run: bool,
) -> str:
    """Insert a FloorPlanEntity into the entities table and return its entity_id."""
    entity_id = str(uuid.uuid4())
    payload = json.dumps(entity.model_dump())

    if dry_run:
        logger.debug("[dry-run] Would insert entity %s type=%s tag=%s", entity_id, entity.entity_type, entity.tag)
        return entity_id

    conn.execute(
        """
        INSERT INTO entities
          (entity_id, project_id, document_id, sheet_id, type, payload, bbox, page,
           extractor_version, confidence, source_track)
        VALUES (%s, %s, %s, %s, 'floor_plan_entity', %s::jsonb, %s, %s, %s, %s, 'vision')
        """,
        (
            entity_id,
            project_id,
            document_id,
            sheet_id,
            payload,
            entity.bbox,
            entity.page,
            extractor_version,
            entity.confidence,
        ),
    )
    return entity_id


def _insert_measurement(
    conn: psycopg.Connection[dict[str, object]],
    *,
    project_id: str,
    result_row: dict[str, object],
    extractor_version: str,
    dry_run: bool,
) -> None:
    """Insert a MeasurementResult dict into the measurements table."""
    if dry_run:
        logger.debug(
            "[dry-run] Would insert measurement %s type=%s value=%.4f %s",
            result_row["measurement_id"],
            result_row["type"],
            result_row["value"],
            result_row["unit"],
        )
        return

    conn.execute(
        """
        INSERT INTO measurements
          (measurement_id, project_id, sheet_id, type, value, unit,
           confidence, trace, extractor_version, bbox, entity_id, tag)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
        """,
        (
            result_row["measurement_id"],
            project_id,
            result_row["sheet_id"],
            result_row["type"],
            result_row["value"],
            result_row["unit"],
            result_row["confidence"],
            json.dumps(result_row["trace"]),
            extractor_version,
            result_row.get("bbox"),
            result_row.get("entity_id"),
            result_row.get("tag"),
        ),
    )


def _insert_llm_call_logs(
    conn: psycopg.Connection[dict[str, object]],
    call_log_rows: list[dict[str, object]],
    dry_run: bool,
) -> None:
    """Bulk-insert LLM call log rows."""
    if not call_log_rows:
        return

    if dry_run:
        logger.debug("[dry-run] Would insert %d LLM call log rows", len(call_log_rows))
        return

    for row in call_log_rows:
        conn.execute(
            """
            INSERT INTO llm_call_log
              (call_id, prompt_hash, model, tokens_in, tokens_out, latency_ms,
               cost_usd, caller_service)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (call_id) DO NOTHING
            """,
            (
                row["call_id"],
                row["prompt_hash"],
                row["model"],
                row["tokens_in"],
                row["tokens_out"],
                row["latency_ms"],
                row["cost_usd"],
                row.get("caller_service", "measurement"),
            ),
        )


def _update_sheet_columns(
    conn: psycopg.Connection[dict[str, object]],
    sheet_id: str,
    *,
    pdf_quality_class: str | None,
    calibrated_scale_ratio: float | None,
    dry_run: bool,
) -> None:
    if dry_run:
        logger.debug(
            "[dry-run] Would update sheet %s: quality=%s scale=%.4f",
            sheet_id,
            pdf_quality_class,
            calibrated_scale_ratio or 0.0,
        )
        return

    conn.execute(
        """
        UPDATE sheets
        SET    pdf_quality_class     = COALESCE(%s, pdf_quality_class),
               calibrated_scale_ratio = COALESCE(%s, calibrated_scale_ratio)
        WHERE  sheet_id = %s
        """,
        (pdf_quality_class, calibrated_scale_ratio, sheet_id),
    )


# ---------------------------------------------------------------------------
# Public pipeline entry point
# ---------------------------------------------------------------------------

def run_measurement_pipeline(
    database_url: str,
    project_id: str,
    submittal_id: str,
    anthropic_api_key: str,
    *,
    dry_run: bool = False,
) -> MeasurementPipelineResult:
    """Run the full measurement pipeline for one submittal.

    Downloads PDF(s) from S3, runs FloorPlanGeometryAgent per sheet,
    inserts entities and measurements.  Returns a summary result.

    Parameters
    ----------
    database_url:
        psycopg-compatible connection string.
    project_id:
        UUID of the project row.
    submittal_id:
        UUID of the submittal row.
    anthropic_api_key:
        Passed directly to FloorPlanGeometryAgent; never read from env here.
    dry_run:
        If True, compute everything but skip all DB writes and S3 downloads.
    """
    result = MeasurementPipelineResult(
        project_id=project_id,
        submittal_id=submittal_id,
    )

    extractor_version = f"measurement-pipeline/{VERSION}+fp/{FP_VERSION}+dm/{DM_VERSION}"

    # S3 client — built once per pipeline run
    s3_cfg = S3Config(
        endpoint=os.environ.get("S3_ENDPOINT", ""),
        access_key=os.environ.get("S3_ACCESS_KEY", ""),
        secret_key=os.environ.get("S3_SECRET_KEY", ""),
    )
    s3_client = make_s3_client(s3_cfg) if not dry_run else None

    conn: psycopg.Connection[dict[str, object]] = psycopg.connect(
        database_url, row_factory=psycopg.rows.dict_row
    )

    try:
        # ----------------------------------------------------------------
        # 1. Load all plan_set sheets for this project / submittal
        # ----------------------------------------------------------------
        sheet_rows: list[dict[str, object]] = conn.execute(
            """
            SELECT s.sheet_id,
                   s.page,
                   s.sheet_type,
                   s.declared_scale,
                   s.pdf_quality_class,
                   s.page_width_pts,
                   s.page_height_pts,
                   d.document_id,
                   d.s3_uri,
                   d.filename
            FROM   sheets s
            JOIN   documents d  ON d.document_id = s.document_id
            JOIN   submittals sub ON sub.submittal_id = d.submittal_id
            WHERE  sub.project_id  = %s
              AND  d.doc_type      = 'plan_set'
            ORDER  BY s.page
            """,
            (project_id,),
        ).fetchall()

        if not sheet_rows:
            logger.warning(
                "MeasurementPipeline: no plan_set sheets found for project %s submittal %s",
                project_id,
                submittal_id,
            )
            return result

        logger.info(
            "MeasurementPipeline: found %d plan_set sheets for project %s",
            len(sheet_rows),
            project_id,
        )

        # ----------------------------------------------------------------
        # 2. Group sheets by document_id to download each PDF only once
        # ----------------------------------------------------------------
        # doc_id → list of sheet row dicts
        docs: dict[str, list[dict[str, object]]] = {}
        for row in sheet_rows:
            doc_id = str(row["document_id"])
            docs.setdefault(doc_id, []).append(row)

        # Accumulate LLM call log rows across all sheets; insert in one go at end
        call_log_rows: list[dict[str, object]] = []

        for doc_id, doc_sheets in docs.items():
            s3_uri: str = str(doc_sheets[0]["s3_uri"])
            bucket, key = _parse_s3_uri(s3_uri)

            # ----------------------------------------------------------------
            # 3. Download PDF (once per document_id)
            # ----------------------------------------------------------------
            pdf_path: str | None = None
            fitz_doc: fitz.Document | None = None

            if dry_run:
                logger.info("[dry-run] Skipping S3 download for %s", s3_uri)
                fitz_doc = None
            else:
                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                tmp.close()
                pdf_path = tmp.name
                try:
                    logger.info(
                        "MeasurementPipeline: downloading s3://%s/%s → %s",
                        bucket, key, pdf_path,
                    )
                    s3_client.download_file(bucket, key, pdf_path)  # type: ignore[union-attr]
                    fitz_doc = fitz.open(pdf_path)
                except Exception as exc:
                    err = f"S3 download failed for {s3_uri}: {exc}"
                    logger.error(err)
                    result.errors.append(err)
                    result.skipped_sheets += len(doc_sheets)
                    continue

            try:
                for sheet_row in doc_sheets:
                    sheet_id: str = str(sheet_row["sheet_id"])
                    page_num: int = int(sheet_row["page"])  # type: ignore[arg-type]
                    sheet_type: str | None = sheet_row.get("sheet_type")  # type: ignore[assignment]
                    declared_scale: str | None = sheet_row.get("declared_scale")  # type: ignore[assignment]

                    logger.info(
                        "MeasurementPipeline: processing sheet %s (page %d, type=%s)",
                        sheet_id, page_num, sheet_type,
                    )

                    # ----------------------------------------------------
                    # 4. Get the PyMuPDF page object
                    # ----------------------------------------------------
                    fitz_page: fitz.Page | None = None
                    if fitz_doc is not None:
                        try:
                            fitz_page = fitz_doc.load_page(page_num)
                        except Exception as exc:
                            err = f"Cannot load page {page_num} from {s3_uri}: {exc}"
                            logger.warning(err)
                            result.errors.append(err)
                            result.skipped_sheets += 1
                            continue

                    # ----------------------------------------------------
                    # 5. Classify PDF quality and update sheet row
                    # ----------------------------------------------------
                    pdf_quality: str = "raster"
                    pdf_quality_confidence: float = 0.70
                    if fitz_page is not None:
                        pdf_quality, pdf_quality_confidence = classify_page(fitz_page)

                    # ----------------------------------------------------
                    # 6. Resolve scale and update sheet row
                    # ----------------------------------------------------
                    scale: SheetScaleResult = resolve_sheet_scale(
                        sheet_id=sheet_id,
                        declared_scale=declared_scale,
                    )

                    _update_sheet_columns(
                        conn,
                        sheet_id,
                        pdf_quality_class=pdf_quality,
                        calibrated_scale_ratio=scale.pts_per_real_inch,
                        dry_run=dry_run,
                    )

                    result.sheets_processed += 1

                    # ----------------------------------------------------
                    # 7. Decide whether to run FloorPlanGeometryAgent
                    # ----------------------------------------------------
                    should_extract = (
                        sheet_type is None
                        or sheet_type in _FLOOR_PLAN_SHEET_TYPES
                    )

                    if not should_extract:
                        logger.debug(
                            "Skipping FloorPlanGeometryAgent for sheet %s (type=%s)",
                            sheet_id, sheet_type,
                        )
                        result.skipped_sheets += 1
                        continue

                    if fitz_page is None:
                        # dry_run path — skip extraction
                        logger.debug("[dry-run] Skipping extraction for sheet %s", sheet_id)
                        continue

                    # ----------------------------------------------------
                    # 8. Run FloorPlanGeometryAgent
                    # ----------------------------------------------------
                    try:
                        extraction = extract_floor_plan(
                            fitz_page,
                            sheet_id=sheet_id,
                            api_key=anthropic_api_key,
                            pdf_quality=pdf_quality,
                            call_log_rows=call_log_rows,
                        )
                    except Exception as exc:
                        err = f"FloorPlanGeometryAgent failed on sheet {sheet_id}: {exc}"
                        logger.error(err)
                        result.errors.append(err)
                        continue

                    entities = extraction.entities
                    logger.info(
                        "MeasurementPipeline: sheet %s extracted %d entities (doors=%d windows=%d rooms=%d)",
                        sheet_id,
                        len(entities),
                        extraction.total_doors,
                        extraction.total_windows,
                        extraction.total_rooms,
                    )

                    # ----------------------------------------------------
                    # 9. Insert entities + compute measurements
                    # ----------------------------------------------------
                    # Collect by type for egress distance computation
                    bedroom_entities: list[tuple[str, FloorPlanEntity]] = []
                    exit_entities: list[tuple[str, FloorPlanEntity]] = []

                    for entity in entities:
                        # Insert entity row
                        entity_id = _insert_entity(
                            conn,
                            project_id=project_id,
                            document_id=doc_id,
                            sheet_id=sheet_id,
                            entity=entity,
                            extractor_version=extractor_version,
                            dry_run=dry_run,
                        )
                        result.entities_inserted += 1

                        etype = entity.entity_type

                        # --- Door clear width ---
                        if etype == "door":
                            m = compute_door_clear_width(entity, scale)
                            m_dict = m.model_dump()
                            m_dict["entity_id"] = entity_id
                            _insert_measurement(
                                conn,
                                project_id=project_id,
                                result_row=m_dict,
                                extractor_version=extractor_version,
                                dry_run=dry_run,
                            )
                            result.measurements_inserted += 1

                        # --- Window NCO ---
                        elif etype == "window":
                            m = compute_window_nco(entity, scale)
                            m_dict = m.model_dump()
                            m_dict["entity_id"] = entity_id
                            _insert_measurement(
                                conn,
                                project_id=project_id,
                                result_row=m_dict,
                                extractor_version=extractor_version,
                                dry_run=dry_run,
                            )
                            result.measurements_inserted += 1

                        # --- Room area ---
                        elif etype == "room":
                            m = compute_room_area(entity, scale)
                            m_dict = m.model_dump()
                            m_dict["entity_id"] = entity_id
                            _insert_measurement(
                                conn,
                                project_id=project_id,
                                result_row=m_dict,
                                extractor_version=extractor_version,
                                dry_run=dry_run,
                            )
                            result.measurements_inserted += 1

                            # Track bedrooms for egress computation
                            if entity.room_use == "bedroom":
                                bedroom_entities.append((entity_id, entity))

                        # --- Exit — track for egress computation ---
                        elif etype == "exit":
                            exit_entities.append((entity_id, entity))

                    # --------------------------------------------------------
                    # 10. Compute egress distances: each bedroom × nearest exit
                    # --------------------------------------------------------
                    if bedroom_entities and exit_entities:
                        for _bed_eid, bedroom in bedroom_entities:
                            # Use nearest exit (minimum straight-line distance)
                            nearest_exit_eid: str | None = None
                            nearest_exit_entity: FloorPlanEntity | None = None
                            min_dist_pts: float = float("inf")

                            bed_cx = (bedroom.bbox[0] + bedroom.bbox[2]) / 2.0
                            bed_cy = (bedroom.bbox[1] + bedroom.bbox[3]) / 2.0

                            for _exit_eid, exit_ent in exit_entities:
                                ex_cx = (exit_ent.bbox[0] + exit_ent.bbox[2]) / 2.0
                                ex_cy = (exit_ent.bbox[1] + exit_ent.bbox[3]) / 2.0
                                d = ((ex_cx - bed_cx) ** 2 + (ex_cy - bed_cy) ** 2) ** 0.5
                                if d < min_dist_pts:
                                    min_dist_pts = d
                                    nearest_exit_eid = _exit_eid
                                    nearest_exit_entity = exit_ent

                            if nearest_exit_entity is not None:
                                m = compute_egress_distance(bedroom, nearest_exit_entity, scale)
                                m_dict = m.model_dump()
                                m_dict["entity_id"] = _bed_eid  # linked to bedroom entity
                                _insert_measurement(
                                    conn,
                                    project_id=project_id,
                                    result_row=m_dict,
                                    extractor_version=extractor_version,
                                    dry_run=dry_run,
                                )
                                result.measurements_inserted += 1

            finally:
                # Always close the fitz document and clean up temp file
                if fitz_doc is not None:
                    try:
                        fitz_doc.close()
                    except Exception:
                        pass
                if pdf_path and os.path.exists(pdf_path):
                    try:
                        os.unlink(pdf_path)
                    except Exception:
                        pass

        # ----------------------------------------------------------------
        # 11. Bulk-insert LLM call log rows and commit
        # ----------------------------------------------------------------
        _insert_llm_call_logs(conn, call_log_rows, dry_run=dry_run)

        if not dry_run:
            conn.commit()
            logger.info(
                "MeasurementPipeline: committed. sheets=%d entities=%d measurements=%d errors=%d",
                result.sheets_processed,
                result.entities_inserted,
                result.measurements_inserted,
                len(result.errors),
            )
        else:
            logger.info(
                "MeasurementPipeline: dry-run complete. sheets=%d entities=%d measurements=%d",
                result.sheets_processed,
                result.entities_inserted,
                result.measurements_inserted,
            )

    except Exception as exc:
        logger.exception("MeasurementPipeline: unhandled error: %s", exc)
        result.errors.append(f"Pipeline error: {exc}")
        if not dry_run:
            try:
                conn.rollback()
            except Exception:
                pass
    finally:
        conn.close()

    return result
