"""Architectural reviewer — Phase 04.

Deterministic rules (pass 1):
  AR-EGRESS-WIN-001   Bedroom lacks egress window entry in measurements
  AR-WIN-NCO-001      Window NCO < 5.7 sq ft (or < 5.0 for grade floor)
  AR-WIN-HEIGHT-001   Window NCO height < 24 inches
  AR-WIN-WIDTH-001    Window NCO width < 20 inches
  AR-WIN-SILL-001     Window sill height > 44 inches AFF
  AR-CODE-ANALYSIS-001 Code analysis narrative missing from plan set
  AR-SHOWER-001       Shower/tub wall finish not specified (CBC 1210)
  AR-RESTROOM-001     Restroom details not provided (CBC 1210)
  AR-EXIT-SEP-001     Exit separation < 1/2 diagonal (project-wide note)
  AR-TRAVEL-001       Exit access travel distance not noted on plans
  AR-EXIT-DISC-001    Exit discharge route not shown
  AR-SMOKE-001        Smoke alarm locations not shown in each sleeping room

LLM residue (pass 2):
  AR-LLM-001   Catch architectural issues not covered by deterministic rules
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

import anthropic
import psycopg
import psycopg.rows

from app.reviewers._context import (
    ArchAccessRuleContext,
    FindingPayload,
    FloorPlanEntityRow,
    MeasurementRow,
    emit_findings_aa,
    get_citation_aa,
    load_arch_access_context,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Skill — loaded once at import time.  Missing file is soft-fail; the LLM
# pass is skipped if the skill text is empty.
# ---------------------------------------------------------------------------

_SKILL_PATH: Path = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "skills"
    / "architectural"
    / "SKILL.md"
)

def _load_skill() -> str:
    try:
        return _SKILL_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Architectural skill file not found at %s", _SKILL_PATH)
        return ""

_SKILL_TEXT: str = _load_skill()


# ---------------------------------------------------------------------------
# Rule version stamps
# ---------------------------------------------------------------------------

_RULE_VERSIONS: dict[str, str] = {
    "AR-EGRESS-WIN-001":    "1.0.0",
    "AR-WIN-NCO-001":       "1.0.0",
    "AR-WIN-HEIGHT-001":    "1.0.0",
    "AR-WIN-WIDTH-001":     "1.0.0",
    "AR-WIN-SILL-001":      "1.0.0",
    "AR-CODE-ANALYSIS-001": "1.0.0",
    "AR-SHOWER-001":        "1.0.0",
    "AR-RESTROOM-001":      "1.0.0",
    "AR-EXIT-SEP-001":      "1.0.0",
    "AR-TRAVEL-001":        "1.0.0",
    "AR-EXIT-DISC-001":     "1.0.0",
    "AR-SMOKE-001":         "1.0.0",
    "AR-LLM-001":           "1.0.0",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sheet_ref(sheet_id: str | None, detail: str | None = None) -> dict[str, Any]:
    return {"sheet_id": sheet_id, "detail": detail}


def _entity_evidence(entity_id: str, bbox: list[float]) -> dict[str, Any]:
    return {"entity_id": entity_id, "bbox": bbox}


def _measurement_evidence(m: MeasurementRow) -> dict[str, Any]:
    return {
        "measurement_id": m.measurement_id,
        "type": m.type,
        "value": m.value,
        "unit": m.unit,
        "confidence": m.confidence,
        "tag": m.tag,
        "bbox": m.bbox,
    }


def _project_ref() -> dict[str, Any]:
    return {"sheet_id": None, "detail": "Project-wide"}


def _fallback_citation(code: str, section: str) -> dict[str, Any]:
    """Return a sentinel citation when the KB has no live text for this section.

    NEVER invents frozen_text. The ``note`` field signals that the KB seed
    must be updated before the citation resolves.
    """
    return {
        "code": code,
        "section": section,
        "canonical_id": f"{code}-{section}",
        "frozen_text": None,
        "note": "Section not yet in KB — seed required",
    }


def _get_citations(
    ctx: ArchAccessRuleContext, *canonical_ids: str
) -> list[dict[str, Any]]:
    """Fetch citations from the KB; fall back gracefully when absent.

    Returns a non-empty list in all cases so findings always carry at least
    a reference stub.
    """
    result: list[dict[str, Any]] = []
    for cid in canonical_ids:
        cit = get_citation_aa(ctx, cid)
        if cit is not None:
            result.append(cit)
        else:
            # Parse the canonical_id into code + section for the fallback.
            code, _, section = cid.partition("-")
            result.append(_fallback_citation(code, section))
    return result


# ---------------------------------------------------------------------------
# AR-EGRESS-WIN-001 — Bedroom missing window_nco measurement
# ---------------------------------------------------------------------------

def rule_ar_egress_win_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """For every bedroom room entity, verify at least one window_nco
    measurement exists on the same sheet.  If not, require the applicant to
    confirm the emergency escape and rescue opening.
    """
    findings: list[FindingPayload] = []
    citations = _get_citations(ctx, "CRC-R310.1")

    # Build set of sheet_ids that already have a window_nco measurement.
    sheets_with_nco: set[str] = {
        m.sheet_id for m in ctx.measurements if m.type == "window_nco"
    }

    for bedroom in ctx.bedroom_rooms:
        if bedroom.sheet_id in sheets_with_nco:
            continue  # at least one NCO measurement exists on this sheet

        label = bedroom.room_label or bedroom.tag or "unlabeled bedroom"
        findings.append(
            FindingPayload(
                rule_id="AR-EGRESS-WIN-001",
                rule_version=_RULE_VERSIONS["AR-EGRESS-WIN-001"],
                severity="provide",
                sheet_reference=_sheet_ref(
                    bedroom.sheet_id,
                    f"Bedroom: {label}",
                ),
                evidence=[_entity_evidence(bedroom.entity_id, bedroom.bbox)],
                citations=citations,
                draft_comment_text=(
                    f"Bedroom '{label}' on sheet {bedroom.sheet_id}: confirm the "
                    "window(s) serving this sleeping room meet the emergency escape "
                    "and rescue opening requirements per CRC §R310. Provide a window "
                    "schedule entry with net clear opening (NCO) area, height, width, "
                    "and sill height for each egress window in this room."
                ),
                confidence=0.87,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# AR-WIN-NCO-001 — Window NCO area below minimum
# ---------------------------------------------------------------------------

def rule_ar_win_nco_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Flag any window_nco measurement below the CRC R310.2.1 minimums.

    Grade / below-grade floor minimum: 5.0 sqft.
    Upper floors: 5.7 sqft.  Since we cannot always determine the floor
    level from measurements alone we cite 5.7 sqft and note that 5.0 applies
    at grade so the reviewer can confirm.
    """
    findings: list[FindingPayload] = []
    citations = _get_citations(ctx, "CRC-R310.2.1")

    UPPER_FLOOR_MIN = 5.7
    GRADE_FLOOR_MIN = 5.0

    for m in ctx.measurements:
        if m.type != "window_nco":
            continue
        if m.value >= UPPER_FLOOR_MIN:
            continue

        tag_desc = f" (tag: {m.tag})" if m.tag else ""
        if m.value < GRADE_FLOOR_MIN:
            note = (
                f"The measured NCO of {m.value:.2f} sqft is below the 5.0 sqft "
                "minimum for grade-floor windows and below the 5.7 sqft minimum "
                "for windows on upper floors."
            )
        else:
            note = (
                f"The measured NCO of {m.value:.2f} sqft meets the 5.0 sqft grade-floor "
                "minimum but is below the 5.7 sqft minimum required for upper-floor "
                "emergency escape and rescue openings. Confirm this window is at "
                "grade level; if above grade, revise."
            )

        findings.append(
            FindingPayload(
                rule_id="AR-WIN-NCO-001",
                rule_version=_RULE_VERSIONS["AR-WIN-NCO-001"],
                severity="revise",
                sheet_reference=_sheet_ref(m.sheet_id, f"Window NCO{tag_desc}"),
                evidence=[_measurement_evidence(m)],
                citations=citations,
                draft_comment_text=(
                    f"Sheet {m.sheet_id}: window{tag_desc} has a net clear opening "
                    f"(NCO) area of {m.value:.2f} sqft. {note} "
                    "Revise the window to provide the required minimum net clear "
                    "opening. (CRC §R310.2.1)"
                ),
                confidence=0.90,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# AR-WIN-HEIGHT-001 — Window NCO clear height < 24 inches
# ---------------------------------------------------------------------------

def rule_ar_win_height_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Flag windows whose clear opening height is below 24 inches (CRC R310.2.2)."""
    findings: list[FindingPayload] = []
    citations = _get_citations(ctx, "CRC-R310.2.2")
    MIN_HEIGHT_IN = 24.0

    for m in ctx.measurements:
        if m.type != "window_clear_height":
            continue
        if m.value >= MIN_HEIGHT_IN:
            continue

        tag_desc = f" (tag: {m.tag})" if m.tag else ""
        findings.append(
            FindingPayload(
                rule_id="AR-WIN-HEIGHT-001",
                rule_version=_RULE_VERSIONS["AR-WIN-HEIGHT-001"],
                severity="revise",
                sheet_reference=_sheet_ref(
                    m.sheet_id, f"Window clear height{tag_desc}"
                ),
                evidence=[_measurement_evidence(m)],
                citations=citations,
                draft_comment_text=(
                    f"Sheet {m.sheet_id}: window{tag_desc} has a net clear opening "
                    f"height of {m.value:.1f} inches. CRC §R310.2.2 requires a "
                    f"minimum net clear opening height of {MIN_HEIGHT_IN:.0f} inches "
                    "for emergency escape and rescue openings. Revise window "
                    "specifications to comply."
                ),
                confidence=0.90,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# AR-WIN-WIDTH-001 — Window NCO clear width < 20 inches
# ---------------------------------------------------------------------------

def rule_ar_win_width_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Flag windows whose clear opening width is below 20 inches (CRC R310.2.3)."""
    findings: list[FindingPayload] = []
    citations = _get_citations(ctx, "CRC-R310.2.3")
    MIN_WIDTH_IN = 20.0

    for m in ctx.measurements:
        if m.type != "window_clear_width":
            continue
        if m.value >= MIN_WIDTH_IN:
            continue

        tag_desc = f" (tag: {m.tag})" if m.tag else ""
        findings.append(
            FindingPayload(
                rule_id="AR-WIN-WIDTH-001",
                rule_version=_RULE_VERSIONS["AR-WIN-WIDTH-001"],
                severity="revise",
                sheet_reference=_sheet_ref(
                    m.sheet_id, f"Window clear width{tag_desc}"
                ),
                evidence=[_measurement_evidence(m)],
                citations=citations,
                draft_comment_text=(
                    f"Sheet {m.sheet_id}: window{tag_desc} has a net clear opening "
                    f"width of {m.value:.1f} inches. CRC §R310.2.3 requires a "
                    f"minimum net clear opening width of {MIN_WIDTH_IN:.0f} inches "
                    "for emergency escape and rescue openings. Revise window "
                    "specifications to comply."
                ),
                confidence=0.90,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# AR-WIN-SILL-001 — Window sill height > 44 inches AFF
# ---------------------------------------------------------------------------

def rule_ar_win_sill_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Flag windows with a sill height above 44 inches AFF (CRC R310.2.4)."""
    findings: list[FindingPayload] = []
    citations = _get_citations(ctx, "CRC-R310.2.4")
    MAX_SILL_IN = 44.0

    for m in ctx.measurements:
        if m.type != "window_sill_height":
            continue
        if m.value <= MAX_SILL_IN:
            continue

        tag_desc = f" (tag: {m.tag})" if m.tag else ""
        findings.append(
            FindingPayload(
                rule_id="AR-WIN-SILL-001",
                rule_version=_RULE_VERSIONS["AR-WIN-SILL-001"],
                severity="revise",
                sheet_reference=_sheet_ref(
                    m.sheet_id, f"Window sill height{tag_desc}"
                ),
                evidence=[_measurement_evidence(m)],
                citations=citations,
                draft_comment_text=(
                    f"Sheet {m.sheet_id}: window{tag_desc} has a sill height of "
                    f"{m.value:.1f} inches above the finished floor. CRC §R310.2.4 "
                    f"requires that the sill height of an emergency escape and rescue "
                    f"opening shall not exceed {MAX_SILL_IN:.0f} inches above the "
                    "finished floor. Lower the sill height or provide an approved "
                    "window well to comply."
                ),
                confidence=0.90,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# AR-CODE-ANALYSIS-001 — Code analysis narrative missing
# ---------------------------------------------------------------------------

def rule_ar_code_analysis_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Fire a project-wide finding when no code_note entities are present.

    A code analysis narrative is required on the plan set; its absence means
    the examiner cannot confirm occupancy, construction type, area, or egress
    basis. (CBC §1004.5 / CBC §107.2.1)
    """
    code_notes = [
        e for e in ctx.floor_plan_entities if e.entity_type == "code_note"
    ]
    if code_notes:
        return []

    citations = _get_citations(ctx, "CBC-1004.5")
    return [
        FindingPayload(
            rule_id="AR-CODE-ANALYSIS-001",
            rule_version=_RULE_VERSIONS["AR-CODE-ANALYSIS-001"],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=citations,
            draft_comment_text=(
                "Provide a complete code analysis on the drawings. The analysis "
                "shall include at minimum: occupancy classification, construction "
                "type, building area, occupant loads per CBC Table 1004.5, and the "
                "basis for the means of egress design. (CBC §1004.5)"
            ),
            confidence=0.85,
        )
    ]


# ---------------------------------------------------------------------------
# AR-SHOWER-001 — Shower / tub wall finish not specified
# ---------------------------------------------------------------------------

def rule_ar_shower_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Flag when bathrooms exist but no code note references shower wall finish.

    CBC §1210 requires nonabsorbent wall finish from floor to 70 in. in wet
    areas.  We proxy this check: if there are bathroom entities but no
    code_note whose geometry_notes mention shower-related keywords, emit a
    'provide' finding.
    """
    bathrooms = [
        e for e in ctx.floor_plan_entities
        if e.entity_type == "room" and e.room_use in ("bathroom", "bath", "restroom")
    ]
    if not bathrooms:
        return []

    # Check if any code note mentions shower/tile/waterproof finish.
    _SHOWER_KEYWORDS = {"shower", "tub", "tile", "waterproof", "1210", "nonabsorb"}
    code_notes = [
        e for e in ctx.floor_plan_entities if e.entity_type == "code_note"
    ]
    has_shower_note = any(
        any(kw in (e.geometry_notes or "").lower() for kw in _SHOWER_KEYWORDS)
        for e in code_notes
    )
    if has_shower_note:
        return []

    citations = _get_citations(ctx, "CBC-1210")
    # Use the sheet_id of the first bathroom found for location context.
    first_bath = bathrooms[0]
    return [
        FindingPayload(
            rule_id="AR-SHOWER-001",
            rule_version=_RULE_VERSIONS["AR-SHOWER-001"],
            severity="provide",
            sheet_reference=_sheet_ref(
                first_bath.sheet_id, "Shower/tub wall finish"
            ),
            evidence=[
                _entity_evidence(b.entity_id, b.bbox) for b in bathrooms[:4]
            ],
            citations=citations,
            draft_comment_text=(
                "Provide detail(s) showing the wall finish materials in shower and "
                "tub enclosures. Wall finishes in shower and tub areas shall be of a "
                "smooth, hard, nonabsorbent surface to a height of not less than "
                "70 inches above the drain inlet. (CBC §1210)"
            ),
            confidence=0.85,
        )
    ]


# ---------------------------------------------------------------------------
# AR-RESTROOM-001 — Restroom detail drawings not provided
# ---------------------------------------------------------------------------

def rule_ar_restroom_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Flag when bathrooms exist but no restroom detail is evident in code notes.

    CBC §1210 requires details showing waterproofing construction at wet areas.
    We check for code_note keywords referencing detail, membrane, or threshold.
    """
    bathrooms = [
        e for e in ctx.floor_plan_entities
        if e.entity_type == "room" and e.room_use in ("bathroom", "bath", "restroom")
    ]
    if not bathrooms:
        return []

    _DETAIL_KEYWORDS = {"detail", "membrane", "threshold", "substrate", "backer", "1210"}
    code_notes = [
        e for e in ctx.floor_plan_entities if e.entity_type == "code_note"
    ]
    has_detail_note = any(
        any(kw in (e.geometry_notes or "").lower() for kw in _DETAIL_KEYWORDS)
        for e in code_notes
    )
    if has_detail_note:
        return []

    citations = _get_citations(ctx, "CBC-1210")
    first_bath = bathrooms[0]
    return [
        FindingPayload(
            rule_id="AR-RESTROOM-001",
            rule_version=_RULE_VERSIONS["AR-RESTROOM-001"],
            severity="provide",
            sheet_reference=_sheet_ref(
                first_bath.sheet_id, "Restroom / wet-area detail"
            ),
            evidence=[
                _entity_evidence(b.entity_id, b.bbox) for b in bathrooms[:4]
            ],
            citations=citations,
            draft_comment_text=(
                "Provide typical bathroom detail(s) showing wall substrate, "
                "waterproofing membrane, tile or finish material, and threshold "
                "construction at shower/tub enclosures. Detail shall demonstrate "
                "compliance with CBC §1210 for wet-area wall and floor finish "
                "requirements."
            ),
            confidence=0.85,
        )
    ]


# ---------------------------------------------------------------------------
# AR-EXIT-SEP-001 — Exit separation confirmation
# ---------------------------------------------------------------------------

def rule_ar_exit_sep_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Emit a clarify finding when plans show ≥2 floor-plan sheets (multi-floor)
    or when the entity count is large enough that two exits may be required.

    Because we cannot directly measure exit separation without calibrated
    geometry tools, we emit a 'clarify' note asking the applicant to demonstrate
    compliance with CBC §1014.3.  This always fires for multi-floor projects.
    """
    # Detect multi-floor: look for floor-plan sheets with distinct level
    # indicators in the sheet canonical_title (e.g. "FIRST FLOOR", "SECOND FLOOR").
    fp_sheets = [
        s for s in ctx.sheets
        if s.sheet_type and "floor plan" in (s.sheet_type or "").lower()
    ]
    is_multi_floor = len(fp_sheets) >= 2

    # Also fire if the project has stair entities (implies vertical circulation).
    has_stairs = any(
        e.entity_type == "stair" for e in ctx.floor_plan_entities
    )

    # Also fire if room count is large (occupant load may require 2 exits).
    room_count = sum(1 for e in ctx.floor_plan_entities if e.entity_type == "room")
    large_floor_plan = room_count >= 5

    if not (is_multi_floor or has_stairs or large_floor_plan):
        return []

    citations = _get_citations(ctx, "CBC-1014.3")
    reason = (
        "multi-floor plan detected" if is_multi_floor
        else "stair entities detected" if has_stairs
        else f"{room_count} room entities found"
    )
    return [
        FindingPayload(
            rule_id="AR-EXIT-SEP-001",
            rule_version=_RULE_VERSIONS["AR-EXIT-SEP-001"],
            severity="clarify",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=citations,
            draft_comment_text=(
                "Confirm that exits are placed a distance apart equal to not less "
                "than one-half the maximum overall diagonal dimension of the building "
                "(or floor area served). Provide the diagonal dimension calculation "
                f"on the plans. ({reason}) (CBC §1014.3)"
            ),
            confidence=0.82,
        )
    ]


# ---------------------------------------------------------------------------
# AR-TRAVEL-001 — Exit access travel distance not annotated
# ---------------------------------------------------------------------------

def rule_ar_travel_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Fire when floor-plan sheets exist but no travel-distance annotation is
    found in code notes.  CBC §1017.2.2 limits travel distance to 250 ft for
    Group R-3 occupancies.
    """
    fp_sheets = [
        s for s in ctx.sheets
        if s.sheet_type and "floor plan" in (s.sheet_type or "").lower()
    ]
    if not fp_sheets:
        return []

    _TRAVEL_KEYWORDS = {"travel distance", "max travel", "egress distance", "1017"}
    code_notes = [
        e for e in ctx.floor_plan_entities if e.entity_type == "code_note"
    ]
    has_travel_note = any(
        any(kw in (e.geometry_notes or "").lower() for kw in _TRAVEL_KEYWORDS)
        for e in code_notes
    )
    if has_travel_note:
        return []

    citations = _get_citations(ctx, "CBC-1017.2.2")
    first_fp = fp_sheets[0]
    return [
        FindingPayload(
            rule_id="AR-TRAVEL-001",
            rule_version=_RULE_VERSIONS["AR-TRAVEL-001"],
            severity="provide",
            sheet_reference=_sheet_ref(
                first_fp.sheet_id, "Exit access travel distance"
            ),
            evidence=[],
            citations=citations,
            draft_comment_text=(
                "Provide the maximum exit access travel distance annotation on the "
                "floor plans. For Group R-3 occupancies, exit access travel distance "
                "shall not exceed 250 feet. Show the travel distance path and "
                "dimension on all floor plan sheets. (CBC §1017.2.2)"
            ),
            confidence=0.85,
        )
    ]


# ---------------------------------------------------------------------------
# AR-EXIT-DISC-001 — Exit discharge route not shown
# ---------------------------------------------------------------------------

def rule_ar_exit_disc_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Flag when stair or multi-floor indicators exist but no exit entity is
    recorded, meaning the exit discharge path to the exterior is not evident
    on the plans.  (CBC §1019.2)
    """
    has_stairs = any(
        e.entity_type == "stair" for e in ctx.floor_plan_entities
    )
    has_exit_entity = any(
        e.entity_type == "exit" for e in ctx.floor_plan_entities
    )
    is_multi_floor = len([
        s for s in ctx.sheets
        if s.sheet_type and "floor plan" in (s.sheet_type or "").lower()
    ]) >= 2

    if not (has_stairs or is_multi_floor):
        return []  # single-story with no stairs — not triggered
    if has_exit_entity:
        return []  # exits are documented

    citations = _get_citations(ctx, "CBC-1019.2")
    return [
        FindingPayload(
            rule_id="AR-EXIT-DISC-001",
            rule_version=_RULE_VERSIONS["AR-EXIT-DISC-001"],
            severity="clarify",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=citations,
            draft_comment_text=(
                "Clarify the exit discharge route from all exits to the public way. "
                "Show the exit discharge path on the site plan or ground-floor plan, "
                "including the path through any exit passageway or yard. "
                "(CBC §1019.2)"
            ),
            confidence=0.80,
        )
    ]


# ---------------------------------------------------------------------------
# AR-SMOKE-001 — Smoke alarm locations not shown in sleeping rooms
# ---------------------------------------------------------------------------

def rule_ar_smoke_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """For each bedroom room entity that has no smoke-alarm measurement or
    annotation, emit a 'provide' finding citing CRC §R314.3.
    """
    findings: list[FindingPayload] = []
    citations = _get_citations(ctx, "CRC-R314.3")

    # Build a set of sheet_ids that have a smoke-alarm measurement.
    sheets_with_smoke: set[str] = {
        m.sheet_id
        for m in ctx.measurements
        if m.type in ("smoke_alarm", "smoke_detector")
    }

    for bedroom in ctx.bedroom_rooms:
        if bedroom.sheet_id in sheets_with_smoke:
            continue  # smoke alarm shown on this sheet

        label = bedroom.room_label or bedroom.tag or "unlabeled bedroom"
        findings.append(
            FindingPayload(
                rule_id="AR-SMOKE-001",
                rule_version=_RULE_VERSIONS["AR-SMOKE-001"],
                severity="provide",
                sheet_reference=_sheet_ref(
                    bedroom.sheet_id,
                    f"Bedroom: {label} — smoke alarm location",
                ),
                evidence=[_entity_evidence(bedroom.entity_id, bedroom.bbox)],
                citations=citations,
                draft_comment_text=(
                    f"Sheet {bedroom.sheet_id}: provide smoke alarm location(s) in "
                    f"bedroom '{label}', in the corridor or hallway outside the "
                    "sleeping area, and on each story of the dwelling unit per "
                    "CRC §R314.3. Show smoke alarm symbols on all applicable floor "
                    "plan sheets."
                ),
                confidence=0.87,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

_RULES = [
    rule_ar_egress_win_001,
    rule_ar_win_nco_001,
    rule_ar_win_height_001,
    rule_ar_win_width_001,
    rule_ar_win_sill_001,
    rule_ar_code_analysis_001,
    rule_ar_shower_001,
    rule_ar_restroom_001,
    rule_ar_exit_sep_001,
    rule_ar_travel_001,
    rule_ar_exit_disc_001,
    rule_ar_smoke_001,
]


# ---------------------------------------------------------------------------
# LLM residue pass — AR-LLM-001
# ---------------------------------------------------------------------------

def _build_project_summary(
    ctx: ArchAccessRuleContext,
    deterministic_findings: list[FindingPayload],
) -> str:
    """Construct a compact text summary of the project for the LLM prompt."""
    room_count = sum(1 for e in ctx.floor_plan_entities if e.entity_type == "room")
    bedroom_count = len(ctx.bedroom_rooms)
    bathroom_count = sum(
        1 for e in ctx.floor_plan_entities
        if e.entity_type == "room" and e.room_use in ("bathroom", "bath", "restroom")
    )
    door_count = sum(1 for e in ctx.floor_plan_entities if e.entity_type == "door")
    window_count = sum(1 for e in ctx.floor_plan_entities if e.entity_type == "window")
    stair_count = sum(1 for e in ctx.floor_plan_entities if e.entity_type == "stair")
    fp_sheet_count = sum(
        1 for s in ctx.sheets
        if s.sheet_type and "floor plan" in s.sheet_type.lower()
    )

    sheet_titles = ", ".join(
        f"{s.canonical_id or s.sheet_id}: {s.canonical_title or '(no title)'}"
        for s in ctx.sheets[:12]
    )
    already_flagged = [fp.rule_id for fp in deterministic_findings]

    return (
        f"Project: {ctx.project_address} | jurisdiction: {ctx.jurisdiction} | "
        f"effective_date: {ctx.effective_date}\n"
        f"Sheets ({len(ctx.sheets)}): {sheet_titles}\n"
        f"Floor plan sheets: {fp_sheet_count}\n"
        f"Rooms: {room_count} total, {bedroom_count} bedrooms, {bathroom_count} bathrooms\n"
        f"Doors: {door_count}, Windows: {window_count}, Stairs: {stair_count}\n"
        f"Measurements: {len(ctx.measurements)}\n"
        f"Deterministic rules already fired: {', '.join(already_flagged) or 'none'}"
    )


def _hash_prompt(system: str, user: str, model: str) -> str:
    content = f"{model}|{system}|{user}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _run_llm_residue(
    ctx: ArchAccessRuleContext,
    anthropic_api_key: str,
    deterministic_findings: list[FindingPayload],
) -> list[FindingPayload]:
    """Run a single LLM call (temperature=0) to catch residue issues.

    Returns a (possibly empty) list of additional FindingPayloads.
    Every citation is retrieved live from the KB; if not found the citation
    stub is included with frozen_text=None rather than hallucinated text.
    """
    if not _SKILL_TEXT:
        logger.warning(
            "AR-LLM-001 skipped: architectural skill text is empty (file missing?)."
        )
        return []

    project_summary = _build_project_summary(ctx, deterministic_findings)
    already_fired = [fp.rule_id for fp in deterministic_findings]

    user_prompt = (
        "You are reviewing a residential building permit plan set for compliance with "
        "the 2022 California Building Standards Code (CBC) and California Residential "
        f"Code (CRC).\n\n"
        f"Project summary:\n{project_summary}\n\n"
        "The following deterministic rule IDs have already been emitted and must NOT "
        f"be duplicated: {', '.join(already_fired) or 'none'}.\n\n"
        "Identify any additional ARCHITECTURAL code compliance issues not already "
        "covered by those rules. Focus on: egress, occupant load, exit separation, "
        "corridor widths, stair geometry, opening protection, and code-analysis "
        "narrative completeness.\n\n"
        "Respond with a JSON array only — no prose before or after. Each element:\n"
        "{\n"
        '  "rule_id": "AR-LLM-001",\n'
        '  "severity": "revise" | "provide" | "clarify" | "reference_only",\n'
        '  "draft_comment_text": "<specific, non-hallucinated comment>",\n'
        '  "sheet_id": "<sheet_id or null>",\n'
        '  "citations": [{"code": "<CBC|CRC>", "section": "<section>"}],\n'
        '  "confidence": <0.70 to 0.80>\n'
        "}\n"
        "If no additional issues are found, respond with an empty array: []"
    )

    model = "claude-sonnet-4-6"
    prompt_hash = _hash_prompt(_SKILL_TEXT, user_prompt, model)
    t0 = time.monotonic()

    try:
        client = anthropic.Anthropic(api_key=anthropic_api_key)
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            temperature=0,
            system=_SKILL_TEXT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        raw_text = response.content[0].text if response.content else "[]"
        usage = response.usage

        logger.info(
            "AR-LLM-001 call complete: model=%s prompt_hash=%s "
            "input_tokens=%d output_tokens=%d latency_ms=%d",
            model,
            prompt_hash,
            usage.input_tokens,
            usage.output_tokens,
            latency_ms,
        )
    except Exception as exc:  # pragma: no cover
        logger.error("AR-LLM-001 Anthropic API call failed: %s", exc)
        return []

    # Parse the JSON response.
    try:
        # Strip markdown fences if present.
        stripped = raw_text.strip()
        if stripped.startswith("```"):
            stripped = stripped.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        llm_items: list[dict[str, Any]] = json.loads(stripped)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("AR-LLM-001 JSON parse failed (%s). Raw: %r", exc, raw_text[:300])
        return []

    if not isinstance(llm_items, list):
        logger.warning("AR-LLM-001 unexpected JSON type: %s", type(llm_items))
        return []

    findings: list[FindingPayload] = []
    for item in llm_items:
        if not isinstance(item, dict):
            continue

        severity = item.get("severity", "clarify")
        if severity not in ("revise", "provide", "clarify", "reference_only"):
            severity = "clarify"

        confidence = float(item.get("confidence", 0.73))
        confidence = max(0.60, min(0.85, confidence))  # clamp to LLM range

        sheet_id: str | None = item.get("sheet_id") or None
        draft_text: str = str(item.get("draft_comment_text", "")).strip()

        # Retrieve citations from the KB; never use LLM-supplied frozen text.
        raw_citations: list[dict[str, Any]] = item.get("citations", [])
        retrieved_citations: list[dict[str, Any]] = []
        for rc in raw_citations:
            if not isinstance(rc, dict):
                continue
            code = rc.get("code", "")
            section = rc.get("section", "")
            if not code or not section:
                continue
            canonical_id = f"{code.upper()}-{section}"
            live = get_citation_aa(ctx, canonical_id)
            if live is not None:
                retrieved_citations.append(live)
            else:
                # Fallback stub — never hallucinate frozen_text.
                retrieved_citations.append(_fallback_citation(code, section))

        if not draft_text:
            continue  # skip empty findings

        findings.append(
            FindingPayload(
                rule_id="AR-LLM-001",
                rule_version=_RULE_VERSIONS["AR-LLM-001"],
                severity=severity,
                sheet_reference=_sheet_ref(sheet_id),
                evidence=[],
                citations=retrieved_citations,
                draft_comment_text=draft_text,
                confidence=confidence,
                llm_reasoner_id=model,
                prompt_hash=prompt_hash,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# ArchitecturalReviewer — orchestrator
# ---------------------------------------------------------------------------


class ArchitecturalReviewer:
    """Two-pass architectural reviewer.

    Pass 1: deterministic rules (no LLM).
    Pass 2: LLM residue (AR-LLM-001) — only when ``anthropic_api_key`` is provided.

    Call ``run()`` once per submittal round.  It fetches all needed data from
    the database, runs every rule, and bulk-inserts findings. The connection
    is not committed here — the caller owns the transaction.
    """

    DISCIPLINE = "architectural"

    def run(
        self,
        conn: psycopg.Connection,  # type: ignore[type-arg]
        *,
        project_id: str,
        submittal_id: str,
        review_round: int,
        database_url: str,
        anthropic_api_key: str | None = None,
        extractor_versions_used: list[str] | None = None,
    ) -> list[str]:
        """Run all architectural rules and persist findings.

        Returns the list of created finding IDs.  The caller must commit.
        """
        ctx: ArchAccessRuleContext = load_arch_access_context(
            conn,
            project_id=project_id,
            submittal_id=submittal_id,
            review_round=review_round,
            database_url=database_url,
        )

        all_findings: list[FindingPayload] = []

        # --- Pass 1: deterministic rules ---
        for rule_fn in _RULES:
            rule_findings = rule_fn(ctx)
            all_findings.extend(rule_findings)

        logger.info(
            "ArchitecturalReviewer: %d deterministic finding(s) for project %s",
            len(all_findings),
            project_id,
        )

        # --- Pass 2: LLM residue ---
        if anthropic_api_key:
            llm_findings = _run_llm_residue(ctx, anthropic_api_key, all_findings)
            if llm_findings:
                logger.info(
                    "ArchitecturalReviewer: AR-LLM-001 produced %d additional finding(s).",
                    len(llm_findings),
                )
            all_findings.extend(llm_findings)
        else:
            logger.warning(
                "ArchitecturalReviewer: anthropic_api_key not provided — "
                "AR-LLM-001 residue pass skipped."
            )

        if not all_findings:
            return []

        return emit_findings_aa(
            conn,
            ctx,
            all_findings,
            self.DISCIPLINE,
            extractor_versions_used,
        )
