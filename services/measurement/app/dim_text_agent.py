from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import fitz  # PyMuPDF

VERSION = "1.0.0"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns for architectural dimension strings
# ---------------------------------------------------------------------------

# Feet-and-inches:  24'-6"  /  24'-6 1/2"  /  2'-0"  /  3'6"  /  3\'6"
_FEET_INCHES_RE = re.compile(
    r"""
    \(?                                     # optional opening paren
    (?P<feet>\d+(?:\.\d+)?)                 # feet (integer or decimal)
    \s*                                     # optional space
    ['\u2019\\\-]'?                         # feet separator: ' or \' or - or '
    \s*
    (?P<in_whole>\d+)                       # whole inches
    (?:                                     # optional fractional inches
        \s+(?P<in_num>\d+)/(?P<in_den>\d+)
    )?
    \s*["\u201d]?                           # optional closing inch mark
    \)?                                     # optional closing paren
    """,
    re.VERBOSE,
)

# Inches-only:  36"  /  36.5"
_INCHES_ONLY_RE = re.compile(
    r"""
    \(?
    (?P<inches>\d+(?:\.\d+)?)
    \s*["\u201d]
    \)?
    """,
    re.VERBOSE,
)

# Decimal feet:  2.5'  /  (2.5')
_DECIMAL_FEET_RE = re.compile(
    r"""
    \(?
    (?P<dec_feet>\d+\.\d+)
    \s*['\u2019]
    \)?
    """,
    re.VERBOSE,
)


@dataclass
class DimTextResult:
    """Parsed architectural dimension found on a PDF page."""

    raw_text: str
    value_ft: float       # feet component (0 if inches-only)
    value_in: float       # inches component within the foot (e.g. 6.5 for 6 1/2")
    total_inches: float   # total inches (value_ft * 12 + value_in)
    bbox: list[float]     # [x1, y1, x2, y2] in PDF points
    confidence: float


def parse_dim_string(raw: str) -> tuple[float, float, float] | None:
    """Parse an architectural dimension string.

    Returns (value_ft, value_in_part, total_inches) or None.

    Handles:
      "24'-6\""      → (24.0, 6.0,  294.0)
      "24'-6 1/2\""  → (24.0, 6.5,  294.5)
      "2'-0\""       → (2.0,  0.0,   24.0)
      "36\""         → (0.0, 36.0,   36.0)
      "3\\'6\""      → (3.0,  6.0,   42.0)
      "2.5'"         → (2.5,  0.0,   30.0)
      "(3'-0\")"     → (3.0,  0.0,   36.0)
    """
    stripped = raw.strip()

    # --- Feet + inches (highest priority) ---
    m = _FEET_INCHES_RE.search(stripped)
    if m:
        value_ft = float(m.group("feet"))
        in_whole = float(m.group("in_whole"))
        in_num_str = m.group("in_num")
        in_den_str = m.group("in_den")
        in_frac = (
            float(in_num_str) / float(in_den_str)
            if in_num_str and in_den_str
            else 0.0
        )
        value_in = in_whole + in_frac
        total_inches = value_ft * 12.0 + value_in
        return (value_ft, value_in, total_inches)

    # --- Inches-only ---
    m2 = _INCHES_ONLY_RE.search(stripped)
    if m2:
        total_inches = float(m2.group("inches"))
        return (0.0, total_inches, total_inches)

    # --- Decimal feet ---
    m3 = _DECIMAL_FEET_RE.search(stripped)
    if m3:
        value_ft = float(m3.group("dec_feet"))
        total_inches = value_ft * 12.0
        return (value_ft, 0.0, total_inches)

    return None


def _assign_confidence(raw: str) -> float:
    """Assign base confidence based on dimension format detected."""
    stripped = raw.strip()

    # Feet-and-inches is the most unambiguous architectural format
    if _FEET_INCHES_RE.search(stripped):
        return 0.95

    # Inches-only is common but could be confused with other numeric text
    if _INCHES_ONLY_RE.search(stripped):
        return 0.80

    # Decimal feet is less common in plan sets
    if _DECIMAL_FEET_RE.search(stripped):
        return 0.75

    return 0.60


def extract_dim_texts(
    page: fitz.Page,
    min_confidence: float = 0.60,
) -> list[DimTextResult]:
    """Extract all dimension texts from a page using PyMuPDF native text extraction.

    1. Retrieves all text spans via page.get_text("rawdict").
    2. Attempts parse_dim_string on each span's text.
    3. Filters by min_confidence.
    """
    results: list[DimTextResult] = []

    try:
        raw_dict: dict[str, object] = page.get_text(  # type: ignore[assignment]
            "rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE  # type: ignore[attr-defined]
        )
    except Exception as exc:
        logger.warning(
            "Page %d: get_text('rawdict') failed: %s", page.number, exc
        )
        return results

    blocks: list[dict[str, object]] = raw_dict.get("blocks", [])  # type: ignore[assignment]

    for block in blocks:
        # Only process text blocks (type 0); skip image blocks (type 1)
        if block.get("type") != 0:
            continue

        for line in block.get("lines", []):  # type: ignore[union-attr]
            for span in line.get("spans", []):  # type: ignore[union-attr]
                span_text: str = span.get("text", "")  # type: ignore[assignment]
                if not span_text:
                    continue

                parsed = parse_dim_string(span_text)
                if parsed is None:
                    continue

                value_ft, value_in, total_inches = parsed
                confidence = _assign_confidence(span_text)

                if confidence < min_confidence:
                    logger.debug(
                        "Page %d: dim text %r confidence %.2f < threshold %.2f, skipping",
                        page.number,
                        span_text,
                        confidence,
                        min_confidence,
                    )
                    continue

                # bbox from span: (x0, y0, x1, y1)
                raw_bbox = span.get("bbox", [0.0, 0.0, 0.0, 0.0])
                bbox: list[float] = [float(v) for v in raw_bbox]  # type: ignore[union-attr]

                results.append(
                    DimTextResult(
                        raw_text=span_text,
                        value_ft=value_ft,
                        value_in=value_in,
                        total_inches=total_inches,
                        bbox=bbox,
                        confidence=confidence,
                    )
                )
                logger.debug(
                    "Page %d: extracted dim %r → ft=%.1f in=%.2f total_in=%.2f conf=%.2f",
                    page.number,
                    span_text,
                    value_ft,
                    value_in,
                    total_inches,
                    confidence,
                )

    logger.info(
        "Page %d: extracted %d dimension texts (min_confidence=%.2f)",
        page.number,
        len(results),
        min_confidence,
    )
    return results
