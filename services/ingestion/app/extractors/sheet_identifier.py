"""SheetIdentifierParser — derive discipline / sheet_number / canonical_id / sheet_type.

Deterministic, no LLM. Takes the dual-track ``TitleBlockExtraction`` as input
and produces a normalised ``SheetIdentifier`` suitable for persisting to the
``sheets`` row columns and for plan-integrity rules.

Invariants:
- Provenance preserved: ``bbox`` is copied from the title-block identifier
  field when present; confidence is the minimum of the raw-identifier and
  parsing confidence.
- Never paraphrases. When the raw string cannot be parsed as a valid permit-set
  sheet ID (e.g. vision read "x0.131" or "1"), ``canonical_id`` is ``None``
  and ``discipline_letter`` is ``None`` — never fabricated.
"""
from __future__ import annotations

from inzohra_shared.schemas.extraction import SheetIdentifier, TitleBlockExtraction
from inzohra_shared.taxonomy import (
    classify_sheet_type,
    parse_sheet_identifier,
)

VERSION = "1.0.0"


def extract_sheet_identifier(tb: TitleBlockExtraction) -> SheetIdentifier:
    """Parse a ``TitleBlockExtraction`` into a canonical ``SheetIdentifier``.

    The returned object is always well-formed; unparseable fields become
    ``None`` with a confidence penalty rather than being fabricated.
    """
    raw_field = tb.sheet_identifier_raw
    title_field = tb.sheet_title

    raw_value = (raw_field.value or "").strip() if raw_field and raw_field.value else None
    title_value = (title_field.value or "").strip() if title_field and title_field.value else None

    parsed = parse_sheet_identifier(raw_value)
    if parsed is None:
        # Could not interpret as a sheet ID — preserve raw, everything else None
        discipline = None
        number = None
        canonical = None
        # Low parse confidence but do not drop the original extraction fully
        parse_conf = 0.0 if raw_value else 0.0
    else:
        discipline, number, canonical = parsed
        parse_conf = 1.0

    sheet_type = classify_sheet_type(title_value, discipline)

    # Composite confidence = min(raw-field conf, parse conf); parse is 0/1.
    raw_conf = raw_field.confidence if raw_field else 0.0
    title_conf = title_field.confidence if title_field else 0.0
    overall = min(raw_conf, parse_conf) if parse_conf else raw_conf * 0.3

    # If we have a good title match but no parseable ID, that still gives us
    # sheet_type — acknowledge that with a floor on confidence.
    if canonical is None and sheet_type != "unknown" and title_conf > 0:
        overall = max(overall, title_conf * 0.5)

    bbox = raw_field.bbox if raw_field and raw_field.bbox else [0.0, 0.0, 0.0, 0.0]

    return SheetIdentifier(
        raw_id=raw_value,
        canonical_id=canonical,
        discipline_letter=discipline,
        sheet_number=number,
        sheet_type=sheet_type,
        sheet_title=title_value,
        confidence=float(max(0.0, min(1.0, overall))),
        bbox=list(bbox),
    )
