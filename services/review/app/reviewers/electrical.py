"""Electrical reviewer — Phase 05.

Deterministic rules:
  ELEC-PANEL-LOC-001        Panel/sub-panel locations not shown — BV #45
  ELEC-PANEL-AMP-001        Panel amperage not specified — BV #45
  ELEC-R21-COMPLIANCE-001   CEC R-2.1 compliance not verified — BV #46
  ELEC-GFCI-001             GFCI protection not specified in wet areas — general
  ELEC-AFCI-001             AFCI protection not specified in living areas — general
  ELEC-EXT-LIGHTING-001     Switched light at exterior doors not shown — BV #47
  ELEC-ACCESSIBLE-CTRL-001  Accessible controls (15-48" AFF) not specified — BV #46

No LLM residue pass — all rules are absence-based deterministic checks.
"""
from __future__ import annotations

import logging
from typing import Any

import psycopg
import psycopg.rows

from inzohra_shared.critical_path import requires_licensed_review as _is_critical

from app.reviewers._context import (
    ArchAccessRuleContext,
    FindingPayload,
    FloorPlanEntityRow,
    emit_findings_aa,
    get_citation_aa,
    load_arch_access_context,
)

logger = logging.getLogger(__name__)

_RULE_VERSIONS: dict[str, str] = {
    "ELEC-PANEL-LOC-001":       "1.0.0",
    "ELEC-PANEL-AMP-001":       "1.0.0",
    "ELEC-R21-COMPLIANCE-001":  "1.0.0",
    "ELEC-GFCI-001":            "1.0.0",
    "ELEC-AFCI-001":            "1.0.0",
    "ELEC-EXT-LIGHTING-001":    "1.0.0",
    "ELEC-ACCESSIBLE-CTRL-001": "1.0.0",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sheet_ref(sheet_id: str | None, detail: str | None = None) -> dict[str, Any]:
    return {"sheet_id": sheet_id, "detail": detail}


def _entity_evidence(entity_id: str, bbox: list[float]) -> dict[str, Any]:
    return {"entity_id": entity_id, "bbox": bbox}


def _project_ref() -> dict[str, Any]:
    return {"sheet_id": None, "detail": "Project-wide"}


def _fallback_citation(code: str, section: str) -> dict[str, Any]:
    """Return a stub citation when the KB lookup returns None.

    Never invents text — frozen_text is explicitly None with a note.
    """
    return {
        "code": code,
        "section": section,
        "frozen_text": None,
        "note": "Section not in KB",
    }


def _get_cit(
    ctx: ArchAccessRuleContext,
    canonical_id: str,
    *,
    fallback_code: str = "CEC",
    fallback_section: str = "210.70",
) -> dict[str, Any]:
    """Return a live citation or a clearly-flagged fallback — never hallucinated."""
    cit = get_citation_aa(ctx, canonical_id)
    if cit is not None:
        return cit
    # Derive fallback section from canonical_id where possible
    if "-" in canonical_id:
        parts = canonical_id.split("-", 1)
        fallback_code = parts[0]
        fallback_section = parts[1]
    return _fallback_citation(fallback_code, fallback_section)


def _has_code_note_with_text(ctx: ArchAccessRuleContext, keyword: str) -> bool:
    """True if any code_note entity has a room_label or geometry_notes containing keyword."""
    kw = keyword.lower()
    for e in ctx.floor_plan_entities:
        if e.entity_type != "code_note":
            continue
        label = (e.room_label or "").lower()
        notes = (e.geometry_notes or "").lower()
        if kw in label or kw in notes:
            return True
    return False


def _has_entity_type_keyword(ctx: ArchAccessRuleContext, keyword: str) -> bool:
    """True if any entity's entity_type contains the given keyword (case-insensitive)."""
    kw = keyword.lower()
    return any(kw in (e.entity_type or "").lower() for e in ctx.floor_plan_entities)


def _has_r21_indicators(ctx: ArchAccessRuleContext) -> bool:
    """True if any title_block or code_note references R-2.1 occupancy."""
    for tb in ctx.title_blocks:
        title = (tb.sheet_title or "").lower()
        name = (tb.project_name or "").lower()
        if "r-2.1" in title or "r-2.1" in name or "r2.1" in title or "r2.1" in name:
            return True
    for e in ctx.floor_plan_entities:
        label = (e.room_label or "").lower()
        notes = (e.geometry_notes or "").lower()
        if "r-2.1" in label or "r-2.1" in notes or "r2.1" in label or "r2.1" in notes:
            return True
    return False


def _bath_or_kitchen_entities(ctx: ArchAccessRuleContext) -> list[FloorPlanEntityRow]:
    """All floor-plan entities that are bathrooms or kitchens."""
    result: list[FloorPlanEntityRow] = []
    for e in ctx.floor_plan_entities:
        use = (e.room_use or "").lower()
        label = (e.room_label or "").lower()
        if (
            "bath" in use or "toilet" in use or "bath" in label or "toilet" in label
            or "kitchen" in use or "kitchen" in label
        ):
            result.append(e)
    return result


def _exterior_door_entities(ctx: ArchAccessRuleContext) -> list[FloorPlanEntityRow]:
    """All floor-plan entities that appear to be exterior doors or exit elements."""
    result: list[FloorPlanEntityRow] = []
    for e in ctx.floor_plan_entities:
        use = (e.room_use or "").lower()
        notes = (e.geometry_notes or "").lower()
        label = (e.room_label or "").lower()
        if (
            (e.entity_type == "door" and ("exterior" in notes or "exterior" in label))
            or use == "exit"
            or "exterior door" in notes
            or "exterior door" in label
        ):
            result.append(e)
    return result


# ---------------------------------------------------------------------------
# ELEC-PANEL-LOC-001 — Panel/sub-panel locations not shown (BV #45)
# ---------------------------------------------------------------------------


def rule_elec_panel_loc_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when no electrical panel entity or 'panel' code_note is present."""
    # Check for entity with 'electrical' in entity_type
    has_elec_entity = _has_entity_type_keyword(ctx, "electrical")
    # Check for code_note mentioning 'panel' or 'electrical panel'
    has_panel_note = (
        _has_code_note_with_text(ctx, "panel")
        or _has_code_note_with_text(ctx, "electrical panel")
    )

    if has_elec_entity or has_panel_note:
        return []

    cit = _get_cit(ctx, "CEC-230.70")
    rule_id = "ELEC-PANEL-LOC-001"
    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Show all electrical panel and sub-panel locations on the floor plans. "
                "Provide a load calculation schedule specifying panel amperage, main "
                "overcurrent protection, and branch circuit listing for both the R-3 "
                "and R-2.1 occupancies. Each occupancy shall have its own electrical "
                "service or clearly delineated panel sections. "
                "(CEC \u00a7230.70, CBC \u00a7107.2.1)"
            ),
            confidence=0.80,
            requires_licensed_review=_is_critical(rule_id),
        )
    ]


# ---------------------------------------------------------------------------
# ELEC-PANEL-AMP-001 — Panel amperage not specified (BV #45)
# ---------------------------------------------------------------------------


def rule_elec_panel_amp_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when no amperage specification is found in code_notes."""
    # Check for any code_note mentioning amperage values or unit
    has_amp_note = (
        _has_code_note_with_text(ctx, "200a")
        or _has_code_note_with_text(ctx, "100a")
        or _has_code_note_with_text(ctx, "amps")
        or _has_code_note_with_text(ctx, "amperage")
    )

    if has_amp_note:
        return []

    cit = _get_cit(ctx, "CEC-230.70")
    rule_id = "ELEC-PANEL-AMP-001"
    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Specify the amperage of each electrical panel and sub-panel serving "
                "the project on the electrical plans or schedule. Include the main "
                "disconnect rating and all branch circuit breaker sizes. "
                "(CEC \u00a7230.70)"
            ),
            confidence=0.80,
            requires_licensed_review=_is_critical(rule_id),
        )
    ]


# ---------------------------------------------------------------------------
# ELEC-R21-COMPLIANCE-001 — CEC R-2.1 compliance not verified (BV #46)
# ---------------------------------------------------------------------------


def rule_elec_r21_compliance_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when project has R-2.1 indicators but no CEC compliance note."""
    if not _has_r21_indicators(ctx):
        return []

    has_compliance_note = (
        _has_code_note_with_text(ctx, "cec")
        or _has_code_note_with_text(ctx, "group r-2.1 electrical")
        or _has_code_note_with_text(ctx, "r-2.1 electrical")
    )
    if has_compliance_note:
        return []

    cit = _get_cit(ctx, "CEC-210.8-A")
    rule_id = "ELEC-R21-COMPLIANCE-001"
    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Verify and document on the plans that all electrical systems in the "
                "Group R-2.1 occupancy comply with the California Electrical Code for "
                "Group R-2 occupancies. Confirm that receptacle outlets are located "
                "within 15\u201348 inches AFF for accessibility, all wet areas have "
                "GFCI protection, and tamper-resistant receptacles are provided in all "
                "accessible dwelling units. (CEC \u00a7210.8(A), \u00a7210.52)"
            ),
            confidence=0.80,
            requires_licensed_review=_is_critical(rule_id),
        )
    ]


# ---------------------------------------------------------------------------
# ELEC-GFCI-001 — GFCI protection not specified in wet areas
# ---------------------------------------------------------------------------


def rule_elec_gfci_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when bath/kitchen entities exist but no GFCI code_note is present."""
    wet_rooms = _bath_or_kitchen_entities(ctx)
    if not wet_rooms:
        return []

    if _has_code_note_with_text(ctx, "gfci"):
        return []

    cit = _get_cit(ctx, "CEC-210.8-A")
    rule_id = "ELEC-GFCI-001"
    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[_entity_evidence(e.entity_id, e.bbox) for e in wet_rooms[:3]],
            citations=[cit],
            draft_comment_text=(
                "Provide a note on the electrical plans specifying that all receptacle "
                "outlets in bathrooms, kitchens (countertop receptacles), garages, and "
                "exterior locations shall have GFCI protection per CEC \u00a7210.8(A)."
            ),
            confidence=0.80,
            requires_licensed_review=_is_critical(rule_id),
        )
    ]


# ---------------------------------------------------------------------------
# ELEC-AFCI-001 — AFCI protection not specified in living areas
# ---------------------------------------------------------------------------


def rule_elec_afci_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when bedroom entities exist but no AFCI code_note is present."""
    bedroom_entities = ctx.bedroom_rooms
    if not bedroom_entities:
        return []

    has_afci = (
        _has_code_note_with_text(ctx, "afci")
        or _has_code_note_with_text(ctx, "arc fault")
    )
    if has_afci:
        return []

    cit = _get_cit(ctx, "CEC-210.12-A")
    rule_id = "ELEC-AFCI-001"
    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[
                _entity_evidence(e.entity_id, e.bbox) for e in bedroom_entities[:3]
            ],
            citations=[cit],
            draft_comment_text=(
                "Specify on the electrical plans that all 120V, 15- and 20-ampere "
                "branch circuits serving bedrooms, living areas, and all other "
                "specified rooms in dwelling units shall be protected by arc-fault "
                "circuit interrupter (AFCI) combination-type breakers per "
                "CEC \u00a7210.12(A)."
            ),
            confidence=0.80,
            requires_licensed_review=_is_critical(rule_id),
        )
    ]


# ---------------------------------------------------------------------------
# ELEC-EXT-LIGHTING-001 — Switched light at exterior doors not shown (BV #47)
# ---------------------------------------------------------------------------


def rule_elec_ext_lighting_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when exterior doors exist but no exterior lighting note is present.

    Triggers when:
    - There are exterior door entities, OR
    - There are 2+ floor-plan sheets (implies primary entrance + secondary exits exist)
    AND no code_note references exterior lighting or exterior door lighting.
    """
    ext_doors = _exterior_door_entities(ctx)
    floor_plan_sheets = [
        s for s in ctx.sheets
        if s.sheet_type and "floor" in s.sheet_type.lower()
    ]
    has_trigger = bool(ext_doors) or len(floor_plan_sheets) >= 2

    if not has_trigger:
        return []

    has_lighting_note = (
        _has_code_note_with_text(ctx, "exterior lighting")
        or _has_code_note_with_text(ctx, "exterior door")
        and _has_code_note_with_text(ctx, "light")
    )
    if has_lighting_note:
        return []

    cit = _get_cit(ctx, "CEC-210.70-A")
    rule_id = "ELEC-EXT-LIGHTING-001"

    evidence = [_entity_evidence(e.entity_id, e.bbox) for e in ext_doors[:3]]

    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=evidence,
            citations=[cit],
            draft_comment_text=(
                "A wall switch-controlled lighting outlet shall be installed at all "
                "exterior doors, including the primary entrance and any secondary "
                "entrances, per CEC \u00a7210.70(A). Show exterior lighting locations "
                "on the plans and specify fixture type and switching arrangement."
            ),
            confidence=0.80,
            requires_licensed_review=_is_critical(rule_id),
        )
    ]


# ---------------------------------------------------------------------------
# ELEC-ACCESSIBLE-CTRL-001 — Accessible controls (15-48" AFF) not specified (BV #46)
# ---------------------------------------------------------------------------


def rule_elec_accessible_ctrl_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when R-2.1 present but no accessible control height note found."""
    if not _has_r21_indicators(ctx):
        return []

    has_ctrl_note = (
        _has_code_note_with_text(ctx, "accessible controls")
        or (
            _has_code_note_with_text(ctx, "15")
            and _has_code_note_with_text(ctx, "48")
        )
    )
    if has_ctrl_note:
        return []

    cit = _get_cit(ctx, "CEC-210.8-A")
    rule_id = "ELEC-ACCESSIBLE-CTRL-001"
    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "In the Group R-2.1 accessible dwelling unit(s), specify that all "
                "light switches, electrical controls, and receptacle outlets shall be "
                "located between 15 inches and 48 inches above the finished floor per "
                "CBC \u00a711B-308 and CEC \u00a7210.52."
            ),
            confidence=0.80,
            requires_licensed_review=_is_critical(rule_id),
        )
    ]


# ---------------------------------------------------------------------------
# Rule registry — ordered, all deterministic
# ---------------------------------------------------------------------------

_RULES = [
    rule_elec_panel_loc_001,
    rule_elec_panel_amp_001,
    rule_elec_r21_compliance_001,
    rule_elec_gfci_001,
    rule_elec_afci_001,
    rule_elec_ext_lighting_001,
    rule_elec_accessible_ctrl_001,
]


# ---------------------------------------------------------------------------
# ElectricalReviewer — orchestrator
# ---------------------------------------------------------------------------


class ElectricalReviewer:
    """Deterministic electrical reviewer (CEC + CBC §107.2.1).

    Call ``run()`` once per submittal round.  It fetches all needed data from
    the database, runs every rule, and bulk-inserts findings.  The connection
    is not committed here — the caller owns the transaction.
    """

    DISCIPLINE = "electrical"

    def run(
        self,
        conn: psycopg.Connection,  # type: ignore[type-arg]
        *,
        project_id: str,
        submittal_id: str,
        review_round: int,
        database_url: str,
        extractor_versions_used: list[str] | None = None,
    ) -> list[str]:
        """Run all electrical rules and persist findings.

        Returns the list of created finding IDs.  The caller must commit.
        """
        ctx = load_arch_access_context(
            conn,
            project_id=project_id,
            submittal_id=submittal_id,
            review_round=review_round,
            database_url=database_url,
        )

        all_findings: list[FindingPayload] = []
        for rule_fn in _RULES:
            all_findings.extend(rule_fn(ctx))

        if not all_findings:
            return []

        return emit_findings_aa(
            conn,
            ctx,
            all_findings,
            self.DISCIPLINE,
            extractor_versions_used,
        )
