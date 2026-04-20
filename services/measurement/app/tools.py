"""Measurement tool surface — callable API for reviewer agents.

Every tool reads from the DB and returns a typed result with provenance.
Tools are read-only.  No LLM calls.  No writes.

These functions implement the measure_* and get_* surface described in
docs/09-reasoning-tools.md and are called by Layer-7 reviewer agents.

All results carry:
  measurement_id  — UUID for the stored measurement row
  confidence      — composed confidence from the derivation chain
  trace           — JSON-serialisable derivation trace (full provenance)

Layer: 6 — Reasoning tools (read-only view over L1 storage).
"""
from __future__ import annotations

import math
import uuid
from typing import Any

import psycopg

VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row: Any) -> dict[str, object]:
    """Convert a psycopg dict-row to a plain Python dict."""
    if isinstance(row, dict):
        return dict(row)
    # Fallback for named-tuple style rows (psycopg NamedTupleCursor)
    return row._asdict() if hasattr(row, "_asdict") else dict(row)


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------

def get_sheet_scale(
    conn: "psycopg.Connection[Any]",
    sheet_id: str,
) -> dict[str, object]:
    """Return scale information for a sheet from the sheets table.

    Returns
    -------
    dict with keys:
        sheet_id            str
        declared            str | None    — declared_scale column verbatim
        pts_per_real_inch   float         — calibrated_scale_ratio if present, else 1.5 (default)
        confidence          float         — 0.85 if ratio set, 0.50 if default
        source              str           — "calibrated" | "title_block" | "default"
    """
    row = conn.execute(
        """
        SELECT sheet_id, declared_scale, calibrated_scale_ratio
        FROM   sheets
        WHERE  sheet_id = %s
        """,
        (sheet_id,),
    ).fetchone()

    if row is None:
        return {
            "sheet_id": sheet_id,
            "declared": None,
            "pts_per_real_inch": 1.5,
            "confidence": 0.50,
            "source": "default",
            "error": f"sheet_id {sheet_id!r} not found",
        }

    r = _row_to_dict(row)
    ratio: float | None = r.get("calibrated_scale_ratio")  # type: ignore[assignment]

    if ratio is not None and ratio > 0:
        return {
            "sheet_id": sheet_id,
            "declared": r.get("declared_scale"),
            "pts_per_real_inch": float(ratio),
            "confidence": 0.85,
            "source": "calibrated",
        }

    # Fall back to declared_scale text; if absent, use default
    declared: str | None = r.get("declared_scale")  # type: ignore[assignment]
    if declared:
        return {
            "sheet_id": sheet_id,
            "declared": declared,
            "pts_per_real_inch": 1.5,
            "confidence": 0.70,
            "source": "title_block",
        }

    return {
        "sheet_id": sheet_id,
        "declared": None,
        "pts_per_real_inch": 1.5,
        "confidence": 0.50,
        "source": "default",
    }


def get_door_specs(
    conn: "psycopg.Connection[Any]",
    project_id: str,
    door_tag: str,
) -> dict[str, object]:
    """Return clear-width measurement and entity info for a tagged door.

    Reads measurements WHERE type='door_clear_width' AND tag=door_tag
    AND project_id=project_id.  Joins entities for bbox and entity_id.

    Returns most-recently-created measurement (append-only storage means
    the latest row supersedes earlier runs for the same tag).

    Returns
    -------
    dict with keys:
        measurement_id  str
        entity_id       str | None
        sheet_id        str
        tag             str
        width_in        float
        unit            str   ("in")
        confidence      float
        trace           dict
        bbox            list[float] | None
    """
    row = conn.execute(
        """
        SELECT m.measurement_id,
               m.sheet_id,
               m.value          AS width_in,
               m.unit,
               m.confidence,
               m.trace,
               m.bbox,
               m.entity_id,
               m.tag
        FROM   measurements m
        WHERE  m.project_id = %s
          AND  m.type       = 'door_clear_width'
          AND  m.tag        = %s
        ORDER  BY m.created_at DESC
        LIMIT  1
        """,
        (project_id, door_tag),
    ).fetchone()

    if row is None:
        return {
            "error": f"No door_clear_width measurement found for tag={door_tag!r} in project {project_id!r}",
            "tag": door_tag,
            "project_id": project_id,
        }

    r = _row_to_dict(row)
    return {
        "measurement_id": str(r["measurement_id"]),
        "entity_id": str(r["entity_id"]) if r.get("entity_id") else None,
        "sheet_id": str(r["sheet_id"]),
        "tag": r.get("tag"),
        "width_in": float(r["width_in"]),
        "unit": r["unit"],
        "confidence": float(r["confidence"]),
        "trace": r["trace"] if isinstance(r["trace"], dict) else {},
        "bbox": list(r["bbox"]) if r.get("bbox") else None,
    }


def get_window_specs(
    conn: "psycopg.Connection[Any]",
    project_id: str,
    window_tag: str,
) -> dict[str, object]:
    """Return NCO and width info for a tagged window.

    Reads measurements WHERE type='window_nco' AND tag=window_tag.

    Returns
    -------
    dict with keys:
        measurement_id  str
        entity_id       str | None
        sheet_id        str
        tag             str
        nco_sqft        float
        width_in        float   (derived: sqrt(nco_sqft * 12/44) * 12 — approximate)
        unit            str     ("sqft")
        confidence      float
        trace           dict
        bbox            list[float] | None
    """
    row = conn.execute(
        """
        SELECT m.measurement_id,
               m.sheet_id,
               m.value          AS nco_sqft,
               m.unit,
               m.confidence,
               m.trace,
               m.bbox,
               m.entity_id,
               m.tag
        FROM   measurements m
        WHERE  m.project_id = %s
          AND  m.type       = 'window_nco'
          AND  m.tag        = %s
        ORDER  BY m.created_at DESC
        LIMIT  1
        """,
        (project_id, window_tag),
    ).fetchone()

    if row is None:
        return {
            "error": f"No window_nco measurement found for tag={window_tag!r} in project {project_id!r}",
            "tag": window_tag,
            "project_id": project_id,
        }

    r = _row_to_dict(row)
    nco_sqft: float = float(r["nco_sqft"])

    # Recover approximate width_in from NCO and the standard assumed height.
    # NCO_sqft = (width_in/12) * (44/12) → width_in = NCO_sqft * 144 / 44
    width_in: float = nco_sqft * 144.0 / 44.0

    return {
        "measurement_id": str(r["measurement_id"]),
        "entity_id": str(r["entity_id"]) if r.get("entity_id") else None,
        "sheet_id": str(r["sheet_id"]),
        "tag": r.get("tag"),
        "nco_sqft": nco_sqft,
        "width_in": round(width_in, 4),
        "unit": r["unit"],
        "confidence": float(r["confidence"]),
        "trace": r["trace"] if isinstance(r["trace"], dict) else {},
        "bbox": list(r["bbox"]) if r.get("bbox") else None,
    }


def measure_distance(
    conn: "psycopg.Connection[Any]",
    sheet_id: str,
    point_a: tuple[float, float],
    point_b: tuple[float, float],
) -> dict[str, object]:
    """Compute straight-line distance between two PDF-point coordinates.

    Uses the sheet's calibrated scale to convert from PDF points to inches.
    This is an on-demand calculation — no measurement row is stored.

    Parameters
    ----------
    conn:
        Active psycopg connection with dict_row factory.
    sheet_id:
        Sheet to look up scale for.
    point_a, point_b:
        (x, y) coordinates in PDF points (72 pts/inch), top-left origin.

    Returns
    -------
    dict with keys:
        value_in    float   distance in inches
        unit        str     "in"
        confidence  float
        trace       dict
    """
    scale_info = get_sheet_scale(conn, sheet_id)
    pts_per_real_inch: float = float(scale_info.get("pts_per_real_inch", 1.5))  # type: ignore[arg-type]
    scale_confidence: float = float(scale_info.get("confidence", 0.50))  # type: ignore[arg-type]

    dist_pts = math.sqrt(
        (point_b[0] - point_a[0]) ** 2 + (point_b[1] - point_a[1]) ** 2
    )
    value_in: float = dist_pts / pts_per_real_inch

    # Confidence: scale_confidence * geometry_certainty (0.92 for clean vector points)
    geometry_certainty = 0.92
    confidence = max(0.30, min(0.99, scale_confidence * geometry_certainty))

    trace = {
        "sublayers": [
            {
                "layer": "geometry",
                "point_a": list(point_a),
                "point_b": list(point_b),
                "dist_pts": round(dist_pts, 4),
                "confidence": geometry_certainty,
            },
            {
                "layer": "scale",
                "pts_per_real_inch": pts_per_real_inch,
                "source": scale_info.get("source"),
                "confidence": scale_confidence,
            },
            {
                "layer": "formula",
                "formula": "value_in = sqrt((bx-ax)^2 + (by-ay)^2) / pts_per_real_inch",
                "confidence": geometry_certainty,
            },
        ],
        "formula": "value_in = sqrt((bx-ax)^2 + (by-ay)^2) / pts_per_real_inch",
        "source_bboxes": [
            [point_a[0], point_a[1], point_a[0], point_a[1]],
            [point_b[0], point_b[1], point_b[0], point_b[1]],
        ],
        "composed_confidence": confidence,
    }

    return {
        "value_in": round(value_in, 4),
        "unit": "in",
        "confidence": confidence,
        "trace": trace,
        "sheet_id": sheet_id,
    }


def list_bedroom_windows(
    conn: "psycopg.Connection[Any]",
    project_id: str,
) -> list[dict[str, object]]:
    """Return all window NCO measurements for the project.

    Simplified implementation for Phase 03: returns every window_nco
    measurement stored for the project.  Phase 05 will refine this to
    spatially join measurements to bedroom entities.

    Returns
    -------
    list of dicts, each matching the shape of get_window_specs().
    """
    rows = conn.execute(
        """
        SELECT m.measurement_id,
               m.sheet_id,
               m.value       AS nco_sqft,
               m.unit,
               m.confidence,
               m.trace,
               m.bbox,
               m.entity_id,
               m.tag,
               m.created_at
        FROM   measurements m
        WHERE  m.project_id = %s
          AND  m.type       = 'window_nco'
        ORDER  BY m.created_at
        """,
        (project_id,),
    ).fetchall()

    results: list[dict[str, object]] = []
    for row in rows:
        r = _row_to_dict(row)
        nco_sqft = float(r["nco_sqft"])
        width_in = nco_sqft * 144.0 / 44.0
        results.append(
            {
                "measurement_id": str(r["measurement_id"]),
                "entity_id": str(r["entity_id"]) if r.get("entity_id") else None,
                "sheet_id": str(r["sheet_id"]),
                "tag": r.get("tag"),
                "nco_sqft": nco_sqft,
                "width_in": round(width_in, 4),
                "unit": r["unit"],
                "confidence": float(r["confidence"]),
                "trace": r["trace"] if isinstance(r["trace"], dict) else {},
                "bbox": list(r["bbox"]) if r.get("bbox") else None,
            }
        )
    return results


def list_bedroom_egress_distances(
    conn: "psycopg.Connection[Any]",
    project_id: str,
) -> list[dict[str, object]]:
    """Return all egress_distance measurements for the project.

    Returns
    -------
    list of dicts with keys:
        measurement_id, sheet_id, tag, dist_ft, unit, confidence, trace, bbox
    """
    rows = conn.execute(
        """
        SELECT m.measurement_id,
               m.sheet_id,
               m.value       AS dist_ft,
               m.unit,
               m.confidence,
               m.trace,
               m.bbox,
               m.entity_id,
               m.tag,
               m.created_at
        FROM   measurements m
        WHERE  m.project_id = %s
          AND  m.type       = 'egress_distance'
        ORDER  BY m.created_at
        """,
        (project_id,),
    ).fetchall()

    results: list[dict[str, object]] = []
    for row in rows:
        r = _row_to_dict(row)
        results.append(
            {
                "measurement_id": str(r["measurement_id"]),
                "entity_id": str(r["entity_id"]) if r.get("entity_id") else None,
                "sheet_id": str(r["sheet_id"]),
                "tag": r.get("tag"),
                "dist_ft": float(r["dist_ft"]),
                "unit": r["unit"],
                "confidence": float(r["confidence"]),
                "trace": r["trace"] if isinstance(r["trace"], dict) else {},
                "bbox": list(r["bbox"]) if r.get("bbox") else None,
            }
        )
    return results
