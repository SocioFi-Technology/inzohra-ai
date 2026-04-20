"""ScheduleAgent — extract door, window, wall, and other schedule tables.

Strategy: hybrid native-table + Claude vision fallback.

Pass 1 — PyMuPDF native table detection (``page.find_tables()``).  High
confidence (0.92) when tables are detected natively.

Pass 2 — Claude vision fallback only when:
  - No native tables were found on this page, AND
  - Page text contains schedule heading keywords.

Invariants upheld:
  - Temperature 0 (invariant #4).
  - Every row carries bbox + confidence (invariant #1).
  - LLM calls logged to call_log_rows.
  - No commit inside this module.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from typing import Any

import fitz  # PyMuPDF

from inzohra_shared.schemas.extraction import (
    DoorScheduleRow,
    ScheduleExtraction,
    ScheduleRow,
    WindowScheduleRow,
)

VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SCHEDULE_HEADER_KEYWORDS: set[str] = {
    "MARK", "TAG", "TYPE", "SIZE", "WIDTH", "HEIGHT",
    "FIRE", "RATING", "MATERIAL", "HARDWARE",
    "U-FACTOR", "SHGC", "NCO",
}

_DOOR_KEYWORDS: set[str] = {"DOOR", "HARDWARE", "FIRE"}
_WINDOW_KEYWORDS: set[str] = {"WINDOW", "U-FACTOR", "SHGC", "NCO"}
_WALL_KEYWORDS: set[str] = {"WALL TYPE", "ASSEMBLY"}

_VISION_TRIGGERS: list[str] = [
    "DOOR SCHEDULE",
    "WINDOW SCHEDULE",
    "FASTENER SCHEDULE",
    "HOLDOWN SCHEDULE",
    "WALL TYPE",
]

_SYS_PROMPT = (
    "You are analyzing a construction drawing sheet. "
    "Extract any schedule tables you find."
)

_USER_PROMPT = (
    "Return JSON: "
    '[{"schedule_type": "door_schedule", "headers": [...], '
    '"rows": [{"row_index": 0, "tag": "1", "cells": {...}}]}]. '
    "Return empty array [] if no schedules."
)


# ---------------------------------------------------------------------------
# Helpers — schedule type detection
# ---------------------------------------------------------------------------

def _classify_schedule_type(headers: list[str]) -> str:
    """Determine schedule_type from header names."""
    headers_upper = {h.upper() for h in headers}

    # Check for door keywords
    if (
        _DOOR_KEYWORDS & headers_upper
        or any("DOOR" in h or "HW" in h for h in headers_upper)
    ):
        return "door_schedule"

    # Check for window keywords
    if _WINDOW_KEYWORDS & headers_upper or any(
        "WINDOW" in h or "WIN" in h for h in headers_upper
    ):
        return "window_schedule"

    # Check for wall keywords
    if any("WALL" in h or "ASSEMBLY" in h for h in headers_upper):
        return "wall_schedule"

    return "schedule"


def _looks_like_schedule(headers: list[str]) -> bool:
    """True if at least one header matches a known schedule keyword."""
    headers_upper = {h.upper() for h in headers}
    return bool(_SCHEDULE_HEADER_KEYWORDS & headers_upper)


# ---------------------------------------------------------------------------
# Helpers — typed row construction
# ---------------------------------------------------------------------------

def _header_match(headers: list[str], *candidates: str) -> str | None:
    """Return the first header that contains any candidate substring (case-insensitive)."""
    for h in headers:
        hu = h.upper()
        for c in candidates:
            if c in hu:
                return h
    return None


def _cell_value(cells: dict[str, str | None], header: str | None) -> str | None:
    if header is None:
        return None
    return cells.get(header)


def _try_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        return None


def _try_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    v = value.strip().upper()
    if v in ("YES", "Y", "TRUE", "1", "REQUIRED", "REQ"):
        return True
    if v in ("NO", "N", "FALSE", "0", "N/A", "NA"):
        return False
    return None


def _build_door_row(
    row_index: int,
    tag: str | None,
    cells: dict[str, str | None],
    headers: list[str],
    bbox: list[float],
    confidence: float,
) -> DoorScheduleRow:
    width_h = _header_match(headers, "WIDTH", "WD", "W")
    height_h = _header_match(headers, "HEIGHT", "HT", "HGT", "H")
    type_h = _header_match(headers, "TYPE", "DOOR TYPE")
    mat_h = _header_match(headers, "MATERIAL", "MAT", "FRAME")
    fire_h = _header_match(headers, "FIRE", "RATING", "FR")
    hw_h = _header_match(headers, "HARDWARE", "HW", "HDWR")

    return DoorScheduleRow(
        row_index=row_index,
        tag=tag,
        cells=cells,
        bbox=bbox,
        confidence=confidence,
        width_raw=_cell_value(cells, width_h),
        height_raw=_cell_value(cells, height_h),
        door_type=_cell_value(cells, type_h),
        material=_cell_value(cells, mat_h),
        fire_rating=_cell_value(cells, fire_h),
        hardware_group=_cell_value(cells, hw_h),
    )


def _build_window_row(
    row_index: int,
    tag: str | None,
    cells: dict[str, str | None],
    headers: list[str],
    bbox: list[float],
    confidence: float,
) -> WindowScheduleRow:
    width_h = _header_match(headers, "WIDTH", "WD", "W")
    height_h = _header_match(headers, "HEIGHT", "HT", "HGT", "H")
    type_h = _header_match(headers, "TYPE", "WINDOW TYPE", "WIN TYPE")
    uf_h = _header_match(headers, "U-FACTOR", "U FACTOR", "U-VALUE", "U VALUE")
    shgc_h = _header_match(headers, "SHGC")
    egress_h = _header_match(headers, "EGRESS")
    nco_h = _header_match(headers, "NCO")

    return WindowScheduleRow(
        row_index=row_index,
        tag=tag,
        cells=cells,
        bbox=bbox,
        confidence=confidence,
        width_raw=_cell_value(cells, width_h),
        height_raw=_cell_value(cells, height_h),
        window_type=_cell_value(cells, type_h),
        u_factor=_try_float(_cell_value(cells, uf_h)),
        shgc=_try_float(_cell_value(cells, shgc_h)),
        egress_compliant=_try_bool(_cell_value(cells, egress_h)),
        nco_area=_try_float(_cell_value(cells, nco_h)),
    )


def _build_row(
    row_index: int,
    tag: str | None,
    cells: dict[str, str | None],
    headers: list[str],
    bbox: list[float],
    confidence: float,
    schedule_type: str,
) -> ScheduleRow:
    if schedule_type == "door_schedule":
        return _build_door_row(row_index, tag, cells, headers, bbox, confidence)
    if schedule_type == "window_schedule":
        return _build_window_row(row_index, tag, cells, headers, bbox, confidence)
    return ScheduleRow(
        row_index=row_index,
        tag=tag,
        cells=cells,
        bbox=bbox,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Pass 1 — PyMuPDF native table detection
# ---------------------------------------------------------------------------

def _extract_native_tables(
    page: fitz.Page,
    *,
    sheet_id: str,
) -> list[ScheduleExtraction]:
    """Attempt to extract schedule tables using PyMuPDF's native table finder."""
    results: list[ScheduleExtraction] = []

    try:
        tabs = page.find_tables()
    except Exception:  # noqa: BLE001
        return []

    if not tabs or not tabs.tables:
        return []

    for tab in tabs.tables:
        try:
            extracted = tab.extract()
        except Exception:  # noqa: BLE001
            continue

        if not extracted or len(extracted) < 2:
            # Need at least a header row + one data row
            continue

        # First row is the header
        raw_headers = extracted[0]
        headers = [
            str(cell).strip() if cell is not None else ""
            for cell in raw_headers
        ]

        if not _looks_like_schedule(headers):
            continue

        schedule_type = _classify_schedule_type(headers)
        tab_bbox = list(tab.bbox)  # (x0, y0, x1, y1)

        rows: list[ScheduleRow] = []
        for row_index, raw_row in enumerate(extracted[1:]):
            if not raw_row or all(c is None or str(c).strip() == "" for c in raw_row):
                continue

            cells: dict[str, str | None] = {}
            for i, cell in enumerate(raw_row):
                col_name = headers[i] if i < len(headers) else f"col_{i}"
                cells[col_name] = str(cell).strip() if cell is not None else None

            # Tag = first non-empty cell
            tag: str | None = None
            for cell_val in cells.values():
                if cell_val:
                    tag = cell_val
                    break

            # Row bbox: use table bbox as approximation (full table bbox per row)
            row_bbox = tab_bbox[:]

            row = _build_row(
                row_index=row_index,
                tag=tag,
                cells=cells,
                headers=headers,
                bbox=row_bbox,
                confidence=0.92,
                schedule_type=schedule_type,
            )
            rows.append(row)

        if not rows:
            continue

        results.append(
            ScheduleExtraction(
                schedule_type=schedule_type,
                sheet_id=sheet_id,
                headers=headers,
                rows=rows,
                extraction_method="native_table",
                confidence=0.92,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Pass 2 — Claude vision fallback
# ---------------------------------------------------------------------------

def _has_schedule_triggers(page: fitz.Page) -> bool:
    """Quick heuristic: does page text contain any schedule heading keywords?"""
    text = page.get_text().upper()
    return any(trigger in text for trigger in _VISION_TRIGGERS)


def _rasterize_page(page: fitz.Page, dpi: int = 200) -> bytes:
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png")


def _parse_vision_response(
    raw_json: str,
    *,
    sheet_id: str,
) -> list[ScheduleExtraction]:
    """Parse the JSON array returned by the vision call."""
    results: list[ScheduleExtraction] = []

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    for sch_data in data:
        if not isinstance(sch_data, dict):
            continue

        schedule_type = str(sch_data.get("schedule_type") or "schedule").strip()
        raw_headers: list[Any] = sch_data.get("headers") or []
        headers = [str(h).strip() for h in raw_headers if h is not None]

        if not headers:
            continue

        raw_rows: list[Any] = sch_data.get("rows") or []
        rows: list[ScheduleRow] = []

        for raw_row in raw_rows:
            if not isinstance(raw_row, dict):
                continue

            row_index = int(raw_row.get("row_index") or len(rows))
            tag: str | None = raw_row.get("tag")
            if tag is not None:
                tag = str(tag).strip() or None

            raw_cells = raw_row.get("cells") or {}
            if not isinstance(raw_cells, dict):
                raw_cells = {}

            cells: dict[str, str | None] = {
                str(k): (str(v).strip() if v is not None else None)
                for k, v in raw_cells.items()
            }

            row = _build_row(
                row_index=row_index,
                tag=tag,
                cells=cells,
                headers=headers,
                bbox=[0.0, 0.0, 0.0, 0.0],
                confidence=0.75,
                schedule_type=schedule_type,
            )
            rows.append(row)

        if not rows:
            continue

        results.append(
            ScheduleExtraction(
                schedule_type=schedule_type,
                sheet_id=sheet_id,
                headers=headers,
                rows=rows,
                extraction_method="vision",
                confidence=0.75,
            )
        )

    return results


def _extract_via_vision(
    page: fitz.Page,
    *,
    sheet_id: str,
    api_key: str,
    model: str,
    call_log_rows: list[dict[str, Any]],
) -> list[ScheduleExtraction]:
    """Rasterize page and send to Claude vision for schedule extraction."""
    if not api_key or api_key.startswith("sk-ant-xxx"):
        return []

    try:
        import anthropic

        img_bytes = _rasterize_page(page, dpi=200)
        img_b64 = base64.b64encode(img_bytes).decode()
        prompt_hash = hashlib.sha256(_USER_PROMPT.encode()).hexdigest()[:16]

        client = anthropic.Anthropic(api_key=api_key)
        t0 = time.time()
        response = client.messages.create(
            model=model,
            system=_SYS_PROMPT,
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
                        {"type": "text", "text": _USER_PROMPT},
                    ],
                }
            ],
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
            "caller_service": "ingestion.schedule",
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

        return _parse_vision_response(text, sheet_id=sheet_id)

    except Exception as exc:  # noqa: BLE001
        print(f"[ScheduleAgent] vision call failed: {exc}")
        return []


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_schedules(
    page: fitz.Page,
    *,
    sheet_id: str,
    api_key: str,
    model: str,
    call_log_rows: list[dict[str, Any]],
) -> list[ScheduleExtraction]:
    """Extract all schedule tables from a PDF page.

    Pass 1: PyMuPDF native table detection (fast, high confidence).
    Pass 2: Claude vision fallback (only if no native tables and triggers found).

    Args:
        page: PyMuPDF page object.
        sheet_id: The sheet_id for this page (used in ScheduleExtraction).
        api_key: Anthropic API key.
        model: Claude model identifier.
        call_log_rows: Mutable list; LLM call log dicts are appended here.

    Returns:
        List of ScheduleExtraction objects (empty if nothing found).
    """
    # Pass 1 — native table detection
    native_results = _extract_native_tables(page, sheet_id=sheet_id)
    if native_results:
        return native_results

    # Pass 2 — vision fallback (only if schedule content is suspected)
    if not _has_schedule_triggers(page):
        return []

    return _extract_via_vision(
        page,
        sheet_id=sheet_id,
        api_key=api_key,
        model=model,
        call_log_rows=call_log_rows,
    )
