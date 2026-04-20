"""FloorPlanGeometryAgent — vision extraction of doors, windows, rooms from floor plans.

Uses Claude Sonnet with structured JSON output (temperature=0).
Renders each PDF page at 150 DPI for vector PDFs, 200 DPI for raster.

Layer: 3 — Extraction (calls LLM, writes structured JSON, never writes to storage).
Input:  a single fitz.Page already loaded by the caller.
Output: FloorPlanExtraction with entity bboxes in PDF points (top-left origin).
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
import uuid
from typing import Any

import anthropic
import fitz  # PyMuPDF

from inzohra_shared.schemas.measurement import FloorPlanEntity, FloorPlanExtraction

VERSION = "1.0.0"
logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-5"
_RENDER_DPI_VECTOR = 96     # 96 DPI keeps vector pages well under 5 MB limit
_RENDER_DPI_RASTER = 120    # Raster needs a bit more, still under limit
_MAX_IMAGE_BYTES = 4 * 1024 * 1024  # 4 MB headroom under Anthropic's 5 MB limit

_EXTRACTION_PROMPT = """You are analyzing an architectural floor plan drawing. Extract ALL doors, windows, and rooms visible on this sheet.

For EACH entity, provide:
- entity_type: "door", "window", "room", "stair", or "exit"
- tag: the alphanumeric tag/mark shown (e.g., "3", "W-4", "A") — null if none visible
- room_label: the text label shown in the room (e.g., "BEDROOM 2", "MASTER BATH") — null for non-rooms
- room_use: normalized use — one of: "bedroom", "bathroom", "kitchen", "living", "corridor", "garage", "exit", "dining", "laundry", "closet", "mechanical", "office", "other"
- bbox: [x1, y1, x2, y2] bounding box in pixels from top-left of this image
- confidence: 0.0-1.0 (your confidence in the entity detection and attributes)
- geometry_notes: brief note like "swing left", "sliding", "double", "exterior wall", "interior"
- schedule_ref: if you see a schedule reference mark near this entity (e.g., a circled number), record it

IMPORTANT:
- Capture ALL bedrooms — label them clearly as entity_type="room", room_use="bedroom"
- Capture ALL windows in bedrooms — they may be egress windows
- For doors, the tag is often a small number in a circle or diamond shape
- For windows, the tag is often a letter or letter+number
- bbox values are in PIXELS, origin at TOP-LEFT of the image you are analyzing
- Return as JSON array of entities

Return ONLY valid JSON. No markdown, no explanation.
Example:
[
  {"entity_type": "room", "tag": null, "room_label": "BEDROOM 1", "room_use": "bedroom", "bbox": [100, 200, 400, 500], "confidence": 0.92, "geometry_notes": null, "schedule_ref": null},
  {"entity_type": "door", "tag": "3", "room_label": null, "room_use": null, "bbox": [380, 250, 420, 290], "confidence": 0.88, "geometry_notes": "swing right", "schedule_ref": "3"},
  {"entity_type": "window", "tag": "W-2", "room_label": null, "room_use": null, "bbox": [150, 200, 220, 215], "confidence": 0.85, "geometry_notes": "exterior", "schedule_ref": "W-2"}
]"""

# Precompute prompt hash once at module load — the prompt is a constant.
_PROMPT_HASH: str = hashlib.sha256(_EXTRACTION_PROMPT.encode()).hexdigest()[:16]

# Rough cost rates (USD per token) for claude-sonnet-4-5:
#   input  ~$3.00 / 1M tokens  → 3e-6 per token
#   output ~$15.00 / 1M tokens → 15e-6 per token
_COST_PER_INPUT_TOKEN: float = 3e-6
_COST_PER_OUTPUT_TOKEN: float = 15e-6


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _render_page_to_png(page: fitz.Page, dpi: int) -> tuple[bytes, float]:
    """Render page to JPEG bytes. Returns (jpeg_bytes, scale_factor).

    scale_factor = dpi / 72, because PDF coordinates are in 72 pts/inch.
    Uses JPEG at quality=85 to stay well under Anthropic's 5 MB image limit.
    If the result is still too large, halves the DPI and retries once.
    """
    scale = dpi / 72
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    img_bytes = pix.tobytes("jpeg", jpg_quality=85)
    if len(img_bytes) > _MAX_IMAGE_BYTES:
        # Halve DPI and retry
        scale = (dpi // 2) / 72
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img_bytes = pix.tobytes("jpeg", jpg_quality=80)
    return img_bytes, scale


def _bbox_from_pixels_to_pts(
    bbox_px: list[float], scale_factor: float
) -> list[float]:
    """Convert pixel bbox [x1,y1,x2,y2] back to PDF points."""
    return [v / scale_factor for v in bbox_px]


def _parse_entities(
    raw_json: str,
    page_number: int,
    scale_factor: float,
) -> list[FloorPlanEntity]:
    """Parse the model's JSON response into validated FloorPlanEntity objects.

    Bboxes are converted from pixels → PDF points.  Any item that fails
    Pydantic validation is skipped (logged at WARNING level) so a single
    malformed entity never kills the whole extraction.
    """
    # Strip markdown code fences that Claude sometimes wraps responses in
    cleaned = raw_json.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned[3:]
        # Remove closing fence
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].rstrip()

    try:
        items: list[dict[str, Any]] = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning(
            "FloorPlanGeometryAgent: JSON parse error (page=%d): %s",
            page_number,
            exc,
        )
        return []

    if not isinstance(items, list):
        logger.warning(
            "FloorPlanGeometryAgent: expected JSON array, got %s (page=%d)",
            type(items).__name__,
            page_number,
        )
        return []

    entities: list[FloorPlanEntity] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            logger.warning(
                "FloorPlanGeometryAgent: item %d is not a dict, skipping", idx
            )
            continue

        # Convert bbox from pixels → PDF points before validation.
        raw_bbox: Any = item.get("bbox")
        if isinstance(raw_bbox, list) and len(raw_bbox) == 4:
            item["bbox"] = _bbox_from_pixels_to_pts(
                [float(v) for v in raw_bbox], scale_factor
            )

        # Inject page number — the vision model operates on a single rendered
        # image and has no concept of PDF page numbers.
        item["page"] = page_number

        try:
            entities.append(FloorPlanEntity(**item))
        except Exception as exc:  # pydantic.ValidationError or any other
            logger.warning(
                "FloorPlanGeometryAgent: entity %d validation failed (page=%d): %s",
                idx,
                page_number,
                exc,
            )

    return entities


def _compute_extraction_confidence(entities: list[FloorPlanEntity]) -> float:
    """Average confidence across entities; fall back to 0.20 when list is empty."""
    if not entities:
        return 0.20
    return sum(e.confidence for e in entities) / len(entities)


def _count_by_type(entities: list[FloorPlanEntity], entity_type: str) -> int:
    return sum(1 for e in entities if e.entity_type == entity_type)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_floor_plan(
    page: fitz.Page,
    *,
    sheet_id: str,
    api_key: str,
    model: str = _DEFAULT_MODEL,
    pdf_quality: str = "vector",
    call_log_rows: list[dict[str, object]],
) -> FloorPlanExtraction:
    """Extract all floor plan entities from a single fitz.Page.

    Returns a FloorPlanExtraction with entity bboxes in PDF points
    (top-left origin, matching PyMuPDF's coordinate system).

    Parameters
    ----------
    page:
        A loaded PyMuPDF page object.  Must already be the correct page;
        this function does not open or seek a document.
    sheet_id:
        The project-level sheet identifier (UUID or canonical ID).
    api_key:
        Anthropic API key.  Never read from env here — the caller supplies it
        so secrets handling stays in one place.
    model:
        Claude model ID.  Defaults to claude-sonnet-4-5 (temperature=0).
    pdf_quality:
        One of "vector", "hybrid", "raster", "low_quality_scan".  Controls
        render DPI: vector → 150 DPI, anything else → 200 DPI.
    call_log_rows:
        Caller-supplied mutable list.  This function appends one dict per LLM
        call so the caller can bulk-insert to llm_call_log.

    Returns
    -------
    FloorPlanExtraction
        On JSON parse failure: empty entity list, extraction_confidence=0.20.

    Raises
    ------
    anthropic.APIError
        Propagated unmodified so the caller can apply retry / circuit-breaker
        logic at the pipeline level.
    """
    page_number: int = page.number  # 0-based PyMuPDF page index

    # 1. Render the page to a PNG at the appropriate DPI.
    dpi = _RENDER_DPI_VECTOR if pdf_quality == "vector" else _RENDER_DPI_RASTER
    img_bytes, scale_factor = _render_page_to_png(page, dpi)
    b64_image = base64.standard_b64encode(img_bytes).decode("ascii")

    logger.debug(
        "FloorPlanGeometryAgent: rendering page %d at %d DPI "
        "(scale_factor=%.4f, image_bytes=%d)",
        page_number,
        dpi,
        scale_factor,
        len(img_bytes),
    )

    # 2. Call Claude with the image and extraction prompt.
    client = anthropic.Anthropic(api_key=api_key)
    call_id = str(uuid.uuid4())
    t0 = time.perf_counter()

    response = client.messages.create(
        model=model,
        max_tokens=8192,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64_image,
                        },
                    },
                    {
                        "type": "text",
                        "text": _EXTRACTION_PROMPT,
                    },
                ],
            }
        ],
    )

    latency_ms = int((time.perf_counter() - t0) * 1000)

    # 3. Extract the text content from the response.
    raw_text: str = ""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            raw_text += block.text

    tokens_in: int = response.usage.input_tokens
    tokens_out: int = response.usage.output_tokens
    cost_usd: float = (
        tokens_in * _COST_PER_INPUT_TOKEN + tokens_out * _COST_PER_OUTPUT_TOKEN
    )

    # 4. Log the LLM call for the caller to persist.
    call_log_rows.append(
        {
            "call_id": call_id,
            "prompt_hash": _PROMPT_HASH,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": latency_ms,
            "cost_usd": cost_usd,
            "caller_service": "measurement",
        }
    )

    logger.info(
        "FloorPlanGeometryAgent: page=%d model=%s tokens_in=%d tokens_out=%d "
        "latency_ms=%d cost_usd=%.6f",
        page_number,
        model,
        tokens_in,
        tokens_out,
        latency_ms,
        cost_usd,
    )

    # 5. Parse JSON → FloorPlanEntity list, converting pixel bboxes to PDF pts.
    entities = _parse_entities(raw_text, page_number, scale_factor)

    if not entities:
        logger.warning(
            "FloorPlanGeometryAgent: no entities extracted from page %d "
            "(sheet_id=%s). raw_text[:200]=%r",
            page_number,
            sheet_id,
            raw_text[:200],
        )

    # 6. Assemble and return the extraction result.
    return FloorPlanExtraction(
        sheet_id=sheet_id,
        page=page_number,
        entities=entities,
        extraction_confidence=_compute_extraction_confidence(entities),
        prompt_hash=_PROMPT_HASH,
        model=model,
        total_doors=_count_by_type(entities, "door"),
        total_windows=_count_by_type(entities, "window"),
        total_rooms=_count_by_type(entities, "room"),
    )
