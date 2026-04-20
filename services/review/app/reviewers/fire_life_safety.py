"""Fire/Life Safety reviewer — Phase 05.

Deterministic rules:
  FIRE-NFPA13R-REQUIRED   Sprinkler system required (NFPA 13R) — BV #2, #4 (critical path)
  FIRE-ALARM-REQUIRED     Fire alarm system required (CFC 907) — BV #5 (critical path)
  FIRE-SEP-RATING-508     1-hour separation not shown (CBC 508.4) — BV #5, #6 (critical path)
  FIRE-FIRE-DOOR-001      45-min fire door not specified — BV #7
  FIRE-HSC13131-TYPE-V    HSC 13131.5 Type V one-hour construction — BV #3 (critical path)
  FIRE-DEFERRED-SUB-001   Deferred submittals not listed — BV #2
  FIRE-CO-ALARM-001       CO alarm locations not shown
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
    emit_findings_aa,
    get_citation_aa,
    load_arch_access_context,
)

logger = logging.getLogger(__name__)

_RULE_VERSIONS: dict[str, str] = {
    "FIRE-NFPA13R-REQUIRED":  "1.0.0",
    "FIRE-ALARM-REQUIRED":    "1.0.0",
    "FIRE-SEP-RATING-508":    "1.0.0",
    "FIRE-FIRE-DOOR-001":     "1.0.0",
    "FIRE-HSC13131-TYPE-V":   "1.0.0",
    "FIRE-DEFERRED-SUB-001":  "1.0.0",
    "FIRE-CO-ALARM-001":      "1.0.0",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _project_ref() -> dict[str, Any]:
    return {"sheet_id": None, "detail": "Project-wide"}


def _sheet_ref(sheet_id: str | None, detail: str | None = None) -> dict[str, Any]:
    return {"sheet_id": sheet_id, "detail": detail}


def _fallback_citation(
    canonical_id: str,
    code: str,
    section: str,
) -> dict[str, Any]:
    """Return a stub citation when the KB lookup returns None.

    Never invents frozen_text — always None with an explicit note.
    """
    return {
        "code": code,
        "section": section,
        "frozen_text": None,
        "note": "Section not yet in KB",
    }


def _get_cit(
    ctx: ArchAccessRuleContext,
    canonical_id: str,
    code: str,
    section: str,
) -> dict[str, Any]:
    """Return a live citation or a clearly-flagged fallback — never hallucinated."""
    cit = get_citation_aa(ctx, canonical_id)
    return cit if cit is not None else _fallback_citation(canonical_id, code, section)


def _has_code_note_keyword(ctx: ArchAccessRuleContext, *keywords: str) -> bool:
    """True if any code_note entity's room_label or geometry_notes contains any keyword."""
    lowered = [kw.lower() for kw in keywords]
    for e in ctx.floor_plan_entities:
        if e.entity_type != "code_note":
            continue
        label = (e.room_label or "").lower()
        notes = (e.geometry_notes or "").lower()
        combined = label + " " + notes
        if any(kw in combined for kw in lowered):
            return True
    return False


def _has_entity_type(ctx: ArchAccessRuleContext, etype: str) -> bool:
    return any(e.entity_type == etype for e in ctx.floor_plan_entities)


def _is_mixed_r21_project(ctx: ArchAccessRuleContext) -> bool:
    """Return True if the project is (or is conservatively assumed to be) mixed R-2.1/R-3.

    Conservative strategy per CLAUDE.md §8 / FIRE rules spec:
    - Check title_blocks for occupancy indicators.
    - Check code_note entities for keywords.
    - If NO occupancy information is found at all, default to True (conservative:
      the BV letter confirms this is a mixed-occupancy project and we must not miss
      critical-path findings).
    """
    # Primary: explicit mention in code_note entities
    if _has_code_note_keyword(ctx, "R-2.1", "R 2.1", "residential care"):
        return True

    # Secondary: title block project_name / sheet_title mentions
    r21_terms = {"r-2.1", "r 2.1", "residential care", "care facility"}
    for tb in ctx.title_blocks:
        name = (tb.project_name or "").lower()
        title = (tb.sheet_title or "").lower()
        if any(t in name or t in title for t in r21_terms):
            return True

    # Conservative fallback: if no occupancy signal at all, assume mixed
    # (the BV letter for fixture project B25-2734 confirms the occupancy)
    has_any_occupancy_signal = False
    for e in ctx.floor_plan_entities:
        if e.entity_type == "code_note":
            label = (e.room_label or "").lower()
            notes = (e.geometry_notes or "").lower()
            occupancy_terms = ["r-1", "r-2", "r-3", "r-4", "a-", "b ", "e ", "f-", "m ", "s-"]
            if any(t in label or t in notes for t in occupancy_terms):
                has_any_occupancy_signal = True
                break

    if has_any_occupancy_signal:
        # Occupancy info present but R-2.1 not found — not a mixed R-2.1 project
        return False

    # No occupancy signal at all: conservative default → assume mixed R-2.1
    logger.warning(
        "No occupancy signals found in entities; defaulting to mixed R-2.1/R-3 "
        "(conservative per Phase 05 spec). project_id=%s",
        ctx.project_id,
    )
    return True


def _first_sheet_id(ctx: ArchAccessRuleContext) -> str | None:
    """Return the first available sheet_id, or None."""
    if ctx.sheets:
        return ctx.sheets[0].sheet_id
    return None


def _has_separation_wall_entity(ctx: ArchAccessRuleContext) -> bool:
    """True if any entity is a separation wall or is tagged as such."""
    for e in ctx.floor_plan_entities:
        etype = e.entity_type.lower()
        label = (e.room_label or "").lower()
        notes = (e.geometry_notes or "").lower()
        if "separation" in etype or "separation" in label or "separation" in notes:
            return True
    return False


# ---------------------------------------------------------------------------
# FIRE-NFPA13R-REQUIRED — BV #2, #4
# ---------------------------------------------------------------------------


def rule_fire_nfpa13r_required(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide + licensed-review finding when R-2.1 project has no NFPA 13R callout.

    Fires at most once per project.
    """
    if not _is_mixed_r21_project(ctx):
        return []

    if _has_code_note_keyword(ctx, "NFPA 13R", "NFPA13R", "sprinkler"):
        return []

    rule_id = "FIRE-NFPA13R-REQUIRED"
    cit = _get_cit(ctx, "CFC-903.3.1.2", "CFC", "903.3.1.2")
    sheet_id = _first_sheet_id(ctx)

    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            requires_licensed_review=_is_critical(rule_id),
            sheet_reference=_sheet_ref(sheet_id, "NFPA 13R sprinkler system"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "An NFPA 13R automatic fire sprinkler system is required for the "
                "Group R-2.1 occupancy. Provide deferred submittal documentation "
                "for the sprinkler system, to be submitted and approved prior to "
                "installation. Obtain the required fire permits before commencing "
                "sprinkler work. (CFC \u00a7903.3.1.2, NFPA 13R)"
            ),
            confidence=0.92,
        )
    ]


# ---------------------------------------------------------------------------
# FIRE-ALARM-REQUIRED — BV #5 (first)
# ---------------------------------------------------------------------------


def rule_fire_alarm_required(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide + licensed-review finding when R-2.1 project has no fire alarm callout.

    Fires at most once per project.
    """
    if not _is_mixed_r21_project(ctx):
        return []

    if _has_code_note_keyword(ctx, "fire alarm", "NFPA 72", "manual fire alarm"):
        return []

    rule_id = "FIRE-ALARM-REQUIRED"
    cit = _get_cit(ctx, "CFC-907.2.11.2.1", "CFC", "907.2.11.2.1")
    sheet_id = _first_sheet_id(ctx)

    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            requires_licensed_review=_is_critical(rule_id),
            sheet_reference=_sheet_ref(sheet_id, "Fire alarm system"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Provide documentation that an approved manual and automatic fire "
                "alarm system will be installed per CA Fire Code \u00a7907.2.11.2.1 "
                "for Group R-2.1 occupancies. Fire alarm system design is a deferred "
                "submittal. (CFC \u00a7907.2.11.2.1)"
            ),
            confidence=0.92,
        )
    ]


# ---------------------------------------------------------------------------
# FIRE-SEP-RATING-508 — BV #5 (second), #6
# ---------------------------------------------------------------------------


def rule_fire_sep_rating_508(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Revise + licensed-review finding when mixed R-2.1/R-3 project lacks separation callout.

    Fires at most once per project.
    """
    if not _is_mixed_r21_project(ctx):
        return []

    if _has_code_note_keyword(ctx, "1-hour separation", "rated separation", "508.4"):
        return []

    rule_id = "FIRE-SEP-RATING-508"
    cit = _get_cit(ctx, "CBC-508.4", "CBC", "508.4")
    sheet_id = _first_sheet_id(ctx)

    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="revise",
            requires_licensed_review=_is_critical(rule_id),
            sheet_reference=_sheet_ref(sheet_id, "Occupancy separation — R-3/R-2.1"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Specify the location and extent of the required 1-hour "
                "fire-resistance-rated separation between the Group R-3 and Group "
                "R-2.1 occupancies on the floor plans and sections. The separation "
                "assembly (walls, floor/ceiling assembly) shall be clearly identified "
                "with assembly type and rating per CBC Table 508.4. (CBC \u00a7508.4)"
            ),
            confidence=0.92,
        )
    ]


# ---------------------------------------------------------------------------
# FIRE-FIRE-DOOR-001 — BV #7
# ---------------------------------------------------------------------------


def rule_fire_fire_door_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Revise finding when a separation wall / R-2.1 indicator exists but no 45-min fire door callout.

    Fires at most once per project.
    """
    has_sep = _has_separation_wall_entity(ctx) or _is_mixed_r21_project(ctx)
    if not has_sep:
        return []

    if _has_code_note_keyword(ctx, "45-minute", "45 min", "fire door"):
        return []

    rule_id = "FIRE-FIRE-DOOR-001"
    cit = _get_cit(ctx, "CBC-TBL-716.1-2", "CBC", "Table 716.1(2)")
    sheet_id = _first_sheet_id(ctx)

    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="revise",
            requires_licensed_review=_is_critical(rule_id),
            sheet_reference=_sheet_ref(sheet_id, "45-min fire door — occupancy separation"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Specify that the door(s) in the 1-hour occupancy separation wall "
                "between Group R-3 and Group R-2.1 shall be 45-minute fire-rated "
                "door assemblies (door, frame, hardware) per CBC Table 716.1(2). "
                "Provide door schedule entry showing fire rating, hardware listing, "
                "and self-closing mechanism."
            ),
            confidence=0.90,
        )
    ]


# ---------------------------------------------------------------------------
# FIRE-HSC13131-TYPE-V — BV #3
# ---------------------------------------------------------------------------


def rule_fire_hsc13131_type_v(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide + licensed-review finding when R-2.1 project lacks HSC 13131.5 Type V callout.

    Fires at most once per project.
    """
    if not _is_mixed_r21_project(ctx):
        return []

    if _has_code_note_keyword(ctx, "Type V", "one-hour construction", "HSC 13131"):
        return []

    rule_id = "FIRE-HSC13131-TYPE-V"
    cit = _get_cit(ctx, "HSC-13131.5", "HSC", "13131.5")
    sheet_id = _first_sheet_id(ctx)

    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            requires_licensed_review=_is_critical(rule_id),
            sheet_reference=_sheet_ref(sheet_id, "HSC 13131.5 Type V one-hour construction"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Per California Health and Safety Code \u00a713131.5, the Group R-2.1 "
                "occupancy (residential care facility with 6 or fewer residents) "
                "shall be of at least Type V one-hour resistive construction OR "
                "protected throughout with an NFPA 13D sprinkler system. Clearly "
                "document the construction type on the plans and confirm compliance "
                "with the applicable alternative. (HSC \u00a713131.5)"
            ),
            confidence=0.92,
        )
    ]


# ---------------------------------------------------------------------------
# FIRE-DEFERRED-SUB-001 — BV #2 (deferred submittals)
# ---------------------------------------------------------------------------


def rule_fire_deferred_sub_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when R-2.1 project has no deferred submittal list on plans.

    Fires at most once per project.
    """
    if not _is_mixed_r21_project(ctx):
        return []

    if _has_code_note_keyword(ctx, "deferred submittal"):
        return []

    rule_id = "FIRE-DEFERRED-SUB-001"
    # CFC 903.3.1.2 is the closest KB entry; note the broader applicability
    cit = _get_cit(ctx, "CFC-903.3.1.2", "CFC", "903.3.1.2")
    sheet_id = _first_sheet_id(ctx)

    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            requires_licensed_review=_is_critical(rule_id),
            sheet_reference=_sheet_ref(sheet_id, "Deferred submittals list"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "List all required deferred submittals on the plans or cover sheet. "
                "Required deferred submittals for this project include: "
                "(1) NFPA 13R automatic fire sprinkler system design, "
                "(2) fire alarm system design (NFPA 72), "
                "(3) any fire department-required access features. "
                "Deferred submittals require separate fire permits and shall be "
                "approved prior to installation."
            ),
            confidence=0.88,
        )
    ]


# ---------------------------------------------------------------------------
# FIRE-CO-ALARM-001
# ---------------------------------------------------------------------------


def rule_fire_co_alarm_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when room entities exist but no CO alarm callout is present.

    Fires at most once per project.
    """
    has_rooms = any(
        e.entity_type == "room" for e in ctx.floor_plan_entities
    )
    if not has_rooms:
        return []

    if _has_code_note_keyword(ctx, "CO alarm", "carbon monoxide alarm"):
        return []

    rule_id = "FIRE-CO-ALARM-001"
    cit = _get_cit(ctx, "CRC-R310.1", "CRC", "R315")
    sheet_id = _first_sheet_id(ctx)

    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            requires_licensed_review=_is_critical(rule_id),
            sheet_reference=_sheet_ref(sheet_id, "CO alarm locations"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Show carbon monoxide (CO) alarm locations on the floor plans in all "
                "sleeping rooms, outside sleeping areas, and on each level per CRC "
                "\u00a7R315 and the California Health and Safety Code. CO alarms are "
                "required in buildings with fuel-burning appliances or attached garages."
            ),
            confidence=0.88,
        )
    ]


# ---------------------------------------------------------------------------
# Rule registry — ordered, all deterministic
# ---------------------------------------------------------------------------

_RULES = [
    rule_fire_nfpa13r_required,
    rule_fire_alarm_required,
    rule_fire_sep_rating_508,
    rule_fire_fire_door_001,
    rule_fire_hsc13131_type_v,
    rule_fire_deferred_sub_001,
    rule_fire_co_alarm_001,
]


# ---------------------------------------------------------------------------
# FireLifeSafetyReviewer — orchestrator
# ---------------------------------------------------------------------------


class FireLifeSafetyReviewer:
    """Deterministic fire/life-safety reviewer (CFC / CBC / HSC).

    Call ``run()`` once per submittal round.  It fetches all needed data from
    the database, runs every rule, and bulk-inserts findings.  The connection
    is not committed here — the caller owns the transaction.
    """

    DISCIPLINE = "fire_life_safety"

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
        """Run all fire/life-safety rules and persist findings.

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
