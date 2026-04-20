from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import fitz  # PyMuPDF

from services.measurement.app.dim_text_agent import DimTextResult

VERSION = "1.0.0"

logger = logging.getLogger(__name__)

_MAX_STROKE_WIDTH: float = 3.0          # pts — thin lines only
_ANGLE_TOLERANCE_DEG: float = 5.0       # degrees from 0° / 90°
_DEFAULT_MIN_LENGTH_PTS: float = 20.0
_DEFAULT_MAX_DISTANCE_PTS: float = 30.0


def compose_confidence(sublayer_confidences: list[float]) -> float:
    """Multiplicative confidence composition, clamped to [0.30, 0.99]."""
    result = 1.0
    for c in sublayer_confidences:
        result *= max(0.01, float(c))
    return max(0.30, min(0.99, result))


@dataclass
class DimLine:
    """A detected dimension line on a PDF page."""

    start: tuple[float, float]          # PDF points (x, y)
    end: tuple[float, float]            # PDF points (x, y)
    length_pts: float
    is_horizontal: bool
    is_vertical: bool
    bbox: list[float]                   # [x1, y1, x2, y2]
    confidence: float


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _angle_deg(
    p1: tuple[float, float],
    p2: tuple[float, float],
) -> float:
    """Angle in degrees [0, 180) of the line from p1 to p2."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return math.degrees(math.atan2(abs(dy), abs(dx))) % 180.0


def _is_axis_aligned(angle: float, tol: float = _ANGLE_TOLERANCE_DEG) -> tuple[bool, bool]:
    """Return (is_horizontal, is_vertical) based on angle."""
    is_horizontal = angle <= tol or angle >= (180.0 - tol)
    is_vertical = abs(angle - 90.0) <= tol
    return is_horizontal, is_vertical


def _bbox_of_points(
    p1: tuple[float, float],
    p2: tuple[float, float],
) -> list[float]:
    x1, y1 = min(p1[0], p2[0]), min(p1[1], p2[1])
    x2, y2 = max(p1[0], p2[0]), max(p1[1], p2[1])
    return [x1, y1, x2, y2]


def _extract_line_endpoints(
    item: dict[str, object],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Extract start/end points from a PyMuPDF drawing item.

    Handles both dict-level 'p1'/'p2' keys (line items) and the 'items' path
    list containing ("l", start, end) segments.
    """
    # Direct line item with p1/p2
    p1_raw = item.get("p1")
    p2_raw = item.get("p2")
    if p1_raw is not None and p2_raw is not None:
        try:
            p1: tuple[float, float] = (float(p1_raw[0]), float(p1_raw[1]))  # type: ignore[index]
            p2: tuple[float, float] = (float(p2_raw[0]), float(p2_raw[1]))  # type: ignore[index]
            return p1, p2
        except (TypeError, ValueError, IndexError):
            pass

    # Path-based: look for first "l" segment in items list
    items_raw = item.get("items")
    if not isinstance(items_raw, (list, tuple)):
        return None

    for seg in items_raw:
        if not isinstance(seg, (list, tuple)) or len(seg) < 3:
            continue
        if str(seg[0]) != "l":
            continue
        try:
            s: tuple[float, float] = (float(seg[1][0]), float(seg[1][1]))  # type: ignore[index]
            e: tuple[float, float] = (float(seg[2][0]), float(seg[2][1]))  # type: ignore[index]
            return s, e
        except (TypeError, ValueError, IndexError):
            continue

    return None


def _stroke_width(item: dict[str, object]) -> float:
    """Return stroke width of a drawing item, defaulting to 1.0 if absent."""
    w = item.get("width")
    if w is None:
        return 1.0
    try:
        return float(w)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_dim_lines_vector(
    page: fitz.Page,
    min_length_pts: float = _DEFAULT_MIN_LENGTH_PTS,
) -> list[DimLine]:
    """Extract dimension lines from a vector PDF page using page.get_drawings().

    A dimension line must be:
    - A straight line (not a rect, arc, or curve)
    - Longer than min_length_pts
    - Horizontal or vertical (within 5° of 0° / 90°)
    - Thin stroke width (< 3 pts)
    """
    try:
        drawings: list[dict[str, object]] = page.get_drawings()  # type: ignore[assignment]
    except Exception as exc:
        logger.warning("Page %d: get_drawings() failed: %s", page.number, exc)
        return []

    dim_lines: list[DimLine] = []

    for item in drawings:
        # Only accept items that have line-segment content; skip rects, quads, curves
        endpoints = _extract_line_endpoints(item)
        if endpoints is None:
            continue

        start, end = endpoints

        length = math.hypot(end[0] - start[0], end[1] - start[1])
        if length < min_length_pts:
            continue

        stroke = _stroke_width(item)
        if stroke >= _MAX_STROKE_WIDTH:
            continue

        angle = _angle_deg(start, end)
        is_horiz, is_vert = _is_axis_aligned(angle)

        if not is_horiz and not is_vert:
            continue

        bbox = _bbox_of_points(start, end)
        confidence = 0.90  # high: deterministic geometry extraction

        dim_lines.append(
            DimLine(
                start=start,
                end=end,
                length_pts=length,
                is_horizontal=is_horiz,
                is_vertical=is_vert,
                bbox=bbox,
                confidence=confidence,
            )
        )

    logger.info(
        "Page %d: extracted %d dim lines (min_length=%.1f pts)",
        page.number,
        len(dim_lines),
        min_length_pts,
    )
    return dim_lines


def find_nearest_dim_line(
    dim_text: DimTextResult,
    dim_lines: list[DimLine],
    max_distance_pts: float = _DEFAULT_MAX_DISTANCE_PTS,
) -> DimLine | None:
    """Find the dimension line closest to a dim text bounding box.

    Filters by:
    - Euclidean distance between bbox centers ≤ max_distance_pts
    - Orientation match: wide text → horizontal line, tall text → vertical line
    """
    text_bbox = dim_text.bbox
    text_cx = (text_bbox[0] + text_bbox[2]) / 2.0
    text_cy = (text_bbox[1] + text_bbox[3]) / 2.0
    text_width = abs(text_bbox[2] - text_bbox[0])
    text_height = abs(text_bbox[3] - text_bbox[1])
    text_is_horizontal = text_width >= text_height

    best_dist: float = max_distance_pts
    best_line: DimLine | None = None

    for dl in dim_lines:
        # Orientation filter
        if text_is_horizontal and not dl.is_horizontal:
            continue
        if not text_is_horizontal and not dl.is_vertical:
            continue

        # Distance between bbox centers
        line_cx = (dl.bbox[0] + dl.bbox[2]) / 2.0
        line_cy = (dl.bbox[1] + dl.bbox[3]) / 2.0
        dist = math.hypot(line_cx - text_cx, line_cy - text_cy)

        if dist < best_dist:
            best_dist = dist
            best_line = dl

    if best_line is not None:
        logger.debug(
            "Matched dim text %r to line length=%.1f pts at dist=%.1f pts",
            dim_text.raw_text,
            best_line.length_pts,
            best_dist,
        )
    else:
        logger.debug(
            "No dim line found within %.1f pts of dim text %r",
            max_distance_pts,
            dim_text.raw_text,
        )

    return best_line


def pair_dims(
    dim_texts: list[DimTextResult],
    dim_lines: list[DimLine],
) -> list[tuple[DimTextResult, DimLine | None]]:
    """Pair each dim text with its nearest matching dim line.

    Returns a list of (DimTextResult, DimLine | None) tuples.
    A dim text with no matching line is paired with None.
    """
    pairs: list[tuple[DimTextResult, DimLine | None]] = []

    for dt in dim_texts:
        matched = find_nearest_dim_line(dt, dim_lines)
        pairs.append((dt, matched))

    matched_count = sum(1 for _, dl in pairs if dl is not None)
    logger.info(
        "pair_dims: %d dim texts, %d matched to lines, %d unmatched",
        len(dim_texts),
        matched_count,
        len(dim_texts) - matched_count,
    )
    return pairs
