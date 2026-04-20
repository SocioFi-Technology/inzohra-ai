from __future__ import annotations

import logging
from collections import Counter

import fitz  # PyMuPDF

VERSION = "1.0.0"

logger = logging.getLogger(__name__)


def classify_page(page: fitz.Page) -> tuple[str, float]:
    """Classify a PyMuPDF page's rendering quality.

    Returns a tuple of (class, confidence) where class is one of:
        "vector", "hybrid", "raster", "low_quality_scan"
    """
    try:
        drawings = page.get_drawings()
    except Exception as exc:
        logger.warning("get_drawings() failed on page %s: %s", page.number, exc)
        drawings = []

    drawing_count: int = len(drawings)

    try:
        raw_dict = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)  # type: ignore[attr-defined]
        image_blocks: list[object] = [
            b for b in raw_dict.get("blocks", []) if b.get("type") == 1  # type: ignore[union-attr]
        ]
    except Exception as exc:
        logger.warning("get_text('rawdict') failed on page %s: %s", page.number, exc)
        image_blocks = []

    image_count: int = len(image_blocks)

    # Vector: many drawings, almost no raster images
    if drawing_count > 50 and image_count < 2:
        return ("vector", 0.95)

    # Hybrid: meaningful drawings AND raster images
    if drawing_count > 20 and image_count > 0:
        return ("hybrid", 0.85)

    # Raster-dominant: few drawings, at least one image
    if drawing_count < 5 and image_count > 0:
        # Check resolution of first embedded image
        try:
            page_images = page.get_images(full=True)
        except Exception as exc:
            logger.warning("get_images() failed on page %s: %s", page.number, exc)
            page_images = []

        if page_images:
            # xres is index 8 in the tuple returned by get_images(full=True)
            # Tuple: (xref, smask, width, height, bpc, colorspace, alt_colorspace, name, filter, referencer)
            # Resolution fields are in a separate call; use get_image_info for resolution
            try:
                image_info_list = page.get_image_info(hashes=False)
            except Exception as exc:
                logger.warning(
                    "get_image_info() failed on page %s: %s", page.number, exc
                )
                image_info_list = []

            xres: float = 0.0
            if image_info_list:
                xres = float(image_info_list[0].get("xres", 0) or 0)

            if xres > 0 and xres < 150:
                return ("low_quality_scan", 0.80)

        return ("raster", 0.85)

    # Default fallback
    return ("raster", 0.70)


# ---------------------------------------------------------------------------
# Phase 09 additions — PDF quality pipeline integration
# ---------------------------------------------------------------------------

# Penalty multipliers applied per pdf_quality_class
CONFIDENCE_PENALTIES: dict[str, float] = {
    "vector": 1.0,
    "hybrid": 0.92,
    "raster": 0.80,
    "low_quality_scan": 0.55,
}

# Measurement types disabled on low_quality_scan (require calibration anchors)
DISABLED_ON_LOW_QUALITY: frozenset[str] = frozenset({
    "egress_distance",
    "door_clear_width",
    "accessible_route_width",
    "accessible_route_slope",
})


def apply_quality_penalty(
    measurement_type: str,
    raw_confidence: float,
    pdf_quality_class: str,
) -> tuple[float, str | None]:
    """Return (adjusted_confidence, skip_reason).

    skip_reason is non-None when the measurement should be skipped entirely
    (e.g. egress_distance on a low_quality_scan).
    """
    if pdf_quality_class == "low_quality_scan" and measurement_type in DISABLED_ON_LOW_QUALITY:
        return 0.0, f"disabled on {pdf_quality_class} — provide calibration anchors"
    penalty = CONFIDENCE_PENALTIES.get(pdf_quality_class, 1.0)
    return round(raw_confidence * penalty, 4), None


def classify_sheet(
    database_url: str,
    sheet_id: str,
    *,
    pdf_bytes: bytes | None = None,
) -> tuple[str, float]:
    """Classify a sheet's PDF quality class.

    If pdf_bytes is provided, runs the full PyMuPDF classification and
    persists the result to sheets.pdf_quality_class.
    If pdf_bytes is None, reads the stored value from the DB.
    Returns ("vector", 1.0) as default if neither is available.
    """
    import psycopg  # local import — optional dep not needed by classify_page callers

    if pdf_bytes is not None:
        doc = fitz.Document(stream=pdf_bytes, filetype="pdf")
        try:
            page = doc.load_page(0)
            quality_class, confidence = classify_page(page)
        finally:
            doc.close()

        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE sheets SET pdf_quality_class = %s WHERE sheet_id = %s",
                    (quality_class, sheet_id),
                )
            conn.commit()

        logger.info(
            "classify_sheet: sheet_id=%s classified as '%s' (confidence=%.2f)",
            sheet_id,
            quality_class,
            confidence,
        )
        return quality_class, confidence

    # No PDF bytes — read stored value from DB
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pdf_quality_class FROM sheets WHERE sheet_id = %s",
                (sheet_id,),
            )
            row = cur.fetchone()

    if row and row[0]:
        stored_class: str = row[0]
        penalty = CONFIDENCE_PENALTIES.get(stored_class, 1.0)
        return stored_class, penalty

    logger.warning(
        "classify_sheet: no pdf_bytes and no stored class for sheet_id=%s; defaulting to 'vector'",
        sheet_id,
    )
    return "vector", 1.0


def classify_document(doc: fitz.Document) -> str:
    """Classify a document by majority vote across all pages."""
    counts: Counter[str] = Counter()

    for page_index in range(len(doc)):
        page = doc.load_page(page_index)
        page_class, _confidence = classify_page(page)
        counts[page_class] += 1
        logger.debug(
            "Page %d classified as '%s'", page_index, page_class
        )

    if not counts:
        logger.warning("Document has no pages; defaulting to 'raster'")
        return "raster"

    majority_class, majority_count = counts.most_common(1)[0]
    logger.info(
        "Document classification: '%s' (%d/%d pages)",
        majority_class,
        majority_count,
        len(doc),
    )
    return majority_class
