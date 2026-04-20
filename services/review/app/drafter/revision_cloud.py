"""RevisionCloudAgent — Phase 06.

Scans a PDF document for revision-cloud annotations.  Revision clouds appear
in two forms in practice:

1. **Annotation-based**: PDF annotation objects of type PolyLine (type code 8)
   with a red stroke colour, drawn as a closed multi-segment polyline that
   approximates the scalloped arc pattern.

2. **Drawing-based**: red filled or stroked path/ellipse drawing objects on the
   page content stream, typically clustered in an irregular cloud outline.

The agent detects both forms and returns a flat list of ``RevisionCloud``
objects, each carrying the page number (0-based), the bounding box of the
cloud region, and the detected stroke/fill colour.

Red colour threshold: r > 0.7 and g < 0.3 and b < 0.3.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Colour threshold for "red"
# ---------------------------------------------------------------------------

_RED_R_MIN: float = 0.7
_RED_G_MAX: float = 0.3
_RED_B_MAX: float = 0.3


def _is_red(color: tuple[float, float, float] | None) -> bool:
    """Return True when *color* is sufficiently close to red.

    Args:
        color: An (r, g, b) tuple with components in the range [0.0, 1.0],
            or None if no colour is set.

    Returns:
        True when the colour qualifies as red per the defined threshold.
    """
    if color is None:
        return False
    r, g, b = color
    return r > _RED_R_MIN and g < _RED_G_MAX and b < _RED_B_MAX


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class RevisionCloud:
    """A detected revision cloud on a PDF page.

    Attributes:
        page: 0-based page index within the document.
        bbox: Bounding rectangle [x0, y0, x1, y1] in PDF user-space units.
        color: Detected stroke or fill colour as an (r, g, b) tuple.
    """

    page: int
    bbox: list[float]
    color: tuple[float, float, float]


# ---------------------------------------------------------------------------
# Annotation-based detection
# ---------------------------------------------------------------------------


def _detect_annotation_clouds(
    page: fitz.Page,
    page_index: int,
) -> list[RevisionCloud]:
    """Scan PDF annotation objects for red PolyLine annotations.

    Revision clouds created by PDF mark-up tools (e.g. Bluebeam, Adobe
    Acrobat) appear as PolyLine annotation objects (type code 8) with a red
    stroke colour.

    Args:
        page: A PyMuPDF Page object.
        page_index: 0-based index of the page within its parent Document.

    Returns:
        List of RevisionCloud instances found via annotation scanning.
    """
    clouds: list[RevisionCloud] = []
    for annot in page.annots():
        annot_type_code: int = annot.type[0]
        annot_type_name: str = annot.type[1]
        # PolyLine has type code 8; also accept Polygon (type 9) which is
        # sometimes used for closed revision clouds.
        if annot_type_code not in (8, 9) and annot_type_name not in ("PolyLine", "Polygon"):
            continue

        stroke_color: tuple[float, ...] | None = annot.colors.get("stroke")
        if stroke_color is None or len(stroke_color) < 3:
            continue
        rgb: tuple[float, float, float] = (
            float(stroke_color[0]),
            float(stroke_color[1]),
            float(stroke_color[2]),
        )
        if not _is_red(rgb):
            continue

        rect = annot.rect
        clouds.append(
            RevisionCloud(
                page=page_index,
                bbox=[rect.x0, rect.y0, rect.x1, rect.y1],
                color=rgb,
            )
        )

    return clouds


# ---------------------------------------------------------------------------
# Drawing-based detection
# ---------------------------------------------------------------------------


def _detect_drawing_clouds(
    page: fitz.Page,
    page_index: int,
) -> list[RevisionCloud]:
    """Scan the page drawing objects for red filled or stroked ellipsoidal shapes.

    Many CAD applications (e.g. AutoCAD, Revit) export revision clouds as PDF
    content-stream path or ellipse objects rather than annotation objects.
    This function iterates over ``page.get_drawings()`` and collects items
    whose colour matches the red threshold.

    Args:
        page: A PyMuPDF Page object.
        page_index: 0-based index of the page within its parent Document.

    Returns:
        List of RevisionCloud instances found via drawing-stream scanning.
    """
    clouds: list[RevisionCloud] = []

    try:
        drawings = page.get_drawings()
    except Exception as exc:
        logger.warning(
            "RevisionCloudAgent: get_drawings() failed on page %d: %s",
            page_index,
            exc,
        )
        return clouds

    for draw in drawings:
        # Stroke colour check.
        stroke: tuple[float, ...] | None = draw.get("color")
        fill: tuple[float, ...] | None = draw.get("fill")

        stroke_rgb: tuple[float, float, float] | None = None
        fill_rgb: tuple[float, float, float] | None = None

        if stroke and len(stroke) >= 3:
            stroke_rgb = (float(stroke[0]), float(stroke[1]), float(stroke[2]))
        if fill and len(fill) >= 3:
            fill_rgb = (float(fill[0]), float(fill[1]), float(fill[2]))

        detected_color: tuple[float, float, float] | None = None
        if stroke_rgb and _is_red(stroke_rgb):
            detected_color = stroke_rgb
        elif fill_rgb and _is_red(fill_rgb):
            detected_color = fill_rgb

        if detected_color is None:
            continue

        # Bounding rectangle of this drawing path.
        rect = draw.get("rect")
        if rect is None:
            continue

        clouds.append(
            RevisionCloud(
                page=page_index,
                bbox=[
                    float(rect.x0),
                    float(rect.y0),
                    float(rect.x1),
                    float(rect.y1),
                ],
                color=detected_color,
            )
        )

    return clouds


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def detect_revision_clouds(doc: fitz.Document) -> list[RevisionCloud]:
    """Detect all revision clouds in a PDF document.

    Checks every page for both annotation-based PolyLine clouds and
    drawing-stream red ellipsoidal shapes.

    Args:
        doc: An open PyMuPDF Document object.

    Returns:
        A flat list of RevisionCloud objects ordered by page then by position.
        May be empty if no revision clouds are found.
    """
    all_clouds: list[RevisionCloud] = []

    for page_index in range(len(doc)):
        try:
            page: fitz.Page = doc[page_index]
        except Exception as exc:
            logger.warning(
                "RevisionCloudAgent: could not load page %d: %s", page_index, exc
            )
            continue

        annot_clouds = _detect_annotation_clouds(page, page_index)
        drawing_clouds = _detect_drawing_clouds(page, page_index)

        all_clouds.extend(annot_clouds)
        all_clouds.extend(drawing_clouds)

        if annot_clouds or drawing_clouds:
            logger.debug(
                "RevisionCloudAgent: page %d — %d annotation cloud(s), "
                "%d drawing cloud(s)",
                page_index,
                len(annot_clouds),
                len(drawing_clouds),
            )

    logger.info(
        "RevisionCloudAgent: scanned %d page(s), found %d revision cloud(s) total.",
        len(doc),
        len(all_clouds),
    )
    return all_clouds
