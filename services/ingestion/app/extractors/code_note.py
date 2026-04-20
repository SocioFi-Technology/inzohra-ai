"""CodeNoteAgent — extract code-note blocks from architectural drawing sheets.

Strategy: regex heuristic + Claude text extraction.

Phase 1 — Quick heuristic: scan page text for known heading patterns
  (APPLICABLE CODES, DESIGN CRITERIA, OCCUPANCY CLASSIFICATION, etc.).
  If none are found, return [] without spending LLM tokens.

Phase 2 — Claude text extraction: send full page text to Claude and ask it
  to return structured JSON blocks. One CodeNoteExtraction per logical block.

Phase 3 — Bbox enrichment: try to locate each item statement in the page's
  text dict to attach a real bbox; fall back to [0.0, 0.0, 0.0, 0.0].

Invariants upheld:
  - Temperature 0 (invariant #4).
  - Every item carries bbox + confidence (invariant #1).
  - LLM calls logged to call_log_rows.
  - No commit inside this module.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

import fitz  # PyMuPDF

from inzohra_shared.schemas.extraction import CodeNoteExtraction, CodeNoteItem

VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CODE_NOTE_TRIGGERS: list[str] = [
    "APPLICABLE CODES",
    "APPLICABLE CODE",
    "BUILDING CODES",
    "DESIGN CRITERIA",
    "DESIGN CRITERIA:",
    "OCCUPANCY CLASSIFICATION",
    "OCCUPANCY CLASS",
    "CONSTRUCTION TYPE",
    "TYPE OF CONSTRUCTION",
    "CODE ANALYSIS",
    "GENERAL NOTES",
]

_VALID_BLOCK_TYPES: frozenset[str] = frozenset(
    {
        "applicable_codes",
        "design_criteria",
        "occupancy",
        "construction_type",
        "other",
    }
)

_SYS_PROMPT = (
    "You are reading architectural drawing notes. "
    "Extract structured code notes blocks."
)

_USER_PROMPT_TEMPLATE = """{page_text}

---

Return ONLY valid JSON (no markdown fences, no prose) in this exact shape:

[
  {{
    "block_type": "applicable_codes",
    "block_title": "APPLICABLE CODES",
    "items": [
      {{"reference": "2022 CBC", "statement": "2022 California Building Code"}},
      {{"reference": null, "statement": "..."}}
    ]
  }}
]

Rules:
- block_type MUST be one of: "applicable_codes", "design_criteria", \
"occupancy", "construction_type", "other"
- Extract every code note block present on this sheet.
- reference should be the short code citation (e.g. "2022 CBC", "CRC §R301") \
or null if none is present.
- statement is the full text of the line/item.
- Return [] if no code note blocks are found.
"""


# ---------------------------------------------------------------------------
# Phase 1 — Quick heuristic
# ---------------------------------------------------------------------------

def _has_code_note_triggers(page_text: str) -> bool:
    """Return True if any known heading trigger is found (case-insensitive)."""
    text_upper = page_text.upper()
    return any(trigger in text_upper for trigger in _CODE_NOTE_TRIGGERS)


# ---------------------------------------------------------------------------
# Phase 3 — Bbox enrichment
# ---------------------------------------------------------------------------

def _find_text_bbox(statement: str, page: fitz.Page) -> list[float]:
    """Try to find a statement substring in the page's text dict blocks.

    Returns the bbox of the first matching span as [x0, y0, x1, y1] in PDF
    points, or [0.0, 0.0, 0.0, 0.0] if not found.
    """
    if not statement or not statement.strip():
        return [0.0, 0.0, 0.0, 0.0]

    # Use the first ~60 characters as the search key to avoid whitespace issues
    search_key = statement.strip()[:60].upper()

    try:
        text_dict = page.get_text("dict")
    except Exception:  # noqa: BLE001
        return [0.0, 0.0, 0.0, 0.0]

    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:  # 0 = text block
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                span_text = (span.get("text") or "").strip().upper()
                if search_key[:40] in span_text or span_text[:40] in search_key:
                    bbox = span.get("bbox")
                    if bbox and len(bbox) == 4:
                        return list(map(float, bbox))

    return [0.0, 0.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# Phase 2 — Claude text extraction
# ---------------------------------------------------------------------------

def _build_prompt(page_text: str) -> str:
    # Truncate at 8000 chars to stay within reasonable token budget
    truncated = page_text[:8000]
    return _USER_PROMPT_TEMPLATE.format(page_text=truncated)


def _parse_llm_response(
    raw_json: str,
    page: fitz.Page,
) -> list[CodeNoteExtraction]:
    """Parse Claude's JSON response into CodeNoteExtraction objects."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    results: list[CodeNoteExtraction] = []

    for block in data:
        if not isinstance(block, dict):
            continue

        block_type = str(block.get("block_type") or "other").strip()
        if block_type not in _VALID_BLOCK_TYPES:
            block_type = "other"

        block_title = block.get("block_title")
        if block_title is not None:
            block_title = str(block_title).strip() or None

        raw_items: list[Any] = block.get("items") or []
        items: list[CodeNoteItem] = []

        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue

            statement = str(raw_item.get("statement") or "").strip()
            if not statement:
                continue

            reference = raw_item.get("reference")
            if reference is not None:
                reference = str(reference).strip() or None

            bbox = _find_text_bbox(statement, page)

            items.append(
                CodeNoteItem(
                    reference=reference,
                    statement=statement,
                    bbox=bbox,
                    confidence=0.85,
                )
            )

        if not items:
            continue

        results.append(
            CodeNoteExtraction(
                block_type=block_type,
                block_title=block_title,
                items=items,
                confidence=0.85,
            )
        )

    return results


def _call_claude(
    page_text: str,
    *,
    api_key: str,
    model: str,
    call_log_rows: list[dict[str, Any]],
) -> str:
    """Send page text to Claude; return raw response text."""
    import anthropic

    prompt_text = _build_prompt(page_text)
    prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()[:16]

    client = anthropic.Anthropic(api_key=api_key)
    t0 = time.time()
    response = client.messages.create(
        model=model,
        system=_SYS_PROMPT,
        messages=[{"role": "user", "content": prompt_text}],
        max_tokens=4096,
        temperature=0,
    )
    latency_ms = int((time.time() - t0) * 1000)

    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    cost_usd = (tokens_in * 3 + tokens_out * 15) / 1_000_000

    call_log_rows.append({
        "call_id": str(uuid.uuid4()),
        "prompt_hash": prompt_hash,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
        "cost_usd": cost_usd,
        "caller_service": "ingestion.code_note",
    })

    text = "".join(
        b.text for b in response.content if getattr(b, "type", None) == "text"
    ).strip()

    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        ).strip()

    return text


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_code_notes(
    page: fitz.Page,
    *,
    sheet_id: str,
    api_key: str,
    model: str,
    call_log_rows: list[dict[str, Any]],
) -> list[CodeNoteExtraction]:
    """Extract code-note blocks from a PDF page.

    Phase 1: Quick heuristic — skip if no known heading triggers found.
    Phase 2: Claude text extraction — structured JSON extraction.
    Phase 3: Bbox enrichment — locate each item in the page text dict.

    Args:
        page: PyMuPDF page object.
        sheet_id: The sheet_id for this page (unused in extraction, kept for
            API symmetry with other extractors).
        api_key: Anthropic API key.
        model: Claude model identifier.
        call_log_rows: Mutable list; LLM call log dicts are appended here.

    Returns:
        List of CodeNoteExtraction objects (empty if nothing found).
    """
    # Phase 1 — quick heuristic
    page_text = page.get_text()
    if not _has_code_note_triggers(page_text):
        return []

    # Phase 2 — Claude extraction
    if not api_key or api_key.startswith("sk-ant-xxx"):
        return []

    try:
        raw_response = _call_claude(
            page_text,
            api_key=api_key,
            model=model,
            call_log_rows=call_log_rows,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[CodeNoteAgent] LLM call failed: {exc}")
        return []

    if not raw_response:
        return []

    # Phase 3 — parse + bbox enrichment (done inside _parse_llm_response)
    return _parse_llm_response(raw_response, page)
