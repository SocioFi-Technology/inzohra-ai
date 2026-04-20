"""Title24FormAgent — text + LLM extraction of California Title 24 energy forms.

Invariants upheld:
- Temperature is always 0 for every LLM call            (invariant #4).
- No code text is paraphrased; this agent reads only the PDF (invariant #3).
- Every call is logged with prompt_hash, model, tokens, latency, cost  (invariant #1).
- VERSION = "1.0.0"; bump on any schema or prompt change (house-rule).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from typing import Any

import fitz  # PyMuPDF

from inzohra_shared.schemas.extraction import (
    Title24Extraction,
    T24Surface,
    T24HvacSystem,
    T24Dhw,
)

# ---------------------------------------------------------------------------
# Agent version — bump whenever the prompt or output schema changes.
# ---------------------------------------------------------------------------
VERSION = "1.0.0"

# Maximum characters of document text passed to the LLM.
_MAX_TEXT_CHARS = 12_000

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are parsing a California Title 24 energy compliance form (CF1R, RMS-1, or MF1R). "
    "Extract structured data exactly as found. Return ONLY valid JSON, no markdown fences."
)

_USER_PROMPT_TEMPLATE = """\
The following text was extracted from a California Title 24 energy compliance document.
Extract all available data and return ONLY a single valid JSON object matching the schema below.
Use null for any field not present in the document. Do not invent or estimate values.

--- DOCUMENT TEXT START ---
{document_text}
--- DOCUMENT TEXT END ---

Return a JSON object with EXACTLY this structure (no extra keys, no markdown fences):
{{
  "form_type": "CF1R-PRF-01-E",
  "project_name": "...",
  "project_address": "...",
  "climate_zone": "2",
  "permit_date": "...",
  "conditioned_floor_area": 1234.0,
  "compliance_result": "PASS",
  "envelope_surfaces": [
    {{
      "surface_type": "roof",
      "assembly_id": "Roof-1",
      "area": 1200.0,
      "u_factor": 0.021,
      "r_value": 38.0,
      "assembly_description": "R-38 blown insulation",
      "meets_prescriptive": true
    }}
  ],
  "hvac_systems": [
    {{
      "system_id": "HVAC-1",
      "system_type": "Split DX AC + Gas Furnace",
      "seer": 15.0,
      "eer": null,
      "afue": 80.0,
      "hspf": null,
      "cooling_btu": 36000.0,
      "heating_btu": 60000.0
    }}
  ],
  "dhw_systems": [
    {{
      "fuel_type": "Natural Gas",
      "tank_size_gal": 40.0,
      "ef": null,
      "uef": 0.62
    }}
  ]
}}

Rules:
- form_type must be one of: "CF1R-PRF-01-E", "CF1R", "RMS-1", "MF1R", "unknown"
- compliance_result must be one of: "PASS", "FAIL", "N/A", or null
- surface_type must be one of: "roof", "wall", "floor", "window", "skylight"
- All numeric fields must be numbers (not strings), or null if absent
- envelope_surfaces, hvac_systems, dhw_systems must be arrays (empty [] if none found)
"""

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_full_text(doc: fitz.Document) -> str:
    """Extract text from all pages, joined into one string, capped at _MAX_TEXT_CHARS."""
    parts: list[str] = []
    for page_index in range(len(doc)):
        page = doc[page_index]
        text = page.get_text()
        if text.strip():
            parts.append(text)
    full = "\n".join(parts)
    if len(full) > _MAX_TEXT_CHARS:
        full = full[:_MAX_TEXT_CHARS] + "\n...[truncated]"
    return full


def _detect_form_type(text: str) -> str:
    """Heuristic: scan text for known form-type strings."""
    upper = text.upper()
    if "CF1R-PRF" in upper:
        return "CF1R-PRF-01-E"
    if "CF1R" in upper:
        return "CF1R"
    if "RMS-1" in upper or "RMS1" in upper:
        return "RMS-1"
    if "MF1R" in upper:
        return "MF1R"
    return "unknown"


def _detect_compliance_result(text: str) -> str | None:
    """Heuristic: look for PASS / FAIL / Does Not Meet keywords."""
    upper = text.upper()
    # "does not meet" must be checked before FAIL to avoid false positives
    if "DOES NOT MEET" in upper or "DOES NOT COMPLY" in upper:
        return "FAIL"
    # Isolated PASS / FAIL words
    if re.search(r"\bPASS(?:ES|ED)?\b", upper):
        return "PASS"
    if re.search(r"\bFAIL(?:S|ED|URE)?\b", upper):
        return "FAIL"
    return None


def _derive_r_values(surfaces: list[T24Surface]) -> list[T24Surface]:
    """For each surface: if r_value is None but u_factor is given, derive r_value = 1/u_factor."""
    result: list[T24Surface] = []
    for surface in surfaces:
        if surface.r_value is None and surface.u_factor is not None and surface.u_factor > 0:
            surface = surface.model_copy(
                update={"r_value": round(1.0 / surface.u_factor, 1)}
            )
        result.append(surface)
    return result


def _parse_llm_response(
    raw_text: str,
    fallback_form_type: str,
    fallback_compliance: str | None,
) -> Title24Extraction:
    """Parse the LLM JSON response into a Title24Extraction.

    Returns a low-confidence unknown extraction if JSON parsing fails.
    """
    # Strip markdown fences if the model added them despite instructions
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE)

    try:
        data: dict[str, Any] = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return Title24Extraction(
            form_type="unknown",
            confidence=0.3,
        )

    # --- envelope_surfaces ---
    surfaces: list[T24Surface] = []
    for raw_surface in data.get("envelope_surfaces") or []:
        if not isinstance(raw_surface, dict):
            continue
        try:
            surfaces.append(T24Surface(**{
                k: v for k, v in raw_surface.items()
                if k in T24Surface.model_fields
            }))
        except Exception:  # noqa: BLE001
            pass
    surfaces = _derive_r_values(surfaces)

    # --- hvac_systems ---
    hvac_systems: list[T24HvacSystem] = []
    for raw_hvac in data.get("hvac_systems") or []:
        if not isinstance(raw_hvac, dict):
            continue
        try:
            hvac_systems.append(T24HvacSystem(**{
                k: v for k, v in raw_hvac.items()
                if k in T24HvacSystem.model_fields
            }))
        except Exception:  # noqa: BLE001
            pass

    # --- dhw_systems ---
    dhw_systems: list[T24Dhw] = []
    for raw_dhw in data.get("dhw_systems") or []:
        if not isinstance(raw_dhw, dict):
            continue
        try:
            dhw_systems.append(T24Dhw(**{
                k: v for k, v in raw_dhw.items()
                if k in T24Dhw.model_fields
            }))
        except Exception:  # noqa: BLE001
            pass

    # --- scalar fields ---
    form_type = str(data.get("form_type") or fallback_form_type)
    if form_type not in {"CF1R-PRF-01-E", "CF1R", "RMS-1", "MF1R", "unknown"}:
        form_type = fallback_form_type

    raw_compliance = data.get("compliance_result")
    if isinstance(raw_compliance, str) and raw_compliance.upper() in {"PASS", "FAIL", "N/A"}:
        compliance_result: str | None = raw_compliance.upper()
    else:
        compliance_result = fallback_compliance

    def _float_or_none(v: Any) -> float | None:
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def _str_or_none(v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    confidence = 0.85 if len(surfaces) > 0 else 0.5

    return Title24Extraction(
        form_type=form_type,
        project_name=_str_or_none(data.get("project_name")),
        project_address=_str_or_none(data.get("project_address")),
        climate_zone=_str_or_none(data.get("climate_zone")),
        permit_date=_str_or_none(data.get("permit_date")),
        conditioned_floor_area=_float_or_none(data.get("conditioned_floor_area")),
        compliance_result=compliance_result,
        envelope_surfaces=surfaces,
        hvac_systems=hvac_systems,
        dhw_systems=dhw_systems,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_title24_form(
    doc: fitz.Document,
    *,
    api_key: str,
    model: str,
    call_log_rows: list[dict[str, Any]],  # mutated in-place
) -> Title24Extraction:
    """Extract structured Title 24 energy data from a PDF document.

    Strategy:
    1. Extract full text from all pages (capped at 12,000 chars).
    2. Run heuristic detection for form_type and compliance_result.
    3. Call Claude once with the full text to populate all structured fields.
    4. Derive r_value from u_factor where missing.
    5. Return Title24Extraction with confidence 0.85 (>0 surfaces) or 0.5 (none).

    Args:
        doc: An open fitz.Document.
        api_key: Anthropic API key. If empty or placeholder, returns low-confidence stub.
        model: Model identifier, e.g. "claude-sonnet-4-5".
        call_log_rows: List that will be appended with one llm_call_log dict per LLM call.

    Returns:
        Title24Extraction — never raises; falls back to form_type="unknown", confidence=0.3
        on JSON parse failure.
    """
    # --- Step 1: text extraction ---
    document_text = _extract_full_text(doc)

    # --- Step 2: heuristic pre-detection ---
    fallback_form_type = _detect_form_type(document_text)
    fallback_compliance = _detect_compliance_result(document_text)

    # --- Guard: no API key ---
    if not api_key or api_key.startswith("sk-ant-xxx"):
        return Title24Extraction(
            form_type=fallback_form_type,
            compliance_result=fallback_compliance,
            confidence=0.3,
        )

    # --- Step 3: LLM extraction ---
    user_prompt = _USER_PROMPT_TEMPLATE.format(document_text=document_text)
    prompt_hash = hashlib.sha256(user_prompt.encode()).hexdigest()[:16]

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)
        t0 = time.perf_counter()

        response = client.messages.create(
            model=model,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=4096,
            temperature=0,  # invariant #4
        )

        latency_ms = int((time.perf_counter() - t0) * 1000)
        tokens_in: int = response.usage.input_tokens
        tokens_out: int = response.usage.output_tokens
        cost_usd = round(tokens_in * 0.000003 + tokens_out * 0.000015, 6)

        call_log_rows.append(
            {
                "call_id": str(uuid.uuid4()),
                "prompt_hash": prompt_hash,
                "model": model,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency_ms": latency_ms,
                "cost_usd": cost_usd,
                "caller_service": "ingestion.title24_form",
            }
        )

        raw_text = "".join(
            b.text for b in response.content if getattr(b, "type", None) == "text"
        )

    except Exception as exc:  # noqa: BLE001
        print(f"[Title24FormAgent] LLM call failed: {exc}")
        return Title24Extraction(
            form_type=fallback_form_type,
            compliance_result=fallback_compliance,
            confidence=0.3,
        )

    # --- Step 4 & 5: parse + return ---
    return _parse_llm_response(raw_text, fallback_form_type, fallback_compliance)
