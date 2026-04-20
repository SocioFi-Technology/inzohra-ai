from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import fitz  # PyMuPDF

from services.measurement.app.dim_text_agent import DimTextResult

VERSION = "1.0.0"

logger = logging.getLogger(__name__)

_CONFIDENCE_BOOST_SMALL_DELTA: float = 0.10
_CONFIDENCE_PENALTY_LARGE_DELTA: float = 0.20
_SMALL_DELTA_THRESHOLD: float = 0.05   # 5%
_LARGE_DELTA_THRESHOLD: float = 0.20   # 20%
_MIN_DIM_CONFIDENCE: float = 0.70
_MAX_DISTANCE_TO_LINE: float = 40.0    # PDF points — search radius for dim lines
_MIN_LINE_LENGTH_PTS: float = 10.0


@dataclass
class CalibrationResult:
    """Result of cross-verifying declared scale against dimension-string anchors."""

    pts_per_real_inch: float
    calibrated: bool
    confidence: float
    anchor_count: int
    strongest_delta_pct: float | None   # None if no anchors found
    trace: list[dict[str, object]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _bbox_center(bbox: list[float]) -> tuple[float, float]:
    """Return (cx, cy) of a bbox [x1, y1, x2, y2]."""
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def _distance(pt_a: tuple[float, float], pt_b: tuple[float, float]) -> float:
    """Euclidean distance between two 2-D points."""
    return math.hypot(pt_b[0] - pt_a[0], pt_b[1] - pt_a[1])


def _drawing_bbox(item: dict[str, object]) -> list[float] | None:
    """Extract [x1, y1, x2, y2] from a PyMuPDF drawing item dict."""
    rect = item.get("rect")
    if rect is None:
        return None
    try:
        x1, y1, x2, y2 = float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])  # type: ignore[index]
        return [x1, y1, x2, y2]
    except (TypeError, ValueError, IndexError):
        return None


def _line_length(item: dict[str, object]) -> float | None:
    """Compute length of a straight-line drawing item."""
    # PyMuPDF stores line as list of path items in "items" key
    # For a simple line, items = [("l", (x1,y1), (x2,y2))] or similar
    items_raw = item.get("items")
    if not isinstance(items_raw, (list, tuple)):
        return None

    for seg in items_raw:
        if not isinstance(seg, (list, tuple)) or len(seg) < 3:
            continue
        if str(seg[0]) != "l":
            continue
        try:
            x1, y1 = float(seg[1][0]), float(seg[1][1])  # type: ignore[index]
            x2, y2 = float(seg[2][0]), float(seg[2][1])  # type: ignore[index]
            return math.hypot(x2 - x1, y2 - y1)
        except (TypeError, ValueError, IndexError):
            continue

    # Fallback: derive from rect
    rect = item.get("rect")
    if rect is not None:
        try:
            w = abs(float(rect[2]) - float(rect[0]))  # type: ignore[index]
            h = abs(float(rect[3]) - float(rect[1]))  # type: ignore[index]
            return max(w, h)
        except (TypeError, ValueError, IndexError):
            pass

    return None


def _is_text_horizontal(bbox: list[float]) -> bool:
    """Return True if the bounding box is wider than it is tall (horizontal text)."""
    width = abs(bbox[2] - bbox[0])
    height = abs(bbox[3] - bbox[1])
    return width >= height


def _find_adjacent_line(
    text_bbox: list[float],
    drawings: list[dict[str, object]],
    max_distance_pts: float = _MAX_DISTANCE_TO_LINE,
    min_length_pts: float = _MIN_LINE_LENGTH_PTS,
) -> tuple[float, list[float]] | None:
    """Find the closest straight line to a text bbox.

    Returns (line_length_pts, line_bbox) or None.
    Only considers lines that are longer than min_length_pts.
    Orientation of the line is expected to match the text (horizontal ↔ wide bbox).
    """
    text_center = _bbox_center(text_bbox)
    text_is_horizontal = _is_text_horizontal(text_bbox)

    best_dist: float = max_distance_pts
    best_length: float | None = None
    best_bbox: list[float] | None = None

    for item in drawings:
        # Only straight lines
        if item.get("type") not in ("l", "line"):
            # Also check "items" for line segments in path drawings
            items_raw = item.get("items")
            if not isinstance(items_raw, (list, tuple)):
                continue
            has_line_seg = any(
                isinstance(seg, (list, tuple)) and len(seg) >= 1 and str(seg[0]) == "l"
                for seg in items_raw
            )
            if not has_line_seg:
                continue

        length = _line_length(item)
        if length is None or length < min_length_pts:
            continue

        line_bbox = _drawing_bbox(item)
        if line_bbox is None:
            continue

        # Check orientation match
        line_width = abs(line_bbox[2] - line_bbox[0])
        line_height = abs(line_bbox[3] - line_bbox[1])
        line_is_horizontal = line_width >= line_height

        if line_is_horizontal != text_is_horizontal:
            continue

        line_center = _bbox_center(line_bbox)
        dist = _distance(text_center, line_center)

        if dist < best_dist:
            best_dist = dist
            best_length = length
            best_bbox = line_bbox

    if best_length is not None and best_bbox is not None:
        return (best_length, best_bbox)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calibrate_scale(
    page: fitz.Page,
    declared_pts_per_real_inch: float,
    dim_strings: list[DimTextResult],
) -> CalibrationResult:
    """Cross-verify declared scale against dimension-string anchors on the page.

    Strategy:
    1. For each dim string with confidence > 0.7:
       - Find an adjacent dimension line via page.get_drawings().
       - Compute implied_ratio = line_pts / dim_total_inches.
       - Compare to declared_pts_per_real_inch.
    2. If ≥1 anchor found, apply confidence adjustments based on delta.
    3. Return calibrated ratio using the strongest (lowest delta) anchor's implied ratio
       if calibrated; otherwise return declared value.
    """
    if declared_pts_per_real_inch <= 0:
        logger.error("declared_pts_per_real_inch must be positive; got %.4f", declared_pts_per_real_inch)
        return CalibrationResult(
            pts_per_real_inch=declared_pts_per_real_inch,
            calibrated=False,
            confidence=0.0,
            anchor_count=0,
            strongest_delta_pct=None,
        )

    try:
        drawings: list[dict[str, object]] = page.get_drawings()  # type: ignore[assignment]
    except Exception as exc:
        logger.warning("Page %d: get_drawings() failed: %s", page.number, exc)
        drawings = []

    trace: list[dict[str, object]] = []
    usable_dims = [d for d in dim_strings if d.confidence > _MIN_DIM_CONFIDENCE and d.total_inches > 0]

    for dim in usable_dims:
        result = _find_adjacent_line(dim.bbox, drawings)
        if result is None:
            logger.debug(
                "Page %d: no adjacent dim line found for %r",
                page.number,
                dim.raw_text,
            )
            continue

        line_pts, _line_bbox = result
        implied_ratio = line_pts / dim.total_inches
        delta_pct = abs(implied_ratio - declared_pts_per_real_inch) / declared_pts_per_real_inch

        trace.append(
            {
                "dim_text": dim.raw_text,
                "dim_total_inches": dim.total_inches,
                "line_pts": line_pts,
                "implied_ratio": implied_ratio,
                "delta_pct": delta_pct,
                "dim_confidence": dim.confidence,
            }
        )
        logger.debug(
            "Page %d: anchor %r → line_pts=%.2f implied=%.4f declared=%.4f delta=%.1f%%",
            page.number,
            dim.raw_text,
            line_pts,
            implied_ratio,
            declared_pts_per_real_inch,
            delta_pct * 100,
        )

    if not trace:
        logger.info(
            "Page %d: no usable calibration anchors found; returning declared scale",
            page.number,
        )
        return CalibrationResult(
            pts_per_real_inch=declared_pts_per_real_inch,
            calibrated=False,
            confidence=0.0,
            anchor_count=0,
            strongest_delta_pct=None,
            trace=[],
        )

    # Sort by ascending delta to find the strongest (most consistent) anchor
    trace.sort(key=lambda e: float(e["delta_pct"]))  # type: ignore[arg-type]
    strongest = trace[0]
    strongest_delta: float = float(strongest["delta_pct"])
    strongest_implied: float = float(strongest["implied_ratio"])

    # Build confidence from declared baseline; we don't have a prior confidence here,
    # so start neutral at 0.75 and adjust based on how well anchors agree.
    base_confidence: float = 0.75
    calibrated: bool = False
    final_pts_per_real_inch: float = declared_pts_per_real_inch

    if strongest_delta < _SMALL_DELTA_THRESHOLD:
        calibrated = True
        base_confidence = min(0.99, base_confidence + _CONFIDENCE_BOOST_SMALL_DELTA)
        final_pts_per_real_inch = strongest_implied
        logger.info(
            "Page %d: scale calibrated (delta=%.1f%%) → %.4f pts/in",
            page.number,
            strongest_delta * 100,
            final_pts_per_real_inch,
        )
    elif strongest_delta > _LARGE_DELTA_THRESHOLD:
        base_confidence = max(0.30, base_confidence - _CONFIDENCE_PENALTY_LARGE_DELTA)
        logger.warning(
            "Page %d: scale mismatch suspect (delta=%.1f%%); sticking with declared %.4f pts/in",
            page.number,
            strongest_delta * 100,
            declared_pts_per_real_inch,
        )
    else:
        logger.info(
            "Page %d: scale within tolerance (delta=%.1f%%) but not flagged as calibrated",
            page.number,
            strongest_delta * 100,
        )

    return CalibrationResult(
        pts_per_real_inch=final_pts_per_real_inch,
        calibrated=calibrated,
        confidence=base_confidence,
        anchor_count=len(trace),
        strongest_delta_pct=strongest_delta,
        trace=trace,
    )
