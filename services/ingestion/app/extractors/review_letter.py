"""ReviewLetterAgent — structured extractor for Bureau Veritas plan-check letters.

Invariants upheld:
- Every comment carries page_number, bbox, confidence (invariant #1).
- Temperature is always 0 for the LLM call              (invariant #4).
- No code text is paraphrased; agent touches only the letter (invariant #3).
- VERSION = "1.0.0"; bump on any schema or prompt change  (house-rule).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from typing import Any

import fitz  # PyMuPDF

from inzohra_shared.schemas.extraction import ReviewLetterComment, ReviewLetterExtraction

# ---------------------------------------------------------------------------
# Agent version — bump whenever the prompt or output schema changes.
# ---------------------------------------------------------------------------
VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Discipline normalisation map (group header → canonical discipline slug)
# ---------------------------------------------------------------------------
_DISCIPLINE_MAP: dict[str, str] = {
    "ARCHITECTURE": "architectural",
    "ARCHITECTURAL": "architectural",
    "STRUCTURAL": "structural",
    "MECHANICAL": "mechanical",
    "ELECTRICAL": "electrical",
    "PLUMBING": "plumbing",
    "ENERGY": "energy",
    "FIRE": "fire_life_safety",
    "FIRE LIFE SAFETY": "fire_life_safety",
    "FIRE & LIFE SAFETY": "fire_life_safety",
    "ACCESSIBILITY": "accessibility",
    "CALGREEN": "calgreen",
    "GREEN": "calgreen",
    "CAL GREEN": "calgreen",
    "PLAN INTEGRITY": "plan_integrity",
}

# ---------------------------------------------------------------------------
# PyMuPDF span-flag bit masks
# ---------------------------------------------------------------------------
_FLAG_ITALIC = 1 << 1     # bit 1
_FLAG_BOLD = 1 << 4       # bit 4
_FLAG_UNDERLINE = 1 << 2  # bit 2 (not always set by PDF producers; also check underline key)

# ---------------------------------------------------------------------------
# Regex patterns for discipline group headers and comment numbering
# ---------------------------------------------------------------------------
_GROUP_HEADER_RE = re.compile(
    r"^\s*([A-Z][A-Z\s&/]{2,30})\s*$"
)
_COMMENT_NUMBER_RE = re.compile(
    r"^\s*(?:comment\s*#?\s*)?(\d{1,3})\s*[.):]\s+(.+)",
    re.IGNORECASE | re.DOTALL,
)
_COMMENT_NUMBER_START_RE = re.compile(
    r"^\s*(?:comment\s*#?\s*)?(\d{1,3})\s*[.):]\s*$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = (
    "You are an expert permit plan-check letter parser for California jurisdictions. "
    "Parse the provided text from a Bureau Veritas (or similar agency) plan-check letter "
    "and return structured JSON. Be literal — only report text you can read in the document. "
    "Return ONLY a valid JSON object. No markdown fences, no extra commentary."
)

_USER_PROMPT_TEMPLATE = """Parse this plan-check letter text and return a JSON object with this exact schema:

{{
  "project_name": "string or null",
  "project_address": "string or null",
  "permit_number": "string or null",
  "reviewer_name": "string or null",
  "review_date": "string or null",
  "comments": [
    {{
      "comment_number": 1,
      "discipline_group": "ARCHITECTURE",
      "discipline": "architectural",
      "review_round": 1,
      "typography": null,
      "comment_text": "full comment text",
      "citation_text": "CBC §107.2.1 or null",
      "sheet_reference": "Sheet A-1.1 or null",
      "page_number": 1
    }}
  ]
}}

Rules:
- comment_number: the integer identifying each comment (1, 2, 3, …)
- discipline_group: the ALL-CAPS section header above the comment group (e.g. "ARCHITECTURE", "STRUCTURAL")
- discipline: normalised slug — one of: architectural, structural, mechanical, electrical, plumbing, energy, fire_life_safety, accessibility, calgreen, plan_integrity
- review_round: 1 by default; 2 if comment is a response/resubmittal note; 3 if a second resubmittal
- typography: null | "bold" | "italic" | "underlined" — indicate the dominant typographic style of the comment text
- comment_text: the full text of the comment/correction item
- citation_text: any explicit code citation mentioned (e.g. "CBC §107.2.1", "CRC R310.2.1")
- sheet_reference: any sheet reference mentioned (e.g. "Sheet A-1.1", "Sheets A-2.0 & A-2.1")
- page_number: 1-based page number where this comment appears

PAGE TEXT:
{page_text}
"""

# ---------------------------------------------------------------------------
# Text-extraction helpers
# ---------------------------------------------------------------------------

def _extract_page_data(page: fitz.Page) -> dict[str, Any]:
    """Extract structured text data from a page, including spans with typography flags."""
    raw = page.get_text("dict", sort=True)
    blocks_out: list[dict[str, Any]] = []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        lines_out: list[dict[str, Any]] = []
        for line in block.get("lines", []):
            spans_out: list[dict[str, Any]] = []
            for span in line.get("spans", []):
                text = span.get("text", "")
                if not text.strip():
                    continue
                flags: int = span.get("flags", 0)
                is_bold = bool(flags & _FLAG_BOLD)
                is_italic = bool(flags & _FLAG_ITALIC)
                is_underline = bool(flags & _FLAG_UNDERLINE) or span.get("color") == 0  # heuristic
                # PyMuPDF also provides a dedicated underline key in some builds
                if not is_underline and span.get("underline", False):
                    is_underline = True
                spans_out.append({
                    "text": text,
                    "bbox": list(span["bbox"]),
                    "bold": is_bold,
                    "italic": is_italic,
                    "underline": is_underline,
                    "flags": flags,
                })
            if spans_out:
                line_text = "".join(s["text"] for s in spans_out)
                # Dominant typography: bold > underline > italic (first wins)
                bold_chars = sum(len(s["text"]) for s in spans_out if s["bold"])
                italic_chars = sum(len(s["text"]) for s in spans_out if s["italic"])
                underline_chars = sum(len(s["text"]) for s in spans_out if s["underline"])
                total_chars = len(line_text)
                if total_chars > 0:
                    if bold_chars / total_chars >= 0.5:
                        dominant = "bold"
                    elif underline_chars / total_chars >= 0.5:
                        dominant = "underlined"
                    elif italic_chars / total_chars >= 0.5:
                        dominant = "italic"
                    else:
                        dominant = None
                else:
                    dominant = None
                lines_out.append({
                    "text": line_text,
                    "bbox": list(line["bbox"]),
                    "dominant_typography": dominant,
                    "spans": spans_out,
                })
        if lines_out:
            blocks_out.append({
                "bbox": list(block["bbox"]),
                "lines": lines_out,
            })
    return {"blocks": blocks_out, "page_width": page.rect.width, "page_height": page.rect.height}


def _build_page_text(page_data: dict[str, Any]) -> str:
    """Build a flat text string from page_data for feeding to the LLM."""
    lines: list[str] = []
    for block in page_data["blocks"]:
        for line in block["lines"]:
            lines.append(line["text"])
        lines.append("")  # blank line between blocks
    return "\n".join(lines)


def _extract_metadata_from_page1(page_data: dict[str, Any]) -> dict[str, str | None]:
    """Heuristically extract project metadata from page 1 text."""
    all_text = _build_page_text(page_data)

    project_name: str | None = None
    project_address: str | None = None
    permit_number: str | None = None
    reviewer_name: str | None = None
    review_date: str | None = None

    for pattern, key in [
        (r"project\s*name[:\s]+([^\n]+)", "project_name"),
        (r"project[:\s]+([^\n]+)", "project_name"),
        (r"job\s*(?:name|title)[:\s]+([^\n]+)", "project_name"),
    ]:
        m = re.search(pattern, all_text, re.IGNORECASE)
        if m and project_name is None:
            project_name = m.group(1).strip()

    for pattern in [
        r"(?:project\s*)?address[:\s]+([^\n]+)",
        r"site\s*address[:\s]+([^\n]+)",
        r"property\s*address[:\s]+([^\n]+)",
        r"(\d{3,5}\s+\w[\w\s]{2,30}(?:lane|ln|street|st|avenue|ave|blvd|road|rd|drive|dr|way|court|ct|place|pl)[^\n]{0,60})",
    ]:
        m = re.search(pattern, all_text, re.IGNORECASE)
        if m and project_address is None:
            project_address = m.group(1).strip()

    for pattern in [
        r"permit\s*(?:no|number|#|num)[:\s.]*([A-Z0-9\-]+)",
        r"(B\d{2}-\d{4})",
        r"plan\s*check\s*(?:no|number|#)[:\s]+([A-Z0-9\-]+)",
    ]:
        m = re.search(pattern, all_text, re.IGNORECASE)
        if m and permit_number is None:
            permit_number = m.group(1).strip()

    for pattern in [
        r"(?:plan\s*checker|reviewer|reviewed\s*by|checked\s*by|prepared\s*by)[:\s]+([^\n]+)",
        r"(?:engineer|inspector)[:\s]+([^\n]+)",
    ]:
        m = re.search(pattern, all_text, re.IGNORECASE)
        if m and reviewer_name is None:
            reviewer_name = m.group(1).strip()

    for pattern in [
        r"(?:date|reviewed|issued)[:\s]+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
        r"(?:date|reviewed|issued)[:\s]+(\w+\s+\d{1,2},?\s+\d{4})",
        r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})",
    ]:
        m = re.search(pattern, all_text, re.IGNORECASE)
        if m and review_date is None:
            review_date = m.group(1).strip()

    return {
        "project_name": project_name,
        "project_address": project_address,
        "permit_number": permit_number,
        "reviewer_name": reviewer_name,
        "review_date": review_date,
    }


def _build_bbox_index(page_data: dict[str, Any], page_number: int) -> dict[str, tuple[int, list[float]]]:
    """Build index: normalised line text → (page_number, bbox) for first-line bbox lookup."""
    index: dict[str, tuple[int, list[float]]] = {}
    for block in page_data["blocks"]:
        for line in block["lines"]:
            key = line["text"].strip().lower()[:60]
            if key and key not in index:
                index[key] = (page_number, line["bbox"])
    return index


def _lookup_comment_bbox(
    comment_number: int,
    comment_text: str,
    bbox_index: dict[str, tuple[int, list[float]]],
) -> list[float]:
    """Try to find the bbox for the first line of a comment in the index."""
    # Try matching the comment number prefix
    for prefix_template in [
        f"{comment_number}. ",
        f"{comment_number}) ",
        f"{comment_number}: ",
        f"comment {comment_number}",
        f"comment #{comment_number}",
    ]:
        for key, (_, bbox) in bbox_index.items():
            if key.startswith(prefix_template.lower()):
                return bbox

    # Try matching the start of comment_text
    if comment_text:
        first_words = comment_text.strip().lower()[:40]
        for key, (_, bbox) in bbox_index.items():
            if key and first_words and key[:len(first_words)] == first_words[:len(key)]:
                return bbox

    return [0.0, 0.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------

def _call_llm_for_page_batch(
    page_texts: list[tuple[int, str]],
    *,
    api_key: str,
    model: str,
    call_log_rows: list[dict[str, object]],
) -> dict[str, Any] | None:
    """Send a batch of page texts to Claude and return the parsed JSON dict."""
    if not api_key or api_key.startswith("sk-ant-xxx"):
        return None

    combined_text = ""
    for page_num, text in page_texts:
        combined_text += f"\n--- PAGE {page_num} ---\n{text}\n"

    prompt_text = _USER_PROMPT_TEMPLATE.format(page_text=combined_text)
    prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()[:16]

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)
        t0 = time.perf_counter()

        response = client.messages.create(
            model=model,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt_text}],
            max_tokens=4096,
            temperature=0,  # invariant #4
        )

        latency_ms = int((time.perf_counter() - t0) * 1000)
        text_out = "".join(
            b.text for b in response.content if getattr(b, "type", None) == "text"
        )

        call_log_rows.append({
            "call_id": str(uuid.uuid4()),
            "prompt_hash": prompt_hash,
            "model": model,
            "tokens_in": response.usage.input_tokens,
            "tokens_out": response.usage.output_tokens,
            "latency_ms": latency_ms,
            "cost_usd": 0.0,
            "caller_service": "ingestion.review_letter",
        })

        # Strip markdown fences if any
        text_out = re.sub(r"^```(?:json)?\s*|\s*```$", "", text_out.strip())
        return json.loads(text_out)

    except Exception as exc:  # noqa: BLE001
        print(f"[ReviewLetterAgent] LLM call failed: {exc}")
        return None


def _normalise_discipline(discipline_group: str | None, discipline: str | None) -> str | None:
    """Resolve discipline from group header or raw discipline string."""
    if discipline_group:
        key = discipline_group.strip().upper()
        if key in _DISCIPLINE_MAP:
            return _DISCIPLINE_MAP[key]
        # Try partial match
        for map_key, map_val in _DISCIPLINE_MAP.items():
            if map_key in key or key in map_key:
                return map_val
    if discipline:
        slug = discipline.strip().lower()
        # Accept already-normalised slugs
        valid = {
            "architectural", "structural", "mechanical", "electrical",
            "plumbing", "energy", "fire_life_safety", "accessibility",
            "calgreen", "plan_integrity",
        }
        if slug in valid:
            return slug
        # Map common variations
        for map_key, map_val in _DISCIPLINE_MAP.items():
            if slug == map_key.lower() or slug == map_val:
                return map_val
    return None


def _determine_round(typography: str | None, llm_round: int | None) -> int:
    """Bold → round 2; underlined → round 3; else respect LLM or default 1."""
    if typography == "bold":
        return 2
    if typography == "underlined":
        return 3
    if isinstance(llm_round, int) and llm_round >= 1:
        return llm_round
    return 1


def _build_comments_from_llm(
    llm_data: dict[str, Any],
    bbox_index: dict[str, tuple[int, list[float]]],
) -> list[ReviewLetterComment]:
    """Construct ReviewLetterComment list from LLM JSON output."""
    raw_comments: list[dict[str, Any]] = llm_data.get("comments", [])
    if not isinstance(raw_comments, list):
        return []

    comments: list[ReviewLetterComment] = []
    for raw in raw_comments:
        if not isinstance(raw, dict):
            continue

        comment_number = raw.get("comment_number")
        if not isinstance(comment_number, int):
            try:
                comment_number = int(comment_number)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue

        comment_text: str = raw.get("comment_text", "")
        if not isinstance(comment_text, str):
            comment_text = str(comment_text)
        comment_text = comment_text.strip()
        if not comment_text:
            continue

        discipline_group: str | None = raw.get("discipline_group")
        discipline_raw: str | None = raw.get("discipline")
        discipline = _normalise_discipline(discipline_group, discipline_raw)

        typography: str | None = raw.get("typography")
        if typography not in ("bold", "italic", "underlined", None):
            typography = None

        llm_round: int | None = raw.get("review_round")
        review_round = _determine_round(typography, llm_round)

        page_number: int = raw.get("page_number", 1)
        if not isinstance(page_number, int):
            try:
                page_number = int(page_number)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                page_number = 1

        citation_text: str | None = raw.get("citation_text")
        if citation_text and not isinstance(citation_text, str):
            citation_text = str(citation_text)
        if citation_text:
            citation_text = citation_text.strip() or None

        sheet_reference: str | None = raw.get("sheet_reference")
        if sheet_reference and not isinstance(sheet_reference, str):
            sheet_reference = str(sheet_reference)
        if sheet_reference:
            sheet_reference = sheet_reference.strip() or None

        bbox = _lookup_comment_bbox(comment_number, comment_text, bbox_index)

        comments.append(ReviewLetterComment(
            comment_number=comment_number,
            discipline_group=discipline_group,
            discipline=discipline,
            review_round=review_round,
            typography=typography,
            comment_text=comment_text,
            citation_text=citation_text,
            sheet_reference=sheet_reference,
            page_number=page_number,
            bbox=bbox,
            confidence=0.9 if comment_text else 0.3,
        ))

    return comments


def _build_comments_from_text(
    pages_data: list[tuple[int, dict[str, Any]]],
) -> list[ReviewLetterComment]:
    """Fallback: heuristic comment extraction from raw page data when LLM unavailable."""
    comments: list[ReviewLetterComment] = []
    current_group: str | None = None
    current_discipline: str | None = None
    pending_number: int | None = None
    pending_lines: list[str] = []
    pending_bbox: list[float] = [0.0, 0.0, 0.0, 0.0]
    pending_page: int = 1
    pending_typography: str | None = None

    def _flush_pending() -> None:
        nonlocal pending_number, pending_lines, pending_bbox, pending_page, pending_typography
        if pending_number is not None and pending_lines:
            text = " ".join(pending_lines).strip()
            # Extract citations
            citation_match = re.search(
                r"(C(?:BC|RC|MC|PC|GC|EC|FC)\s*§?\s*[\d\.]+(?:\.\d+)*(?:\s+Table\s+[\w\.\-]+)?)",
                text, re.IGNORECASE,
            )
            citation_text = citation_match.group(1).strip() if citation_match else None

            sheet_match = re.search(
                r"(?:sheet|dwg|drawing)s?\s*([A-Z]-?\d+\.\d+(?:\s*[,&]\s*[A-Z]-?\d+\.\d+)*)",
                text, re.IGNORECASE,
            )
            sheet_reference = sheet_match.group(0).strip() if sheet_match else None

            comments.append(ReviewLetterComment(
                comment_number=pending_number,
                discipline_group=current_group,
                discipline=current_discipline,
                review_round=_determine_round(pending_typography, None),
                typography=pending_typography,
                comment_text=text,
                citation_text=citation_text,
                sheet_reference=sheet_reference,
                page_number=pending_page,
                bbox=pending_bbox,
                confidence=0.7,
            ))
        pending_number = None
        pending_lines = []
        pending_bbox = [0.0, 0.0, 0.0, 0.0]
        pending_typography = None

    for page_number, page_data in pages_data:
        for block in page_data["blocks"]:
            for line in block["lines"]:
                line_text = line["text"].strip()
                if not line_text:
                    continue

                # Check for discipline group header
                grp_match = _GROUP_HEADER_RE.match(line_text)
                if grp_match:
                    candidate = grp_match.group(1).strip().upper()
                    if candidate in _DISCIPLINE_MAP:
                        _flush_pending()
                        current_group = candidate
                        current_discipline = _DISCIPLINE_MAP[candidate]
                        continue

                # Check for comment number
                num_match = _COMMENT_NUMBER_RE.match(line_text)
                if num_match:
                    _flush_pending()
                    pending_number = int(num_match.group(1))
                    pending_lines = [num_match.group(2).strip()]
                    pending_bbox = line["bbox"]
                    pending_page = page_number
                    pending_typography = line.get("dominant_typography")
                    continue

                # Check for lone comment number on its own line
                num_only_match = _COMMENT_NUMBER_START_RE.match(line_text)
                if num_only_match:
                    _flush_pending()
                    pending_number = int(num_only_match.group(1))
                    pending_lines = []
                    pending_bbox = line["bbox"]
                    pending_page = page_number
                    pending_typography = line.get("dominant_typography")
                    continue

                # Continuation line for current comment
                if pending_number is not None:
                    pending_lines.append(line_text)
                    if pending_typography is None and line.get("dominant_typography"):
                        pending_typography = line["dominant_typography"]

    _flush_pending()
    return comments


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_review_letter(
    doc: fitz.Document,
    *,
    api_key: str,
    model: str,
    call_log_rows: list[dict[str, object]],
) -> ReviewLetterExtraction:
    """Extract structured review-letter data from a plan-check letter PDF.

    Args:
        doc: PyMuPDF Document object for the plan-check letter.
        api_key: Anthropic API key. If empty or placeholder, LLM track is skipped.
        model: Anthropic model name to use (temperature always 0).
        call_log_rows: List to append LLM call log dicts to. Caller persists these.

    Returns:
        ReviewLetterExtraction with all extracted comments and provenance.
    """
    page_count = len(doc)

    # --- Phase 1: PyMuPDF text extraction for all pages ---
    pages_data: list[tuple[int, dict[str, Any]]] = []
    for i in range(page_count):
        page = doc[i]
        page_number = i + 1
        page_data = _extract_page_data(page)
        pages_data.append((page_number, page_data))

    # --- Build bbox lookup index (all pages) ---
    full_bbox_index: dict[str, tuple[int, list[float]]] = {}
    for page_number, page_data in pages_data:
        page_idx = _build_bbox_index(page_data, page_number)
        full_bbox_index.update(page_idx)

    # --- Extract metadata from page 1 text ---
    metadata: dict[str, str | None] = {}
    if pages_data:
        metadata = _extract_metadata_from_page1(pages_data[0][1])

    # --- Phase 2: LLM structured extraction ---
    # Budget: up to 3 batches of 5 pages; whole doc in one call if <= 15 pages
    llm_comments: list[ReviewLetterComment] = []
    llm_metadata: dict[str, Any] = {}
    use_llm = bool(api_key and not api_key.startswith("sk-ant-xxx"))

    if use_llm:
        MAX_BATCH_SIZE = 5
        MAX_BATCHES = 3
        max_pages = MAX_BATCH_SIZE * MAX_BATCHES  # 15

        pages_to_process = pages_data[:max_pages]

        if len(pages_to_process) <= MAX_BATCH_SIZE:
            # Single call
            page_texts = [
                (pn, _build_page_text(pd)) for pn, pd in pages_to_process
            ]
            llm_result = _call_llm_for_page_batch(
                page_texts,
                api_key=api_key,
                model=model,
                call_log_rows=call_log_rows,
            )
            if llm_result:
                llm_metadata = llm_result
                llm_comments = _build_comments_from_llm(llm_result, full_bbox_index)
        else:
            # Batched calls
            batch_comments_all: list[ReviewLetterComment] = []
            for batch_idx in range(MAX_BATCHES):
                start = batch_idx * MAX_BATCH_SIZE
                end = start + MAX_BATCH_SIZE
                batch = pages_to_process[start:end]
                if not batch:
                    break
                page_texts = [
                    (pn, _build_page_text(pd)) for pn, pd in batch
                ]
                llm_result = _call_llm_for_page_batch(
                    page_texts,
                    api_key=api_key,
                    model=model,
                    call_log_rows=call_log_rows,
                )
                if llm_result:
                    if not llm_metadata:
                        llm_metadata = llm_result
                    batch_comments = _build_comments_from_llm(llm_result, full_bbox_index)
                    batch_comments_all.extend(batch_comments)
            llm_comments = batch_comments_all

    # --- Fallback: use heuristic text extraction if LLM unavailable or returned nothing ---
    final_comments: list[ReviewLetterComment]
    if llm_comments:
        final_comments = llm_comments
    else:
        final_comments = _build_comments_from_text(pages_data)

    # --- Merge metadata: prefer LLM output, fall back to text heuristics ---
    def _pick(llm_key: str, heuristic_key: str) -> str | None:
        llm_val = llm_metadata.get(llm_key)
        if isinstance(llm_val, str) and llm_val.strip():
            return llm_val.strip()
        return metadata.get(heuristic_key)

    project_name = _pick("project_name", "project_name")
    project_address = _pick("project_address", "project_address")
    permit_number = _pick("permit_number", "permit_number")
    reviewer_name = _pick("reviewer_name", "reviewer_name")
    review_date = _pick("review_date", "review_date")

    comment_count = len(final_comments)
    overall_confidence = 0.9 if comment_count > 0 else 0.3

    return ReviewLetterExtraction(
        project_name=project_name,
        project_address=project_address,
        permit_number=permit_number,
        reviewer_name=reviewer_name,
        review_date=review_date,
        total_comment_count=comment_count,
        comments=final_comments,
        confidence=overall_confidence,
    )
