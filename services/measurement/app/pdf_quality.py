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
