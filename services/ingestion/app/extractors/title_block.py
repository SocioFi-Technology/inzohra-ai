"""TitleBlockAgent — dual-track (text + vision) title-block extractor.

Invariants upheld:
- Every emitted field carries bbox, confidence, source_track  (invariant #1).
- Temperature is always 0 for the vision LLM call             (invariant #4).
- No code text is paraphrased; this agent touches only the drawing (invariant #3).
- version = "1.0.0"; bump on any schema or prompt change      (house-rule).
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
import uuid
from typing import Any

import fitz  # PyMuPDF

from inzohra_shared.schemas.extraction import BBoxField, TitleBlockExtraction

# ---------------------------------------------------------------------------
# Agent version — bump whenever the prompt or output schema changes.
# ---------------------------------------------------------------------------
VERSION = "1.2.0"

# ---------------------------------------------------------------------------
# Vision prompt — sent as the user text alongside the title-block crop image.
# ---------------------------------------------------------------------------
_VISION_SYSTEM = (
    "You are an expert architectural drawing analyst specialising in California "
    "residential permit sets. Your task is to extract structured data from the "
    "title block region of an architectural sheet."
)

_VISION_USER_PROMPT = """Extract the following fields from this architectural drawing title block.
Return ONLY valid JSON with this exact structure (null for missing fields):

{
  "project_name": {"value": "...", "bbox_frac": [x1, y1, x2, y2]},
  "project_address": {"value": "...", "bbox_frac": [x1, y1, x2, y2]},
  "apn": {"value": "...", "bbox_frac": [x1, y1, x2, y2]},
  "permit_number": {"value": "...", "bbox_frac": [x1, y1, x2, y2]},
  "sheet_identifier_raw": {"value": "...", "bbox_frac": [x1, y1, x2, y2]},
  "sheet_title": {"value": "...", "bbox_frac": [x1, y1, x2, y2]},
  "designer_of_record": {"value": "...", "bbox_frac": [x1, y1, x2, y2]},
  "stamp_present": true,
  "date_issued": {"value": "...", "bbox_frac": [x1, y1, x2, y2]},
  "scale_declared": {"value": "...", "bbox_frac": [x1, y1, x2, y2]}
}

bbox_frac coordinates are fractions of the IMAGE dimensions: [left, top, right, bottom]
where (0,0) is top-left and (1,1) is bottom-right.
Return only the JSON object with no additional text."""

# ---------------------------------------------------------------------------
# Label patterns used in the text track
# ---------------------------------------------------------------------------
_LABEL_PATTERNS: dict[str, list[str]] = {
    "project_name": [
        r"project\s*(?:name)?[:\s]+(.+)",
        r"project\s*title[:\s]+(.+)",
    ],
    "project_address": [
        r"(?:project\s*)?address[:\s]+([^\n]+)",
        r"site\s*address[:\s]+([^\n]+)",
        # Street-number pattern: require word-boundary after street type to avoid
        # false positives like "14 gage staples" matching "st[aples]".
        r"(\d+\s+\w[\w\s]{1,30}?\b(?:ln|lane|street|avenue|blvd|boulevard|road|drive|way|court|place)\b[^\n]{0,40})",
    ],
    "apn": [
        r"apn[:\s#]+([0-9\-]+)",
        r"assessor[\'s]*\s*parcel\s*(?:number)?[:\s]+([0-9\-]+)",
        r"parcel\s*(?:no|number|#)[:\s]+([0-9\-]+)",
    ],
    "permit_number": [
        r"permit\s*(?:no|number|#)?[:\s]+([A-Z0-9\-]+)",
        r"(?:bldg|building)\s*permit[:\s]+([A-Z0-9\-]+)",
        r"(B\d{2}-\d{4})",  # e.g. B25-2734
    ],
    "sheet_identifier_raw": [
        r"\b([A-Z]-\d+\.\d+)\b",        # e.g. A-1.1
        r"\b([A-Z]\d+\.\d+)\b",         # e.g. A1.1
        r"\bsheet\s*(?:no|number|#)?[:\s]+([A-Z0-9\.\-]+)",
    ],
    "sheet_title": [
        r"(?:sheet\s*title|drawing\s*title)[:\s]+(.+)",
    ],
    "designer_of_record": [
        r"(?:architect|designer|drawn\s*by|prepared\s*by)[:\s]+(.+)",
        r"(?:licensed\s*architect|architect\s*of\s*record)[:\s]+(.+)",
    ],
    "date_issued": [
        r"(?:date|issued|issue\s*date)[:\s]+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
        r"(?:date|issued)[:\s]+(\w+\s+\d{1,2},?\s+\d{4})",
    ],
    "scale_declared": [
        r"scale[:\s]+(.+?)(?:\s{2,}|\n|$)",
        r'(1[\/\"]?\s*[=:]\s*[\d\'"]+(?:\s*[-\'\"]\s*0[\'\""]?)?)',
    ],
}

# ---------------------------------------------------------------------------
# Text-track helpers
# ---------------------------------------------------------------------------

def _get_title_block_clip(page: fitz.Page) -> fitz.Rect:
    """Return the clip rect for the title-block region.

    Portrait sheets: bottom 35% (y > h*0.65).
    Landscape sheets: right 40% (x > w*0.60) — the title block is a vertical
    strip on the right side of standard 36x24 plan sheets.
    """
    h = page.rect.height
    w = page.rect.width
    if w > h:
        # Landscape: title block is a vertical right-side strip
        return fitz.Rect(w * 0.60, 0, w, h)
    else:
        # Portrait: title block is at the bottom
        return fitz.Rect(0, h * 0.65, w, h)


def _get_title_block_spans(page: fitz.Page) -> list[dict[str, Any]]:
    """Return text spans in the title-block region.

    Adapts the search region based on page orientation (landscape vs portrait).
    """
    clip = _get_title_block_clip(page)
    raw = page.get_text("dict", sort=True, clip=clip)  # type: ignore[call-arg]
    spans: list[dict[str, Any]] = []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span["text"].strip()
                if text and len(text) >= 2:
                    spans.append({"text": text, "bbox": list(span["bbox"])})
    return spans


def _make_empty_field() -> BBoxField:
    return BBoxField(value=None, bbox=[0.0, 0.0, 0.0, 0.0], confidence=0.0, source_track="text")


def _extract_text_fields(page: fitz.Page) -> dict[str, BBoxField]:
    """Run the native-text (PyMuPDF) extraction track."""
    spans = _get_title_block_spans(page)
    full_text = "\n".join(s["text"] for s in spans)
    full_text_lower = full_text.lower()

    # Build a simple map: text → first matching span (for bbox retrieval)
    def _find_span_bbox(value: str) -> list[float]:
        for s in spans:
            if value.lower() in s["text"].lower():
                return s["bbox"]
        return [0.0, 0.0, 0.0, 0.0]

    results: dict[str, BBoxField] = {}

    for field, patterns in _LABEL_PATTERNS.items():
        matched_value: str | None = None
        matched_bbox: list[float] = [0.0, 0.0, 0.0, 0.0]

        for pattern in patterns:
            m = re.search(pattern, full_text_lower, re.IGNORECASE | re.MULTILINE)
            if m:
                matched_value = m.group(1).strip()
                matched_bbox = _find_span_bbox(matched_value)
                # Restore original case from spans
                for s in spans:
                    if matched_value.lower() in s["text"].lower():
                        start = s["text"].lower().index(matched_value.lower())
                        matched_value = s["text"][start : start + len(matched_value)].strip()
                        break
                break

        results[field] = BBoxField(
            value=matched_value,
            bbox=matched_bbox,
            confidence=0.70 if matched_value else 0.0,
            source_track="text",
        )

    return results


def _detect_stamp(page: fitz.Page) -> bool:
    """Heuristic: check for circular image objects or keyword 'licensed' in text."""
    # Look for small circular images (stamps are typically ~1" diameter)
    for img in page.get_images(full=True):
        xref = img[0]
        try:
            pix = fitz.Pixmap(page.parent, xref)  # type: ignore[call-arg]
            if abs(pix.width - pix.height) < 20 and 50 < pix.width < 300:
                return True
        except Exception:
            pass

    text = page.get_text("text")
    return bool(re.search(r"licensed\s+architect|state\s+of\s+california", text, re.IGNORECASE))


# ---------------------------------------------------------------------------
# Vision-track helpers
# ---------------------------------------------------------------------------

def _rasterize_title_block_crop(page: fitz.Page, dpi: int = 150) -> bytes:
    """Rasterize the title-block region for vision extraction.

    Uses the same orientation-adaptive clip as the text track.
    """
    clip = _get_title_block_clip(page)
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
    return pix.tobytes("png")


def _extract_vision_fields(
    page: fitz.Page,
    api_key: str,
    model: str,
    call_log_rows: list[dict[str, Any]],
) -> dict[str, BBoxField] | None:
    """Call Claude Sonnet vision on the title-block crop.

    Returns None if the API call fails or the key is a placeholder.
    Appends an llm_call_log row dict to ``call_log_rows`` on success.
    """
    if not api_key or api_key.startswith("sk-ant-xxx"):
        return None

    try:
        from anthropic import Anthropic

        img_bytes = _rasterize_title_block_crop(page)
        img_b64 = base64.b64encode(img_bytes).decode()

        ph = hashlib.sha256(_VISION_USER_PROMPT.encode()).hexdigest()[:16]
        client = Anthropic(api_key=api_key)
        t0 = time.perf_counter()

        response = client.messages.create(
            model=model,
            system=_VISION_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": img_b64,
                            },
                        },
                        {"type": "text", "text": _VISION_USER_PROMPT},
                    ],
                }
            ],
            max_tokens=1024,
            temperature=0,  # invariant #4
        )

        latency_ms = int((time.perf_counter() - t0) * 1000)
        text = "".join(
            b.text for b in response.content if getattr(b, "type", None) == "text"
        )

        call_log_rows.append(
            {
                "call_id": str(uuid.uuid4()),
                "prompt_hash": ph,
                "model": model,
                "tokens_in": response.usage.input_tokens,
                "tokens_out": response.usage.output_tokens,
                "latency_ms": latency_ms,
                "cost_usd": 0.0,
                "caller_service": "ingestion.title_block",
            }
        )

        # Strip markdown fences if present
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        data = json.loads(text)
        return _parse_vision_json(data, page)

    except Exception as exc:  # noqa: BLE001
        print(f"[TitleBlockAgent] vision track failed: {exc}")
        return None


def _frac_bbox_to_pts(bbox_frac: list[float], page: fitz.Page, crop_y0_frac: float = 0.65) -> list[float]:
    """Convert fractional bbox (of the cropped image) back to page PDF points.

    The crop region is orientation-adaptive:
    - Landscape: right 40% strip (x0=w*0.60, y0=0, x1=w, y1=h)
    - Portrait: bottom 35% strip (x0=0, y0=h*0.65, x1=w, y1=h)
    ``crop_y0_frac`` is ignored (kept for backward compatibility).
    """
    clip = _get_title_block_clip(page)
    clip_w = clip.x1 - clip.x0
    clip_h = clip.y1 - clip.y0

    x1 = clip.x0 + bbox_frac[0] * clip_w
    y1 = clip.y0 + bbox_frac[1] * clip_h
    x2 = clip.x0 + bbox_frac[2] * clip_w
    y2 = clip.y0 + bbox_frac[3] * clip_h
    return [x1, y1, x2, y2]


def _parse_vision_json(
    data: dict[str, Any], page: fitz.Page
) -> dict[str, BBoxField]:
    results: dict[str, BBoxField] = {}
    for field in (
        "project_name", "project_address", "apn", "permit_number",
        "sheet_identifier_raw", "sheet_title", "designer_of_record",
        "date_issued", "scale_declared",
    ):
        raw = data.get(field)
        if raw and isinstance(raw, dict) and raw.get("value"):
            bbox_frac = raw.get("bbox_frac", [0.0, 0.0, 0.0, 0.0])
            if not isinstance(bbox_frac, list) or len(bbox_frac) != 4:
                bbox_frac = [0.0, 0.0, 0.0, 0.0]
            pts = _frac_bbox_to_pts(bbox_frac, page)
            results[field] = BBoxField(
                value=str(raw["value"]).strip(),
                bbox=pts,
                confidence=0.85,
                source_track="vision",
            )
        else:
            results[field] = _make_empty_field()
            results[field].source_track = "vision"
    return results


# ---------------------------------------------------------------------------
# Merge tracks
# ---------------------------------------------------------------------------

_AGREE_THRESHOLD = 0.7  # Jaccard-like character overlap


def _jaccard(a: str, b: str) -> float:
    a_set = set(a.lower().split())
    b_set = set(b.lower().split())
    if not a_set and not b_set:
        return 1.0
    if not a_set or not b_set:
        return 0.0
    return len(a_set & b_set) / len(a_set | b_set)


def _merge_field(
    field: str,
    text_val: BBoxField,
    vision_val: BBoxField,
) -> BBoxField:
    tv = text_val.value
    vv = vision_val.value

    if tv and vv:
        score = _jaccard(tv, vv)
        if score >= _AGREE_THRESHOLD:
            # Agreement — use text bbox (more precise) + high confidence
            return BBoxField(
                value=tv,
                bbox=text_val.bbox if text_val.bbox != [0.0, 0.0, 0.0, 0.0] else vision_val.bbox,
                confidence=0.95,
                source_track="merged",
                text_raw=tv,
                vision_raw=vv,
            )
        else:
            # Disagreement — flag at low confidence, prefer vision value
            return BBoxField(
                value=vv,
                bbox=vision_val.bbox,
                confidence=0.40,
                source_track="merged",
                text_raw=tv,
                vision_raw=vv,
            )
    elif tv:
        return BBoxField(value=tv, bbox=text_val.bbox, confidence=0.70, source_track="text")
    elif vv:
        return BBoxField(value=vv, bbox=vision_val.bbox, confidence=0.70, source_track="vision")
    else:
        return _make_empty_field()


# ---------------------------------------------------------------------------
# Address mismatch detection
# ---------------------------------------------------------------------------

# Street type abbreviation groups — words in the same group are considered equal.
_STREET_ABBREV_GROUPS: list[set[str]] = [
    {"ln", "lane"},
    {"st", "street"},
    {"ave", "av", "avenue"},
    {"blvd", "boulevard"},
    {"rd", "road"},
    {"dr", "drive"},
    {"ct", "court"},
    {"pl", "place"},
    {"hwy", "highway"},
]

_ABBREV_CANONICAL: dict[str, str] = {}
for _group in _STREET_ABBREV_GROUPS:
    _canon = min(_group, key=len)  # shortest = canonical token
    for _tok in _group:
        _ABBREV_CANONICAL[_tok] = _canon


def _normalize_address_words(addr: str) -> set[str]:
    """Lower-case, strip punctuation, normalize street abbreviations."""
    words = re.findall(r"[a-zA-Z0-9]+", addr.lower())
    return {_ABBREV_CANONICAL.get(w, w) for w in words}


def _address_differs(extracted: str, canonical: str) -> bool:
    """Return True when extracted address looks like a DIFFERENT property.

    Uses shared house-number detection first (robust to street-name abbrevs),
    then falls back to normalised Jaccard for edge cases.

    False positives (e.g. "2008 DENNIS LANE, ST ROSA" vs "2008 Dennis Ln,
    Santa Rosa, CA") are suppressed because both share house number "2008"
    and street name token "dennis".
    """
    ext_numbers = set(re.findall(r"\b\d{3,5}\b", extracted))
    can_numbers = set(re.findall(r"\b\d{3,5}\b", canonical))

    if ext_numbers and can_numbers:
        shared_nums = ext_numbers & can_numbers
        if shared_nums:
            # Same house number — check at least one street-name word matches
            ext_words = _normalize_address_words(extracted) - ext_numbers
            can_words = _normalize_address_words(canonical) - can_numbers
            return not bool(ext_words & can_words)
        else:
            # Different house numbers → definitely a different property
            return True

    # Fallback: normalised Jaccard (< 0.35 = mismatch)
    ext_norm = _normalize_address_words(extracted)
    can_norm = _normalize_address_words(canonical)
    if not ext_norm or not can_norm:
        return False
    score = len(ext_norm & can_norm) / len(ext_norm | can_norm)
    return score < 0.35


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_title_block(
    page: fitz.Page,
    *,
    api_key: str = "",
    model: str = "claude-sonnet-4-5",
    canonical_address: str | None = None,
    call_log_rows: list[dict[str, Any]] | None = None,
) -> TitleBlockExtraction:
    """Run dual-track title-block extraction and return a ``TitleBlockExtraction``.

    Args:
        page: PyMuPDF page object (0-indexed internally, caller decides page number).
        api_key: Anthropic API key. If empty or placeholder, vision track is skipped.
        model: Model name for the vision call.
        canonical_address: The project's canonical address. If provided, the
            ``address_mismatch`` flag is set when the extracted address differs.
        call_log_rows: List to append LLM call log dicts to. Caller persists these.

    Returns:
        ``TitleBlockExtraction`` with provenance on every field.
    """
    if call_log_rows is None:
        call_log_rows = []

    # --- text track ---
    text_fields = _extract_text_fields(page)
    stamp = _detect_stamp(page)

    # --- vision track ---
    vision_fields = _extract_vision_fields(page, api_key, model, call_log_rows)

    # --- merge ---
    merged: dict[str, BBoxField] = {}
    for field in (
        "project_name", "project_address", "apn", "permit_number",
        "sheet_identifier_raw", "sheet_title", "designer_of_record",
        "date_issued", "scale_declared",
    ):
        tf = text_fields.get(field, _make_empty_field())
        if vision_fields:
            vf = vision_fields.get(field, _make_empty_field())
            merged[field] = _merge_field(field, tf, vf)
        else:
            # Vision unavailable — use text-only result
            merged[field] = tf

    # --- address mismatch flag ---
    address_mismatch = False
    if canonical_address and merged["project_address"].value:
        address_mismatch = _address_differs(merged["project_address"].value, canonical_address)

    return TitleBlockExtraction(
        **merged,
        stamp_present=stamp,
        address_mismatch=address_mismatch,
    )
