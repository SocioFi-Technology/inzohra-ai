"""Structural reviewer — Phase 05.

Deterministic rules:
  STR-HEADER-SIZING      Header sizes not specified on plans — BV #57 (critical path)
  STR-PLUMB-WALL-STUDS   Plumbing wall studs 2x6 not specified — BV #58 (critical path)
  STR-SHEAR-CALLOUT-001  Shear wall callout schedule not shown
  STR-HOLDOWN-001        Holdown schedule not on plans
  STR-FASTENER-001       Fastener schedule not specified
  STR-LOAD-PATH-001      Continuous load path documentation absent
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
    "STR-HEADER-SIZING":      "1.0.0",
    "STR-PLUMB-WALL-STUDS":   "1.0.0",
    "STR-SHEAR-CALLOUT-001":  "1.0.0",
    "STR-HOLDOWN-001":        "1.0.0",
    "STR-FASTENER-001":       "1.0.0",
    "STR-LOAD-PATH-001":      "1.0.0",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _project_ref() -> dict[str, Any]:
    return {"sheet_id": None, "detail": "Project-wide"}


def _sheet_ref(sheet_id: str | None, detail: str | None = None) -> dict[str, Any]:
    return {"sheet_id": sheet_id, "detail": detail}


def _entity_evidence(entity_id: str, bbox: list[float]) -> dict[str, Any]:
    return {"entity_id": entity_id, "bbox": bbox}


def _fallback_citation(canonical_id: str, code: str = "CBC") -> dict[str, Any]:
    """Return a stub citation when the KB lookup returns None.

    Never invents frozen text — always sets frozen_text=None with an explicit note.
    """
    section = canonical_id.split("-", 1)[1] if "-" in canonical_id else canonical_id
    return {
        "code": code,
        "section": section,
        "frozen_text": None,
        "note": "Section not yet in KB",
    }


def _get_cit(
    ctx: ArchAccessRuleContext,
    canonical_id: str,
    code: str = "CBC",
) -> dict[str, Any]:
    """Return a live citation or a clearly-flagged fallback — never hallucinated."""
    cit = get_citation_aa(ctx, canonical_id)
    return cit if cit is not None else _fallback_citation(canonical_id, code)


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


def _has_floor_plan_entities(ctx: ArchAccessRuleContext) -> bool:
    return bool(ctx.floor_plan_entities)


def _has_bathroom_entities(ctx: ArchAccessRuleContext) -> bool:
    """True if any floor-plan entity is a bathroom or plumbing-related room."""
    for e in ctx.floor_plan_entities:
        use = (e.room_use or "").lower()
        label = (e.room_label or "").lower()
        if "bath" in use or "toilet" in use or "plumb" in use:
            return True
        if "bath" in label or "toilet" in label or "plumb" in label:
            return True
    return False


def _first_structural_sheet(ctx: ArchAccessRuleContext) -> str | None:
    """Return sheet_id of the first structural-discipline sheet, or the first sheet."""
    for s in ctx.sheets:
        if s.discipline_letter and s.discipline_letter.upper() == "S":
            return s.sheet_id
    if ctx.sheets:
        return ctx.sheets[0].sheet_id
    return None


# ---------------------------------------------------------------------------
# STR-HEADER-SIZING — BV #57
# ---------------------------------------------------------------------------


def rule_str_header_sizing(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide + licensed-review finding when no header size schedule/callout found.

    Fires at most once per project.
    """
    if _has_code_note_keyword(ctx, "header size", "header schedule", "beam schedule"):
        return []

    rule_id = "STR-HEADER-SIZING"
    cit = _get_cit(ctx, "CBC-2308.4.2")
    sheet_id = _first_structural_sheet(ctx)

    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            requires_licensed_review=_is_critical(rule_id),
            sheet_reference=_sheet_ref(sheet_id, "Header sizes — exterior/bearing walls"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Specify new header sizes for all openings in exterior walls and "
                "bearing walls on the plans. Header sizes shall comply with CBC "
                "Table 2308.4.2.1 or be engineer-designed. Show header dimensions, "
                "span length, and number of jack studs required for each opening. "
                "(CBC \u00a7107.2, \u00a72308.4.2)"
            ),
            confidence=0.90,
        )
    ]


# ---------------------------------------------------------------------------
# STR-PLUMB-WALL-STUDS — BV #58
# ---------------------------------------------------------------------------


def rule_str_plumb_wall_studs(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide + licensed-review finding when plumbing walls lack 2x6 framing callout.

    Only fires when bathroom/plumbing entities exist.
    Fires at most once per project.
    """
    if not _has_bathroom_entities(ctx):
        return []

    if _has_code_note_keyword(ctx, "2x6", "2\u00d76", "plumbing wall"):
        return []

    rule_id = "STR-PLUMB-WALL-STUDS"
    cit = _get_cit(ctx, "CBC-2308.5.9")
    sheet_id = _first_structural_sheet(ctx)

    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            requires_licensed_review=_is_critical(rule_id),
            sheet_reference=_sheet_ref(sheet_id, "Plumbing wall stud size"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Specify 2x6 stud framing in all walls that contain plumbing drain "
                "pipes (DWV) to prevent excessive notching or boring of studs per "
                "CBC \u00a72308.5.9 and \u00a72308.5.10. Note on the framing plan "
                "which walls require 2x6 framing."
            ),
            confidence=0.90,
        )
    ]


# ---------------------------------------------------------------------------
# STR-SHEAR-CALLOUT-001
# ---------------------------------------------------------------------------


def rule_str_shear_callout_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide + licensed-review finding when floor-plan entities exist but no shear wall callout.

    Fires at most once per project.
    """
    if not _has_floor_plan_entities(ctx):
        return []

    if _has_code_note_keyword(ctx, "shear wall", "shearwall"):
        return []

    rule_id = "STR-SHEAR-CALLOUT-001"
    # Use CBC-2308.4.2 as the closest available citation for CBC Ch. 23/§2308
    cit = _get_cit(ctx, "CBC-2308.4.2")
    sheet_id = _first_structural_sheet(ctx)

    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            requires_licensed_review=_is_critical(rule_id),
            sheet_reference=_sheet_ref(sheet_id, "Shear wall schedule"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Provide a shear wall schedule or callout system on the floor plans "
                "identifying all shear walls, their assembly type, height, and "
                "hold-down anchoring. (CBC Ch. 23, \u00a72308)"
            ),
            confidence=0.85,
        )
    ]


# ---------------------------------------------------------------------------
# STR-HOLDOWN-001
# ---------------------------------------------------------------------------


def rule_str_holdown_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide + licensed-review finding when no holdown schedule/note is found.

    Fires at most once per project.
    """
    if _has_code_note_keyword(ctx, "holdown", "hold-down", "HDU", "PHD"):
        return []

    rule_id = "STR-HOLDOWN-001"
    # CBC §2308 — use 2308.4.2 as nearest KB entry; note applies to §2308 broadly
    cit = _get_cit(ctx, "CBC-2308.4.2")
    sheet_id = _first_structural_sheet(ctx)

    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            requires_licensed_review=_is_critical(rule_id),
            sheet_reference=_sheet_ref(sheet_id, "Holdown anchor schedule"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Provide a holdown/hold-down anchor schedule identifying the type, "
                "size, and location of all holdowns at shear wall ends. Holdowns "
                "shall be shown on the foundation plan and framing plan. "
                "(CBC \u00a72308)"
            ),
            confidence=0.85,
        )
    ]


# ---------------------------------------------------------------------------
# STR-FASTENER-001
# ---------------------------------------------------------------------------


def rule_str_fastener_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Clarify finding when no fastener/nailing schedule is noted on the plans.

    Fires at most once per project.
    """
    if _has_code_note_keyword(ctx, "fastener schedule", "nailing schedule"):
        return []

    rule_id = "STR-FASTENER-001"
    cit = _get_cit(ctx, "CBC-2308.12")
    sheet_id = _first_structural_sheet(ctx)

    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="clarify",
            requires_licensed_review=_is_critical(rule_id),
            sheet_reference=_sheet_ref(sheet_id, "Fastener/nailing schedule"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Provide a fastener/nailing schedule on the plans or in the general "
                "notes referencing the applicable CBC Table for minimum fastener "
                "requirements for structural panel sheathing. (CBC \u00a72308.12)"
            ),
            confidence=0.85,
        )
    ]


# ---------------------------------------------------------------------------
# STR-LOAD-PATH-001
# ---------------------------------------------------------------------------


def rule_str_load_path_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Clarify finding when no continuous load path documentation is present.

    Fires at most once per project.
    """
    if _has_code_note_keyword(ctx, "load path", "continuous load"):
        return []

    rule_id = "STR-LOAD-PATH-001"
    cit = _get_cit(ctx, "CBC-1604.4")
    sheet_id = _first_structural_sheet(ctx)

    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="clarify",
            requires_licensed_review=_is_critical(rule_id),
            sheet_reference=_sheet_ref(sheet_id, "Continuous load path"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Provide documentation of the continuous load path from roof to "
                "foundation on the structural drawings or general notes. Show all "
                "load transfer elements including blocking, straps, holdowns, and "
                "foundation anchors. (CBC \u00a71604.4)"
            ),
            confidence=0.85,
        )
    ]


# ---------------------------------------------------------------------------
# Rule registry — ordered, all deterministic
# ---------------------------------------------------------------------------

_RULES = [
    rule_str_header_sizing,
    rule_str_plumb_wall_studs,
    rule_str_shear_callout_001,
    rule_str_holdown_001,
    rule_str_fastener_001,
    rule_str_load_path_001,
]


# ---------------------------------------------------------------------------
# StructuralReviewer — orchestrator
# ---------------------------------------------------------------------------


class StructuralReviewer:
    """Deterministic structural reviewer (CBC Chapter 23 / §2308).

    Call ``run()`` once per submittal round.  It fetches all needed data from
    the database, runs every rule, and bulk-inserts findings.  The connection
    is not committed here — the caller owns the transaction.
    """

    DISCIPLINE = "structural"

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
        """Run all structural rules and persist findings.

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
