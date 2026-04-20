"""Mechanical reviewer — Phase 05.

Deterministic rules:
  MECH-ATTIC-VENT-001    Attic ventilation calc not provided (CBC 1202.2) — BV #19
  MECH-ATTIC-SCREEN-001  Attic vent protection not specified — BV #20
  MECH-ATTIC-CLEAR-001   Attic insulation clearance note absent — BV #21
  MECH-HVAC-DEDICATED    Dedicated HVAC for R-2.1 not shown — BV #48 (critical path)
  MECH-BATH-EXHAUST-001  Bath exhaust not shown/ducted to exterior — BV #49
  MECH-KITCHEN-HOOD-001  Kitchen exhaust/hood not specified — BV #50
  MECH-DUCT-INSUL-001    Duct insulation not specified — general (CEnC §150.0(m))

No LLM residue pass — mechanical rules are deterministic absence checks.
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
    "MECH-ATTIC-VENT-001":   "1.0.0",
    "MECH-ATTIC-SCREEN-001": "1.0.0",
    "MECH-ATTIC-CLEAR-001":  "1.0.0",
    "MECH-HVAC-DEDICATED":   "1.0.0",
    "MECH-BATH-EXHAUST-001": "1.0.0",
    "MECH-KITCHEN-HOOD-001": "1.0.0",
    "MECH-DUCT-INSUL-001":   "1.0.0",
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


def _fallback_citation(
    code: str,
    section: str,
    note: str = "Section not in KB — seed required",
) -> dict[str, Any]:
    """Return a stub citation when KB lookup returns None.

    Never invents frozen_text — it is explicitly None with a note.
    """
    return {
        "code": code,
        "section": section,
        "frozen_text": None,
        "note": note,
    }


def _get_cit(
    ctx: ArchAccessRuleContext,
    canonical_id: str,
    fallback_code: str,
    fallback_section: str,
) -> dict[str, Any]:
    """Return a live citation or a clearly-flagged fallback — never hallucinated."""
    cit = get_citation_aa(ctx, canonical_id)
    return cit if cit is not None else _fallback_citation(fallback_code, fallback_section)


def _has_code_note_with_text(ctx: ArchAccessRuleContext, keyword: str) -> bool:
    """True if any code_note entity has room_label or geometry_notes containing keyword."""
    kw = keyword.lower()
    for e in ctx.floor_plan_entities:
        if e.entity_type != "code_note":
            continue
        label = (e.room_label or "").lower()
        notes = (e.geometry_notes or "").lower()
        if kw in label or kw in notes:
            return True
    return False


def _has_any_entity_text(ctx: ArchAccessRuleContext, keyword: str) -> bool:
    """True if any floor_plan_entity (any type) has room_label or geometry_notes containing keyword."""
    kw = keyword.lower()
    for e in ctx.floor_plan_entities:
        label = (e.room_label or "").lower()
        notes = (e.geometry_notes or "").lower()
        tag = (e.tag or "").lower()
        if kw in label or kw in notes or kw in tag:
            return True
    return False


def _has_room_use(ctx: ArchAccessRuleContext, *uses: str) -> bool:
    """True if any floor_plan_entity has room_use or room_label matching any of the given strings."""
    for e in ctx.floor_plan_entities:
        use = (e.room_use or "").lower()
        label = (e.room_label or "").lower()
        for u in uses:
            u_lower = u.lower()
            if u_lower in use or u_lower in label:
                return True
    return False


def _first_sheet_for_use(ctx: ArchAccessRuleContext, *uses: str) -> str | None:
    """Return the sheet_id of the first entity matching any of the given room uses/labels."""
    for e in ctx.floor_plan_entities:
        use = (e.room_use or "").lower()
        label = (e.room_label or "").lower()
        for u in uses:
            u_lower = u.lower()
            if u_lower in use or u_lower in label:
                return e.sheet_id
    return None


def _is_mixed_occupancy(ctx: ArchAccessRuleContext) -> bool:
    """True if title blocks or entities indicate both R-2.1 and R-3 occupancies."""
    has_r21 = False
    has_r3 = False
    for tb in ctx.title_blocks:
        title = (tb.sheet_title or "").lower()
        project_name = (tb.project_name or "").lower()
        combined = title + " " + project_name
        if "r-2.1" in combined or "r2.1" in combined:
            has_r21 = True
        if "r-3" in combined or "r3" in combined:
            has_r3 = True
    # Also search entities for occupancy markers
    if not (has_r21 and has_r3):
        for e in ctx.floor_plan_entities:
            label = (e.room_label or "").lower()
            notes = (e.geometry_notes or "").lower()
            combined = label + " " + notes
            if "r-2.1" in combined or "r2.1" in combined:
                has_r21 = True
            if "r-3" in combined or "r3" in combined:
                has_r3 = True
    return has_r21 and has_r3


# ---------------------------------------------------------------------------
# MECH-ATTIC-VENT-001 — Attic ventilation calculations not provided
# ---------------------------------------------------------------------------


def rule_mech_attic_vent_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when no code_note entity mentions attic vent calculations.

    Fires at most once per project. (BV #19)
    """
    if _has_code_note_with_text(ctx, "attic vent"):
        return []

    cit = _get_cit(ctx, "CBC-1202.2", "CBC", "1202.2")
    return [
        FindingPayload(
            rule_id="MECH-ATTIC-VENT-001",
            rule_version=_RULE_VERSIONS["MECH-ATTIC-VENT-001"],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Provide attic ventilation calculations on the drawings. Specify the "
                "total attic area, the required ventilation area (1/150 or 1/300 per "
                "CBC \u00a71202.2), and the actual vent area provided with product "
                "specifications. (CBC \u00a71202.2)"
            ),
            confidence=0.82,
            requires_licensed_review=_is_critical("MECH-ATTIC-VENT-001"),
        )
    ]


# ---------------------------------------------------------------------------
# MECH-ATTIC-SCREEN-001 — Attic vent protection not specified
# ---------------------------------------------------------------------------


def rule_mech_attic_screen_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when no entity mentions corrosion-resistant vent screening.

    Fires at most once per project. (BV #20)
    """
    if _has_code_note_with_text(ctx, "vent screen") or _has_code_note_with_text(
        ctx, "corrosion-resistant"
    ):
        return []

    cit = _get_cit(ctx, "CBC-1202.2", "CBC", "1202.2")
    return [
        FindingPayload(
            rule_id="MECH-ATTIC-SCREEN-001",
            rule_version=_RULE_VERSIONS["MECH-ATTIC-SCREEN-001"],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Specify that attic vents are protected with corrosion-resistant "
                "screening with openings between 1/16 inch and 1/4 inch per "
                "CBC \u00a71202.2."
            ),
            confidence=0.82,
            requires_licensed_review=_is_critical("MECH-ATTIC-SCREEN-001"),
        )
    ]


# ---------------------------------------------------------------------------
# MECH-ATTIC-CLEAR-001 — Attic insulation clearance note absent
# ---------------------------------------------------------------------------


def rule_mech_attic_clear_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when no code_note mentions 1-inch clearance or attic insulation clearance.

    Fires at most once per project. (BV #21)
    """
    if _has_code_note_with_text(ctx, "1 inch clearance") or _has_code_note_with_text(
        ctx, "attic insulation clearance"
    ):
        return []

    cit = _get_cit(ctx, "CBC-1202.2", "CBC", "1202.2")
    return [
        FindingPayload(
            rule_id="MECH-ATTIC-CLEAR-001",
            rule_version=_RULE_VERSIONS["MECH-ATTIC-CLEAR-001"],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Provide a note on the plans specifying that a minimum 1-inch "
                "clearance is maintained between attic insulation and the roof "
                "sheathing at eave and cornice vents per CBC \u00a71202.2.3."
            ),
            confidence=0.82,
            requires_licensed_review=_is_critical("MECH-ATTIC-CLEAR-001"),
        )
    ]


# ---------------------------------------------------------------------------
# MECH-HVAC-DEDICATED — Dedicated HVAC for R-2.1 not shown
# ---------------------------------------------------------------------------


def rule_mech_hvac_dedicated(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Revise finding (critical path) when mixed R-2.1/R-3 project lacks dedicated HVAC note.

    Fires at most once per project. (BV #48)
    """
    if not _is_mixed_occupancy(ctx):
        return []

    # Check for dedicated HVAC code_note
    if _has_code_note_with_text(ctx, "dedicated") and (
        _has_code_note_with_text(ctx, "hvac")
        or _has_code_note_with_text(ctx, "heating")
        or _has_code_note_with_text(ctx, "mechanical")
    ):
        return []

    cit = _get_cit(ctx, "CMC-403.1", "CMC", "403.1")
    return [
        FindingPayload(
            rule_id="MECH-HVAC-DEDICATED",
            rule_version=_RULE_VERSIONS["MECH-HVAC-DEDICATED"],
            severity="revise",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "The plans show both Group R-2.1 and Group R-3 occupancies. Provide "
                "a dedicated heating and ventilation system for the R-2.1 occupancy, "
                "separate and independent from the R-3 system. Show the location and "
                "type of mechanical equipment on the plans. (CMC \u00a7403.1)"
            ),
            confidence=0.82,
            requires_licensed_review=_is_critical("MECH-HVAC-DEDICATED"),
        )
    ]


# ---------------------------------------------------------------------------
# MECH-BATH-EXHAUST-001 — Bath exhaust not shown/ducted to exterior
# ---------------------------------------------------------------------------


def rule_mech_bath_exhaust_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when bathrooms exist but no exhaust fan code_note is present.

    Fires at most once per project. (BV #49)
    """
    has_bath = _has_room_use(ctx, "bath", "bathroom", "toilet")
    if not has_bath:
        return []

    if _has_code_note_with_text(ctx, "exhaust fan") or _has_code_note_with_text(
        ctx, "bath exhaust"
    ):
        return []

    cit = _get_cit(ctx, "CMC-504.1", "CMC", "504.1")
    first_sheet = _first_sheet_for_use(ctx, "bath", "bathroom", "toilet")
    return [
        FindingPayload(
            rule_id="MECH-BATH-EXHAUST-001",
            rule_version=_RULE_VERSIONS["MECH-BATH-EXHAUST-001"],
            severity="provide",
            sheet_reference=_sheet_ref(first_sheet, "Bathroom exhaust ventilation"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Each bathroom containing a bathtub, shower, or spa shall have a "
                "mechanical exhaust ventilation fan rated at minimum 50 cfm "
                "(intermittent) or 20 cfm (continuous), ducted to the exterior of "
                "the building. Show the exhaust fan on plans and specify the duct "
                "termination location. (CMC \u00a7504.1)"
            ),
            confidence=0.82,
            requires_licensed_review=_is_critical("MECH-BATH-EXHAUST-001"),
        )
    ]


# ---------------------------------------------------------------------------
# MECH-KITCHEN-HOOD-001 — Kitchen exhaust/hood not specified
# ---------------------------------------------------------------------------


def rule_mech_kitchen_hood_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when kitchens exist but no kitchen exhaust code_note is present.

    Fires at most once per project. (BV #50)
    """
    has_kitchen = _has_room_use(ctx, "kitchen")
    if not has_kitchen:
        return []

    if _has_code_note_with_text(ctx, "kitchen exhaust") or _has_code_note_with_text(
        ctx, "range hood"
    ):
        return []

    cit = _get_cit(ctx, "CMC-505.1", "CMC", "505.1")
    first_sheet = _first_sheet_for_use(ctx, "kitchen")
    return [
        FindingPayload(
            rule_id="MECH-KITCHEN-HOOD-001",
            rule_version=_RULE_VERSIONS["MECH-KITCHEN-HOOD-001"],
            severity="provide",
            sheet_reference=_sheet_ref(first_sheet, "Kitchen exhaust / range hood"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Specify the kitchen exhaust/range hood on the plans. The hood shall "
                "discharge to the outdoors (not into the attic), and the minimum "
                "exhaust rate shall comply with CEnC Table 150.0-G. Show duct routing "
                "and termination. (CMC \u00a7505.1, CEnC \u00a7150.0(g))"
            ),
            confidence=0.82,
            requires_licensed_review=_is_critical("MECH-KITCHEN-HOOD-001"),
        )
    ]


# ---------------------------------------------------------------------------
# MECH-DUCT-INSUL-001 — Duct insulation not specified
# ---------------------------------------------------------------------------


def rule_mech_duct_insul_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when no code_note mentions duct insulation values.

    Fires at most once per project.
    """
    if _has_code_note_with_text(ctx, "duct insulation") or _has_code_note_with_text(
        ctx, "r-6"
    ):
        return []

    cit = _get_cit(ctx, "CEnC-150.0-m1", "CEnC", "150.0(m)")
    return [
        FindingPayload(
            rule_id="MECH-DUCT-INSUL-001",
            rule_version=_RULE_VERSIONS["MECH-DUCT-INSUL-001"],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Specify duct insulation values on the plans. All supply and return "
                "ducts outside conditioned space shall be insulated to a minimum of "
                "R-6 per CEnC \u00a7150.0(m)."
            ),
            confidence=0.82,
            requires_licensed_review=_is_critical("MECH-DUCT-INSUL-001"),
        )
    ]


# ---------------------------------------------------------------------------
# Rule registry — ordered, all deterministic
# ---------------------------------------------------------------------------

_RULES = [
    rule_mech_attic_vent_001,
    rule_mech_attic_screen_001,
    rule_mech_attic_clear_001,
    rule_mech_hvac_dedicated,
    rule_mech_bath_exhaust_001,
    rule_mech_kitchen_hood_001,
    rule_mech_duct_insul_001,
]


# ---------------------------------------------------------------------------
# MechanicalReviewer — orchestrator
# ---------------------------------------------------------------------------


class MechanicalReviewer:
    """Deterministic mechanical reviewer (CMC + CBC Chapter 12 + CEnC).

    Call ``run()`` once per submittal round.  It fetches all needed data from
    the database, runs every rule, and bulk-inserts findings.  The connection
    is not committed here — the caller owns the transaction.
    """

    DISCIPLINE = "mechanical"

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
        """Run all mechanical rules and persist findings.

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
            try:
                all_findings.extend(rule_fn(ctx))
            except Exception:
                logger.exception("Mechanical rule %s failed", rule_fn.__name__)

        if not all_findings:
            return []

        return emit_findings_aa(
            conn,
            ctx,
            all_findings,
            self.DISCIPLINE,
            extractor_versions_used,
        )
