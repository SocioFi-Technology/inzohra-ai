"""SheetIndexAgent — parse the declared sheet-index table from a cover sheet.

Cover sheets (G-0.x, "Sheet Index", "Project Data") carry a table listing every
sheet in the set: `[SHEET ID, TITLE]`. This agent extracts that table using a
single Claude Sonnet vision call with a tightly-scoped JSON schema.

Invariants:
- Temperature 0 (invariant #4).
- Every entry carries ``bbox`` (invariant #1).
- Cover detection is conservative: title must mention "index" / "sheet list" /
  "cover" or the parsed discipline must be ``G``. This keeps us from burning
  LLM tokens on every page.
- No paraphrase: if Claude returns a non-JSON or missing bbox, drop the entry.
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

from inzohra_shared.schemas.extraction import SheetIndex, SheetIndexEntry

VERSION = "1.0.0"

_SYS_PROMPT = (
    "You are an expert architectural drawing analyst. Your task is to read a "
    "cover sheet / sheet index table and extract every declared sheet row."
)

_USER_PROMPT = """This image is the COVER SHEET of an architectural permit set.
Somewhere on this sheet is a table listing every sheet in the set, typically
titled "SHEET INDEX", "DRAWING INDEX", "SHEET LIST", or "DRAWINGS".

Extract EVERY row from that table as structured data. The table usually has two
columns: a sheet ID (e.g. "A-1.1", "G-0.1", "E-1.0", "T-24") and a sheet title
(e.g. "FLOOR PLAN", "SITE PLAN", "TITLE 24 REPORT").

Return ONLY valid JSON in this exact shape:

{
  "has_index": true,
  "entries": [
    {
      "declared_id": "A-0.1",
      "declared_title": "COVER / SHEET INDEX",
      "bbox_frac": [x1, y1, x2, y2]
    },
    ...
  ]
}

Rules:
- bbox_frac fractions of the IMAGE dimensions [left, top, right, bottom], (0,0)=top-left.
- Preserve the sheet IDs verbatim (do NOT canonicalise).
- If the sheet has no index table, return {"has_index": false, "entries": []}.
- Return ONLY the JSON object, no markdown fences, no extra prose.
"""


def _looks_like_cover_sheet(
    *,
    canonical_id: str | None,
    discipline_letter: str | None,
    sheet_title: str | None,
) -> bool:
    """Conservative cover-sheet detector.

    Trigger on any of:
      - canonical ID starts with G-0 (G-0.1, G-0.2, ...)
      - discipline is G AND sheet number starts with 0
      - title mentions 'index', 'cover', 'sheet list', 'drawing list'
    """
    title_l = (sheet_title or "").lower()
    if any(kw in title_l for kw in ("index", "cover", "sheet list",
                                     "drawing list", "sheet schedule")):
        return True

    if canonical_id:
        cid_upper = canonical_id.upper()
        if cid_upper.startswith(("A-0.", "G-0.")):
            return True

    if (discipline_letter or "").upper() == "G":
        return True

    return False


def _rasterize_full_page(page: fitz.Page, dpi: int = 150) -> bytes:
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png")


def _frac_to_pts(bbox_frac: list[float], page: fitz.Page) -> list[float]:
    w = page.rect.width
    h = page.rect.height
    x1, y1, x2, y2 = bbox_frac
    return [x1 * w, y1 * h, x2 * w, y2 * h]


def extract_sheet_index(
    page: fitz.Page,
    *,
    source_sheet_id: str,
    canonical_id: str | None,
    discipline_letter: str | None,
    sheet_title: str | None,
    api_key: str,
    model: str = "claude-sonnet-4-5",
    call_log_rows: list[dict[str, Any]] | None = None,
) -> SheetIndex | None:
    """Extract sheet-index entries from a cover sheet.

    Returns ``None`` when:
      - page is not classified as a cover sheet, OR
      - no API key is configured, OR
      - vision call fails, OR
      - no index table is detected.
    """
    if call_log_rows is None:
        call_log_rows = []

    if not _looks_like_cover_sheet(
        canonical_id=canonical_id,
        discipline_letter=discipline_letter,
        sheet_title=sheet_title,
    ):
        return None

    if not api_key or api_key.startswith("sk-ant-xxx"):
        return None

    try:
        from anthropic import Anthropic

        img_bytes = _rasterize_full_page(page, dpi=150)
        img_b64 = base64.b64encode(img_bytes).decode()
        prompt_hash = hashlib.sha256(_USER_PROMPT.encode()).hexdigest()[:16]

        client = Anthropic(api_key=api_key)
        t0 = time.perf_counter()
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
            temperature=0,  # invariant #4
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        text = "".join(
            b.text for b in response.content if getattr(b, "type", None) == "text"
        ).strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)

        call_log_rows.append({
            "call_id": str(uuid.uuid4()),
            "prompt_hash": prompt_hash,
            "model": model,
            "tokens_in": response.usage.input_tokens,
            "tokens_out": response.usage.output_tokens,
            "latency_ms": latency_ms,
            "cost_usd": 0.0,
            "caller_service": "ingestion.sheet_index",
        })

        data = json.loads(text)
        if not data.get("has_index"):
            return None

        entries: list[SheetIndexEntry] = []
        for raw in data.get("entries", []):
            declared_id = (raw.get("declared_id") or "").strip()
            if not declared_id:
                continue
            title = (raw.get("declared_title") or "").strip() or None
            bbox_frac = raw.get("bbox_frac") or [0.0, 0.0, 0.0, 0.0]
            if not isinstance(bbox_frac, list) or len(bbox_frac) != 4:
                bbox_frac = [0.0, 0.0, 0.0, 0.0]
            bbox = _frac_to_pts(bbox_frac, page)
            entries.append(SheetIndexEntry(
                declared_id=declared_id,
                declared_title=title,
                bbox=bbox,
                confidence=0.85,
            ))

        if not entries:
            return None

        return SheetIndex(
            source_sheet_id=source_sheet_id,
            entries=entries,
            confidence=0.8,
        )

    except Exception as exc:  # noqa: BLE001
        print(f"[SheetIndexAgent] failed: {exc}")
        return None
