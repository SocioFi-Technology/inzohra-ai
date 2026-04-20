from __future__ import annotations

import logging
import re
from dataclasses import dataclass

VERSION = "1.0.0"

logger = logging.getLogger(__name__)

# Default scale: 1/4" = 1'-0"
_DEFAULT_PTS_PER_REAL_INCH: float = 1.5  # 72 * 0.25 / 12
_DEFAULT_CONFIDENCE: float = 0.50
_DEFAULT_SOURCE: str = "default"
_DEFAULT_DECLARED: str = '1/4" = 1\'-0"'

# Regex patterns for scale string parsing

# Matches: 1/4" = 1'-0"  or  3/16" = 1'-0"  or  1" = 1'-0"  etc.
# Handles all separator combos: 1'-0" (foot+hyphen), 1'0" (foot only), 1-0" (hyphen only)
_ARCH_FRAC_RE = re.compile(
    r"""
    ^\s*
    (?P<num>\d+)               # numerator (e.g. 1, 3)
    (?:/(?P<den>\d+))?         # optional /denominator (e.g. /4, /16)
    \s*["\u2019\u201d']\s*     # inch marker (", ', curly variants)
    =\s*
    (?P<feet>\d+)              # real feet
    \s*(?:['\u2019]\s*-?|-)\s* # feet separator: foot-mark (optionally + hyphen) OR hyphen alone
    (?P<in_whole>\d+)          # whole inches part (usually 0)
    (?:\s*(?P<in_num>\d+)/(?P<in_den>\d+))?   # optional fractional inches
    \s*["\u201d]?              # closing inch marker
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Matches: 1:48  or  1 : 100
_RATIO_RE = re.compile(
    r"""
    ^\s*1\s*:\s*(?P<denominator>\d+(?:\.\d+)?)\s*$
    """,
    re.VERBOSE,
)

# Matches decimal-inch scales like: 0.25" = 1'-0"
_DECIMAL_INCH_RE = re.compile(
    r"""
    ^\s*
    (?P<paper_dec>\d+(?:\.\d+)?)   # decimal paper measurement
    \s*["\u2019\u201d]\s*          # inch marker
    =\s*
    (?P<feet>\d+)                  # real feet
    \s*(?:['\u2019]\s*-?|-)\s*     # feet separator: foot-mark (optionally + hyphen) OR hyphen alone
    (?P<in_whole>\d+)
    \s*["\u201d]?
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)


def parse_scale_string(scale_str: str) -> float | None:
    """Parse a declared scale string to pts_per_real_inch.

    Supports:
      '1/4" = 1\\'-0"'   → 72 * 0.25 / 12 = 1.5
      '3/16" = 1\\'-0"'  → 72 * 0.1875 / 12 = 1.125
      '1/8" = 1\\'-0"'   → 72 * 0.125 / 12 = 0.75
      '3/8" = 1\\'-0"'   → 72 * 0.375 / 12 = 2.25
      '1" = 1\\'-0"'     → 72 * 1.0 / 12 = 6.0
      '1:48'             → 72 / 48 = 1.5

    Returns pts_per_real_inch or None if unparseable.
    """
    cleaned = scale_str.strip()

    # Try ratio pattern first (simplest)
    ratio_match = _RATIO_RE.match(cleaned)
    if ratio_match:
        denominator = float(ratio_match.group("denominator"))
        if denominator <= 0:
            logger.warning("Scale ratio denominator is zero or negative: %r", scale_str)
            return None
        result = 72.0 / denominator
        logger.debug("Parsed ratio scale %r → pts_per_real_inch=%.4f", scale_str, result)
        return result

    # Try architectural fractional: 1/4" = 1'-0"
    arch_match = _ARCH_FRAC_RE.match(cleaned)
    if arch_match:
        num = float(arch_match.group("num"))
        den_str = arch_match.group("den")
        den = float(den_str) if den_str else 1.0
        if den <= 0:
            logger.warning("Scale string has zero denominator: %r", scale_str)
            return None

        paper_frac = num / den  # e.g. 0.25 for 1/4

        real_feet = float(arch_match.group("feet"))
        in_whole = float(arch_match.group("in_whole"))
        in_num_str = arch_match.group("in_num")
        in_den_str = arch_match.group("in_den")
        in_frac = (
            float(in_num_str) / float(in_den_str)
            if in_num_str and in_den_str
            else 0.0
        )
        real_inches_total = real_feet * 12.0 + in_whole + in_frac

        if real_inches_total <= 0:
            logger.warning("Scale string resolves to zero real inches: %r", scale_str)
            return None

        result = 72.0 * paper_frac / real_inches_total
        logger.debug(
            "Parsed arch scale %r → paper_frac=%.4f real_in=%.2f pts_per_real_inch=%.4f",
            scale_str,
            paper_frac,
            real_inches_total,
            result,
        )
        return result

    # Try decimal-inch: 0.25" = 1'-0"
    dec_match = _DECIMAL_INCH_RE.match(cleaned)
    if dec_match:
        paper_dec = float(dec_match.group("paper_dec"))
        real_feet = float(dec_match.group("feet"))
        in_whole = float(dec_match.group("in_whole"))
        real_inches_total = real_feet * 12.0 + in_whole

        if real_inches_total <= 0:
            logger.warning("Decimal scale string resolves to zero real inches: %r", scale_str)
            return None

        result = 72.0 * paper_dec / real_inches_total
        logger.debug(
            "Parsed decimal scale %r → pts_per_real_inch=%.4f", scale_str, result
        )
        return result

    logger.warning("Could not parse scale string: %r", scale_str)
    return None


@dataclass
class SheetScaleResult:
    """Result of resolving a sheet's drawing scale."""

    sheet_id: str
    declared: str | None
    pts_per_real_inch: float
    calibrated: bool
    calibration_confidence: float
    source: str  # "title_block" | "calibrated" | "default"
    confidence: float


def resolve_sheet_scale(
    sheet_id: str,
    declared_scale: str | None,
    title_block_payload: dict[str, object] | None = None,
) -> SheetScaleResult:
    """Resolve scale for a sheet.

    Resolution order:
    1. declared_scale argument (if provided and parseable)
    2. title_block_payload['scale_declared']['value'] (if provided and parseable)
    3. Default 1/4" = 1'-0" at confidence 0.50
    """
    # --- Attempt 1: declared_scale argument ---
    if declared_scale:
        pts = parse_scale_string(declared_scale)
        if pts is not None:
            logger.info(
                "Sheet %s: resolved scale from declared argument %r → %.4f pts/in",
                sheet_id,
                declared_scale,
                pts,
            )
            return SheetScaleResult(
                sheet_id=sheet_id,
                declared=declared_scale,
                pts_per_real_inch=pts,
                calibrated=False,
                calibration_confidence=0.0,
                source="title_block",
                confidence=0.85,
            )
        logger.warning(
            "Sheet %s: declared_scale %r not parseable, falling through",
            sheet_id,
            declared_scale,
        )

    # --- Attempt 2: title_block_payload ---
    if title_block_payload:
        scale_declared = title_block_payload.get("scale_declared")
        if isinstance(scale_declared, dict):
            tb_scale_value = scale_declared.get("value")
            tb_confidence = scale_declared.get("confidence", 0.70)
            if isinstance(tb_scale_value, str) and tb_scale_value.strip():
                pts = parse_scale_string(tb_scale_value)
                if pts is not None:
                    confidence = float(tb_confidence) if isinstance(tb_confidence, (int, float)) else 0.70
                    logger.info(
                        "Sheet %s: resolved scale from title_block %r → %.4f pts/in (confidence=%.2f)",
                        sheet_id,
                        tb_scale_value,
                        pts,
                        confidence,
                    )
                    return SheetScaleResult(
                        sheet_id=sheet_id,
                        declared=tb_scale_value,
                        pts_per_real_inch=pts,
                        calibrated=False,
                        calibration_confidence=0.0,
                        source="title_block",
                        confidence=confidence,
                    )
                logger.warning(
                    "Sheet %s: title_block scale value %r not parseable",
                    sheet_id,
                    tb_scale_value,
                )

    # --- Attempt 3: default ---
    logger.warning(
        "Sheet %s: no parseable scale found; using default %r",
        sheet_id,
        _DEFAULT_DECLARED,
    )
    return SheetScaleResult(
        sheet_id=sheet_id,
        declared=_DEFAULT_DECLARED,
        pts_per_real_inch=_DEFAULT_PTS_PER_REAL_INCH,
        calibrated=False,
        calibration_confidence=0.0,
        source=_DEFAULT_SOURCE,
        confidence=_DEFAULT_CONFIDENCE,
    )
