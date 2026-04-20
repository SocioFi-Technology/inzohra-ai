"""CalGreen reviewer — Phase 05.

Deterministic rules:
  CALG-WATER-FIXTURES-001  Water fixture flow rates not specified (T24P11 4.303.1)
  CALG-RECYCLE-001         Construction waste management plan not shown (T24P11 4.408.1)
  CALG-EV-READY-001        EV-ready parking space not shown (T24P11 5.410.1)
  CALG-INDOOR-AIR-001      Low-VOC finish specs not referenced (T24P11 4.504)
  CALG-MANDATORY-NOTE-001  CalGreen mandatory measures note absent

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
    "CALG-WATER-FIXTURES-001": "1.0.0",
    "CALG-RECYCLE-001":        "1.0.0",
    "CALG-EV-READY-001":       "1.0.0",
    "CALG-INDOOR-AIR-001":     "1.0.0",
    "CALG-MANDATORY-NOTE-001": "1.0.0",
}

# Canonical fallback citation used when specific CalGreen sections are not in KB
_CALG_FALLBACK_CANONICAL = "Title24P11-4.303.1"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sheet_ref(sheet_id: str | None, detail: str | None = None) -> dict[str, Any]:
    return {"sheet_id": sheet_id, "detail": detail}


def _entity_evidence(entity_id: str, bbox: list[float]) -> dict[str, Any]:
    return {"entity_id": entity_id, "bbox": bbox}


def _project_ref() -> dict[str, Any]:
    return {"sheet_id": None, "detail": "Project-wide"}


def _fallback_citation(canonical_id: str) -> dict[str, Any]:
    """Return a stub citation when the KB lookup returns None.

    Never invents text — frozen_text is explicitly None with a note.
    """
    # Derive code and section from canonical_id (e.g. "Title24P11-4.303.1")
    if "-" in canonical_id:
        idx = canonical_id.index("-")
        code = canonical_id[:idx]
        section = canonical_id[idx + 1:]
    else:
        code = "Title24P11"
        section = canonical_id
    return {
        "code": code,
        "section": section,
        "frozen_text": None,
        "note": "Section not in KB",
    }


def _get_cit(ctx: ArchAccessRuleContext, canonical_id: str) -> dict[str, Any]:
    """Return a live citation or a clearly-flagged fallback — never hallucinated."""
    cit = get_citation_aa(ctx, canonical_id)
    return cit if cit is not None else _fallback_citation(canonical_id)


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


def _has_garage_or_site(ctx: ArchAccessRuleContext) -> bool:
    """True if a site plan sheet or garage entity is present."""
    for s in ctx.sheets:
        if s.sheet_type and "site" in s.sheet_type.lower():
            return True
    for e in ctx.floor_plan_entities:
        use = (e.room_use or "").lower()
        label = (e.room_label or "").lower()
        if "garage" in use or "garage" in label or "parking" in use or "parking" in label:
            return True
    return False


# ---------------------------------------------------------------------------
# CALG-WATER-FIXTURES-001 — Water fixture flow rates not specified
# ---------------------------------------------------------------------------


def rule_calg_water_fixtures_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when bath/kitchen entities exist but no CalGreen flow-rate note is present."""
    wet_rooms = _bath_or_kitchen_entities(ctx)
    if not wet_rooms:
        return []

    has_flow_note = (
        _has_code_note_with_text(ctx, "calgreen")
        or _has_code_note_with_text(ctx, "gpf")
        or _has_code_note_with_text(ctx, "gpm")
        or _has_code_note_with_text(ctx, "flow rate")
    )
    if has_flow_note:
        return []

    cit = _get_cit(ctx, _CALG_FALLBACK_CANONICAL)
    rule_id = "CALG-WATER-FIXTURES-001"
    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[_entity_evidence(e.entity_id, e.bbox) for e in wet_rooms[:3]],
            citations=[cit],
            draft_comment_text=(
                "Provide a note on the plumbing plans specifying that all plumbing "
                "fixtures and fittings comply with California Green Building Standards "
                "Code \u00a74.303.1 flow rate requirements: toilets \u22641.28 gpf, "
                "showerheads \u22641.8 gpm, lavatory faucets \u22641.2 gpm, and "
                "kitchen faucets \u22641.8 gpm. "
                "(Title 24, Part 11 \u00a74.303.1)"
            ),
            confidence=0.80,
            requires_licensed_review=_is_critical(rule_id),
        )
    ]


# ---------------------------------------------------------------------------
# CALG-RECYCLE-001 — Construction waste management plan not shown
# ---------------------------------------------------------------------------


def rule_calg_recycle_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when no recycling/waste management note is present."""
    has_waste_note = (
        _has_code_note_with_text(ctx, "recycling")
        or _has_code_note_with_text(ctx, "waste management")
        or _has_code_note_with_text(ctx, "calgreen")
    )
    if has_waste_note:
        return []

    cit = _get_cit(ctx, _CALG_FALLBACK_CANONICAL)
    rule_id = "CALG-RECYCLE-001"
    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Provide a construction waste management note or plan on the drawings "
                "specifying diversion of at least 65% of construction and demolition "
                "debris from disposal in landfills per California Green Building "
                "Standards Code \u00a74.408.1. Identify the material recovery facility "
                "(MRF) to be used."
            ),
            confidence=0.80,
            requires_licensed_review=_is_critical(rule_id),
        )
    ]


# ---------------------------------------------------------------------------
# CALG-EV-READY-001 — EV-ready parking space not shown
# ---------------------------------------------------------------------------


def rule_calg_ev_ready_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Clarify finding when a site plan or garage exists but no EV-readiness note is present."""
    if not _has_garage_or_site(ctx):
        return []

    has_ev_note = (
        _has_code_note_with_text(ctx, "ev")
        or _has_code_note_with_text(ctx, "electric vehicle")
        or _has_code_note_with_text(ctx, "charging")
    )
    if has_ev_note:
        return []

    # Attempt specific section first; fall back to canonical fallback
    cit = get_citation_aa(ctx, "Title24P11-5.410.1")
    if cit is None:
        cit = _get_cit(ctx, _CALG_FALLBACK_CANONICAL)

    rule_id = "CALG-EV-READY-001"
    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="clarify",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Clarify compliance with California Green Building Standards Code "
                "\u00a75.410.1 for electric vehicle (EV) readiness. New residential "
                "construction with parking shall provide EV-capable spaces or "
                "EV-ready spaces as required. Show EV-ready conduit and panel "
                "capacity on the electrical plans."
            ),
            confidence=0.80,
            requires_licensed_review=_is_critical(rule_id),
        )
    ]


# ---------------------------------------------------------------------------
# CALG-INDOOR-AIR-001 — Low-VOC finish specs not referenced
# ---------------------------------------------------------------------------


def rule_calg_indoor_air_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Clarify finding when no low-VOC or CalGreen indoor air quality note is present."""
    has_voc_note = (
        _has_code_note_with_text(ctx, "voc")
        or _has_code_note_with_text(ctx, "low-voc")
        or _has_code_note_with_text(ctx, "calgreen indoor air")
    )
    if has_voc_note:
        return []

    cit = _get_cit(ctx, _CALG_FALLBACK_CANONICAL)
    rule_id = "CALG-INDOOR-AIR-001"
    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="clarify",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Specify on the plans that interior finishes comply with California "
                "Green Building Standards Code \u00a74.504 for low-VOC paints, "
                "coatings, adhesives, and sealants. Provide material specifications "
                "or a note referencing compliance with the applicable VOC limits."
            ),
            confidence=0.80,
            requires_licensed_review=_is_critical(rule_id),
        )
    ]


# ---------------------------------------------------------------------------
# CALG-MANDATORY-NOTE-001 — CalGreen mandatory measures note absent
# ---------------------------------------------------------------------------


def rule_calg_mandatory_note_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when no CalGreen mandatory measures note is present on the plans."""
    has_calgreen_note = (
        _has_code_note_with_text(ctx, "calgreen")
        or _has_code_note_with_text(ctx, "title 24 part 11")
        or _has_code_note_with_text(ctx, "mandatory measures")
    )
    if has_calgreen_note:
        return []

    cit = _get_cit(ctx, _CALG_FALLBACK_CANONICAL)
    rule_id = "CALG-MANDATORY-NOTE-001"
    return [
        FindingPayload(
            rule_id=rule_id,
            rule_version=_RULE_VERSIONS[rule_id],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Add a CalGreen mandatory measures summary note to the plans, "
                "referencing compliance with the applicable portions of California "
                "Green Building Standards Code (Title 24, Part 11) for this project "
                "type and occupancy classification."
            ),
            confidence=0.80,
            requires_licensed_review=_is_critical(rule_id),
        )
    ]


# ---------------------------------------------------------------------------
# Rule registry — ordered, all deterministic
# ---------------------------------------------------------------------------

_RULES = [
    rule_calg_water_fixtures_001,
    rule_calg_recycle_001,
    rule_calg_ev_ready_001,
    rule_calg_indoor_air_001,
    rule_calg_mandatory_note_001,
]


# ---------------------------------------------------------------------------
# CalGreenReviewer — orchestrator
# ---------------------------------------------------------------------------


class CalGreenReviewer:
    """Deterministic CalGreen reviewer (California Green Building Standards Code, Title 24 Part 11).

    Call ``run()`` once per submittal round.  It fetches all needed data from
    the database, runs every rule, and bulk-inserts findings.  The connection
    is not committed here — the caller owns the transaction.
    """

    DISCIPLINE = "calgreen"

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
        """Run all CalGreen rules and persist findings.

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
