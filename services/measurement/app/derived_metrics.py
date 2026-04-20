"""DerivedMetricsEngine — compute code-checkable quantities from extracted entities + scale.

Layer: 4 — Measurement.  Pure computation: no LLM calls, no DB writes.
Inputs:  FloorPlanEntity (from L3 extraction) + SheetScaleResult (from ScaleResolver).
Outputs: MeasurementResult with full provenance trace.

Every result carries:
  bbox          — source bounding region in PDF points
  confidence    — composed product of all sub-layer confidences
  trace         — machine-readable derivation chain down to source bboxes

Invariant: temperature is irrelevant here (no LLM), but all numeric thresholds
are explicit constants so reviewers can audit them.
"""
from __future__ import annotations

import math
import uuid

from inzohra_shared.schemas.measurement import (
    FloorPlanEntity,
    MeasurementResult,
    MeasurementTrace,
)
from app.scale_resolver import SheetScaleResult

VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONFIDENCE_CAP: float = 0.99
_CONFIDENCE_FLOOR: float = 0.30

# Height uncertainty factor — floor plan views show windows in plan (horizontal
# cut).  Width from bbox is reliable; height is NOT visible.  We assume a
# residential default and apply a significant confidence penalty.
_WINDOW_ASSUMED_HEIGHT_IN: float = 44.0   # inches, typical residential egress height
_GEOMETRY_UNCERTAINTY: float = 0.88       # door bbox-to-clear-width conversion
_WINDOW_HEIGHT_UNCERTAINTY: float = 0.70  # height is assumed, not measured
_ROOM_BBOX_UNCERTAINTY: float = 0.75      # rooms rarely perfectly rectangular
_EGRESS_STRAIGHTLINE_UNCERTAINTY: float = 0.80  # straight-line underestimates travel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compose_confidence(sublayer_confidences: list[float]) -> float:
    """Return the product of all confidences, capped at 0.99, floored at 0.30."""
    result: float = 1.0
    for c in sublayer_confidences:
        result *= c
    return max(_CONFIDENCE_FLOOR, min(_CONFIDENCE_CAP, result))


# ---------------------------------------------------------------------------
# Measurement functions
# ---------------------------------------------------------------------------

def compute_door_clear_width(
    entity: FloorPlanEntity,
    scale: SheetScaleResult,
) -> MeasurementResult:
    """Compute clear width of a door opening from its bbox and sheet scale.

    Clear width is derived from the horizontal span of the entity bbox divided
    by the calibrated pts_per_real_inch ratio.

    rule_id: ARCH-DOOR-CLEAR-WIDTH-001
    """
    bbox_width_pts: float = entity.bbox[2] - entity.bbox[0]
    clear_width_in: float = bbox_width_pts / scale.pts_per_real_inch

    confidence = compose_confidence(
        [scale.confidence, entity.confidence, _GEOMETRY_UNCERTAINTY]
    )

    trace = MeasurementTrace(
        sublayers=[
            {
                "layer": "geometry",
                "bbox_width_pts": bbox_width_pts,
                "confidence": entity.confidence,
            },
            {
                "layer": "scale",
                "pts_per_real_inch": scale.pts_per_real_inch,
                "source": scale.source,
                "confidence": scale.confidence,
            },
            {
                "layer": "formula",
                "formula": "clear_width_in = bbox_width_pts / pts_per_real_inch",
                "confidence": _GEOMETRY_UNCERTAINTY,
            },
        ],
        formula="clear_width_in = bbox_width_pts / pts_per_real_inch",
        source_bboxes=[entity.bbox],
        composed_confidence=confidence,
    )

    return MeasurementResult(
        measurement_id=str(uuid.uuid4()),
        type="door_clear_width",
        value=round(clear_width_in, 4),
        unit="in",
        confidence=confidence,
        trace=trace,
        bbox=entity.bbox,
        tag=entity.tag,
        entity_id=None,   # caller fills entity_id after DB insert of entity row
        sheet_id=scale.sheet_id,
    )


def compute_window_nco(
    entity: FloorPlanEntity,
    scale: SheetScaleResult,
    sill_height_in: float | None = None,
) -> MeasurementResult:
    """Compute Net Clear Opening area (sqft) for a window.

    Floor plan views show windows in plan (horizontal cut), not elevation.
    Width from bbox is reliable; height is NOT visible in floor plan.
    We assume 44 inches (typical residential egress height) unless
    schedule data provides a better value.

    For Phase 03, schedule lookup is not yet wired; sill_height_in is accepted
    as a forward-compatibility parameter but unused in the NCO formula
    (it represents sill AFF, not opening height).

    NCO_sqft = (clear_width_in / 12) * (assumed_height_in / 12)

    rule_id: ARCH-WINDOW-NCO-001
    """
    clear_width_in: float = (entity.bbox[2] - entity.bbox[0]) / scale.pts_per_real_inch
    assumed_height_in: float = _WINDOW_ASSUMED_HEIGHT_IN

    nco_sqft: float = (clear_width_in / 12.0) * (assumed_height_in / 12.0)

    confidence = compose_confidence(
        [scale.confidence, entity.confidence, _WINDOW_HEIGHT_UNCERTAINTY]
    )

    trace = MeasurementTrace(
        sublayers=[
            {
                "layer": "geometry",
                "clear_width_in": round(clear_width_in, 4),
                "bbox_width_pts": round(entity.bbox[2] - entity.bbox[0], 4),
                "confidence": entity.confidence,
            },
            {
                "layer": "scale",
                "pts_per_real_inch": scale.pts_per_real_inch,
                "source": scale.source,
                "confidence": scale.confidence,
            },
            {
                "layer": "height_assumption",
                "assumed_height_in": assumed_height_in,
                "note": (
                    "Floor plan view does not expose window height. "
                    "44 in assumed (typical residential egress). "
                    "Override with schedule data when available."
                ),
                "confidence": _WINDOW_HEIGHT_UNCERTAINTY,
            },
            {
                "layer": "formula",
                "formula": "nco_sqft = (clear_width_in / 12) * (assumed_height_in / 12)",
                "confidence": _WINDOW_HEIGHT_UNCERTAINTY,
            },
        ],
        formula="nco_sqft = (clear_width_in / 12) * (assumed_height_in / 12)",
        source_bboxes=[entity.bbox],
        composed_confidence=confidence,
    )

    return MeasurementResult(
        measurement_id=str(uuid.uuid4()),
        type="window_nco",
        value=round(nco_sqft, 6),
        unit="sqft",
        confidence=confidence,
        trace=trace,
        bbox=entity.bbox,
        tag=entity.tag,
        entity_id=None,   # caller fills entity_id after DB insert
        sheet_id=scale.sheet_id,
    )


def compute_room_area(
    entity: FloorPlanEntity,
    scale: SheetScaleResult,
) -> MeasurementResult:
    """Compute approximate room area (sqft) from bounding box.

    The bbox is an approximation — rooms are rarely perfectly rectangular.
    Confidence is penalised accordingly.

    rule_id: ARCH-ROOM-AREA-001
    """
    width_in: float = (entity.bbox[2] - entity.bbox[0]) / scale.pts_per_real_inch
    length_in: float = (entity.bbox[3] - entity.bbox[1]) / scale.pts_per_real_inch
    area_sqft: float = (width_in / 12.0) * (length_in / 12.0)

    confidence = compose_confidence(
        [scale.confidence, entity.confidence, _ROOM_BBOX_UNCERTAINTY]
    )

    trace = MeasurementTrace(
        sublayers=[
            {
                "layer": "geometry",
                "width_in": round(width_in, 4),
                "length_in": round(length_in, 4),
                "bbox": entity.bbox,
                "confidence": entity.confidence,
            },
            {
                "layer": "scale",
                "pts_per_real_inch": scale.pts_per_real_inch,
                "source": scale.source,
                "confidence": scale.confidence,
            },
            {
                "layer": "formula",
                "formula": "area_sqft = (width_in / 12) * (length_in / 12)",
                "note": "bbox approximation — rooms rarely perfectly rectangular",
                "confidence": _ROOM_BBOX_UNCERTAINTY,
            },
        ],
        formula="area_sqft = (width_in / 12) * (length_in / 12)",
        source_bboxes=[entity.bbox],
        composed_confidence=confidence,
    )

    return MeasurementResult(
        measurement_id=str(uuid.uuid4()),
        type="room_area",
        value=round(area_sqft, 4),
        unit="sqft",
        confidence=confidence,
        trace=trace,
        bbox=entity.bbox,
        tag=entity.tag,
        entity_id=None,
        sheet_id=scale.sheet_id,
    )


def compute_egress_distance(
    bedroom: FloorPlanEntity,
    exit_entity: FloorPlanEntity,
    scale: SheetScaleResult,
) -> MeasurementResult:
    """Compute straight-line egress distance from bedroom centre to exit centre (feet).

    This is a lower-bound approximation — actual travel distance follows corridors
    and is always greater than the straight-line value.  Phase 09 will replace this
    with a routed travel-distance measurement.

    rule_id: ARCH-EGRESS-DISTANCE-001
    """
    bed_cx: float = (bedroom.bbox[0] + bedroom.bbox[2]) / 2.0
    bed_cy: float = (bedroom.bbox[1] + bedroom.bbox[3]) / 2.0
    exit_cx: float = (exit_entity.bbox[0] + exit_entity.bbox[2]) / 2.0
    exit_cy: float = (exit_entity.bbox[1] + exit_entity.bbox[3]) / 2.0

    dist_pts: float = math.sqrt((exit_cx - bed_cx) ** 2 + (exit_cy - bed_cy) ** 2)
    dist_ft: float = dist_pts / scale.pts_per_real_inch / 12.0

    confidence = compose_confidence(
        [
            scale.confidence,
            bedroom.confidence,
            exit_entity.confidence,
            _EGRESS_STRAIGHTLINE_UNCERTAINTY,
        ]
    )

    # Combined bbox: the bounding box that encloses both source entities
    combined_bbox: list[float] = [
        min(bedroom.bbox[0], exit_entity.bbox[0]),
        min(bedroom.bbox[1], exit_entity.bbox[1]),
        max(bedroom.bbox[2], exit_entity.bbox[2]),
        max(bedroom.bbox[3], exit_entity.bbox[3]),
    ]

    trace = MeasurementTrace(
        sublayers=[
            {
                "layer": "geometry",
                "bedroom_center": [round(bed_cx, 2), round(bed_cy, 2)],
                "exit_center": [round(exit_cx, 2), round(exit_cy, 2)],
                "dist_pts": round(dist_pts, 4),
                "bedroom_confidence": bedroom.confidence,
                "exit_confidence": exit_entity.confidence,
            },
            {
                "layer": "scale",
                "pts_per_real_inch": scale.pts_per_real_inch,
                "source": scale.source,
                "confidence": scale.confidence,
            },
            {
                "layer": "formula",
                "formula": "dist_ft = sqrt((exit_cx-bed_cx)^2 + (exit_cy-bed_cy)^2) / pts_per_real_inch / 12",
                "note": "Straight-line approximation; actual travel distance will be higher.",
                "confidence": _EGRESS_STRAIGHTLINE_UNCERTAINTY,
            },
        ],
        formula="dist_ft = sqrt((exit_cx-bed_cx)^2 + (exit_cy-bed_cy)^2) / pts_per_real_inch / 12",
        source_bboxes=[bedroom.bbox, exit_entity.bbox],
        composed_confidence=confidence,
    )

    return MeasurementResult(
        measurement_id=str(uuid.uuid4()),
        type="egress_distance",
        value=round(dist_ft, 4),
        unit="ft",
        confidence=confidence,
        trace=trace,
        bbox=combined_bbox,
        tag=bedroom.tag,
        entity_id=None,
        sheet_id=scale.sheet_id,
    )
