"""Plumbing reviewer — Phase 05.

Deterministic rules:
  PLMB-UTILITY-SITE-001  Utility connection lines not on site plan — BV #51
  PLMB-FIXTURE-COUNT-001 Fixture count not verified vs occupancy — BV #52
  PLMB-WH-LOCATION-001   Water heater location not specified (R-3) — BV #53
  PLMB-SHOWER-CTRL-001   Shower hot/cold controls not shown — BV #54
  PLMB-WH-DEDICATED-001  No dedicated water heater for R-2.1 — BV #55
  PLMB-BACKFLOW-001      Backflow prevention not noted — general
  PLMB-WH-ELEVATION-001  Water heater in garage not elevated 18" — general

No LLM residue pass — plumbing rules are deterministic absence checks.
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
    "PLMB-UTILITY-SITE-001":  "1.0.0",
    "PLMB-FIXTURE-COUNT-001": "1.0.0",
    "PLMB-WH-LOCATION-001":   "1.0.0",
    "PLMB-SHOWER-CTRL-001":   "1.0.0",
    "PLMB-WH-DEDICATED-001":  "1.0.0",
    "PLMB-BACKFLOW-001":      "1.0.0",
    "PLMB-WH-ELEVATION-001":  "1.0.0",
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
    """True if any floor_plan_entity (any type) has room_label, geometry_notes, or tag containing keyword."""
    kw = keyword.lower()
    for e in ctx.floor_plan_entities:
        label = (e.room_label or "").lower()
        notes = (e.geometry_notes or "").lower()
        tag = (e.tag or "").lower()
        if kw in label or kw in notes or kw in tag:
            return True
    return False


def _has_measurement_type(ctx: ArchAccessRuleContext, mtype: str) -> bool:
    return any(m.type == mtype for m in ctx.measurements)


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


def _site_sheets(ctx: ArchAccessRuleContext) -> list[Any]:
    """Return all SheetRows whose sheet_type contains 'site'."""
    return [
        s for s in ctx.sheets
        if s.sheet_type and "site" in s.sheet_type.lower()
    ]


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
# PLMB-UTILITY-SITE-001 — Utility connection lines not on site plan
# ---------------------------------------------------------------------------


def rule_plmb_utility_site_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when a site plan sheet exists but no utility note is present.

    Fires at most once per project. (BV #51)
    """
    sites = _site_sheets(ctx)
    if not sites:
        return []

    if _has_code_note_with_text(ctx, "utility") or _has_code_note_with_text(
        ctx, "service connection"
    ):
        return []

    site_sheet_id = sites[0].sheet_id
    cit = _get_cit(ctx, "CPC-501.0", "CPC", "501.0")
    return [
        FindingPayload(
            rule_id="PLMB-UTILITY-SITE-001",
            rule_version=_RULE_VERSIONS["PLMB-UTILITY-SITE-001"],
            severity="provide",
            sheet_reference=_sheet_ref(site_sheet_id, "Utility service connections"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "On the site plan, show all utility service connection lines including "
                "water service, sewer lateral, cleanouts, electrical service, and gas "
                "service lines. Specify pipe sizes, materials, and connection point to "
                "the public main. (CBC \u00a7107.2.1)"
            ),
            confidence=0.82,
            requires_licensed_review=_is_critical("PLMB-UTILITY-SITE-001"),
        )
    ]


# ---------------------------------------------------------------------------
# PLMB-FIXTURE-COUNT-001 — Fixture count not verified vs occupancy
# ---------------------------------------------------------------------------


def rule_plmb_fixture_count_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when bath/kitchen entities exist but no fixture count note is present.

    Fires at most once per project. (BV #52)
    """
    has_bath_or_kitchen = _has_room_use(
        ctx, "bath", "bathroom", "toilet", "kitchen"
    )
    if not has_bath_or_kitchen:
        return []

    if _has_code_note_with_text(ctx, "fixture count") or _has_code_note_with_text(
        ctx, "cpc table 422"
    ):
        return []

    cit = _get_cit(ctx, "CPC-422.1", "CPC", "422.1")
    return [
        FindingPayload(
            rule_id="PLMB-FIXTURE-COUNT-001",
            rule_version=_RULE_VERSIONS["PLMB-FIXTURE-COUNT-001"],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Provide a plumbing fixture count schedule on the drawings comparing "
                "the required number of fixtures per CPC Table 422.1 to the actual "
                "number provided. Confirm fixture counts are adequate for the proposed "
                "occupant load of both R-2.1 and R-3 occupancies."
            ),
            confidence=0.82,
            requires_licensed_review=_is_critical("PLMB-FIXTURE-COUNT-001"),
        )
    ]


# ---------------------------------------------------------------------------
# PLMB-WH-LOCATION-001 — Water heater location not specified (R-3)
# ---------------------------------------------------------------------------


def rule_plmb_wh_location_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Clarify finding when no entity or note mentions water heater in context of R-3.

    Fires at most once per project. (BV #53)
    """
    # Check if water heater is mentioned alongside R-3
    wh_text = _has_any_entity_text(ctx, "water heater")
    r3_text = _has_any_entity_text(ctx, "r-3") or _has_any_entity_text(ctx, "r3")

    # Fire if neither is mentioned, or if WH is mentioned but R-3 context is absent
    if wh_text and r3_text:
        return []

    cit = _get_cit(ctx, "CPC-501.2", "CPC", "501.2")
    return [
        FindingPayload(
            rule_id="PLMB-WH-LOCATION-001",
            rule_version=_RULE_VERSIONS["PLMB-WH-LOCATION-001"],
            severity="clarify",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Specify the water heater serving the R-3 occupancy: type, location, "
                "and venting arrangement. If the existing water heater was relocated "
                "from the garage, clarify the new location, fuel type, and compliance "
                "with minimum elevation requirements if in a new garage location. "
                "(CPC \u00a7501.2)"
            ),
            confidence=0.82,
            requires_licensed_review=_is_critical("PLMB-WH-LOCATION-001"),
        )
    ]


# ---------------------------------------------------------------------------
# PLMB-SHOWER-CTRL-001 — Shower hot/cold controls not shown
# ---------------------------------------------------------------------------


def rule_plmb_shower_ctrl_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when bathrooms exist but no shower control measurement or note.

    Fires at most once per project. (BV #54)
    """
    has_bath = _has_room_use(ctx, "bath", "bathroom", "shower")
    if not has_bath:
        return []

    if _has_measurement_type(ctx, "shower_control_temp"):
        return []
    if _has_code_note_with_text(ctx, "shower control") or _has_code_note_with_text(
        ctx, "thermostatic"
    ):
        return []

    cit = _get_cit(ctx, "CPC-408.3", "CPC", "408.3")
    first_sheet = _first_sheet_for_use(ctx, "bath", "bathroom", "shower")
    return [
        FindingPayload(
            rule_id="PLMB-SHOWER-CTRL-001",
            rule_version=_RULE_VERSIONS["PLMB-SHOWER-CTRL-001"],
            severity="provide",
            sheet_reference=_sheet_ref(first_sheet, "Shower control valve detail"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Detail the shower control valve in the accessible shower, showing a "
                "thermostatic or pressure-balancing mixing valve that limits water "
                "temperature to 120\u00b0F maximum. Show hot and cold water supply "
                "connections with accessible controls per CPC \u00a7408.3 and "
                "CBC \u00a711B-608.5.2."
            ),
            confidence=0.82,
            requires_licensed_review=_is_critical("PLMB-SHOWER-CTRL-001"),
        )
    ]


# ---------------------------------------------------------------------------
# PLMB-WH-DEDICATED-001 — No dedicated water heater for R-2.1
# ---------------------------------------------------------------------------


def rule_plmb_wh_dedicated_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Revise finding when mixed-occupancy project lacks a dedicated water heater note for R-2.1.

    Fires at most once per project. (BV #55)
    """
    if not _is_mixed_occupancy(ctx):
        return []

    if _has_code_note_with_text(
        ctx, "dedicated water heater"
    ) or _has_code_note_with_text(ctx, "separate water heater"):
        return []

    cit = _get_cit(ctx, "CPC-501.0", "CPC", "501.0")
    return [
        FindingPayload(
            rule_id="PLMB-WH-DEDICATED-001",
            rule_version=_RULE_VERSIONS["PLMB-WH-DEDICATED-001"],
            severity="revise",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Provide a separate, dedicated water heater for the Group R-2.1 "
                "occupancy, independent from the R-3 water heater. Each occupancy "
                "shall have its own water heating system. Specify the type, size (in "
                "gallons), recovery rate, and location of the R-2.1 water heater. "
                "(CPC \u00a7501.0)"
            ),
            confidence=0.82,
            requires_licensed_review=_is_critical("PLMB-WH-DEDICATED-001"),
        )
    ]


# ---------------------------------------------------------------------------
# PLMB-BACKFLOW-001 — Backflow prevention not noted
# ---------------------------------------------------------------------------


def rule_plmb_backflow_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Clarify finding when kitchen/laundry entities exist but no backflow prevention note.

    Fires at most once per project.
    """
    has_kitchen_or_laundry = _has_room_use(
        ctx, "kitchen", "laundry", "utility"
    )
    if not has_kitchen_or_laundry:
        return []

    if (
        _has_code_note_with_text(ctx, "backflow")
        or _has_code_note_with_text(ctx, "rpz")
        or _has_code_note_with_text(ctx, "air gap")
    ):
        return []

    cit = _get_cit(ctx, "CPC-710.0", "CPC", "710.0")
    return [
        FindingPayload(
            rule_id="PLMB-BACKFLOW-001",
            rule_version=_RULE_VERSIONS["PLMB-BACKFLOW-001"],
            severity="clarify",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Provide backflow prevention note on the drawings. Specify the type "
                "of backflow prevention device (air gap, RPZ valve, or double check "
                "valve) at all connections to the potable water supply that could be "
                "subject to contamination. (CPC \u00a7710.0)"
            ),
            confidence=0.82,
            requires_licensed_review=_is_critical("PLMB-BACKFLOW-001"),
        )
    ]


# ---------------------------------------------------------------------------
# PLMB-WH-ELEVATION-001 — Water heater in garage not elevated 18 inches
# ---------------------------------------------------------------------------


def rule_plmb_wh_elevation_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Clarify finding when garage entity exists but no 18-inch elevation note for water heater.

    Fires at most once per project.
    """
    has_garage = _has_room_use(ctx, "garage")
    # Also check geometry_notes for any entity mentioning garage
    if not has_garage:
        has_garage = _has_any_entity_text(ctx, "garage")
    if not has_garage:
        return []

    if _has_code_note_with_text(ctx, "18 inch"):
        return []

    cit = _get_cit(ctx, "CPC-501.2", "CPC", "501.2")
    first_sheet = _first_sheet_for_use(ctx, "garage")
    return [
        FindingPayload(
            rule_id="PLMB-WH-ELEVATION-001",
            rule_version=_RULE_VERSIONS["PLMB-WH-ELEVATION-001"],
            severity="clarify",
            sheet_reference=_sheet_ref(first_sheet, "Water heater garage elevation"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "If the water heater is installed in the garage, provide a note "
                "specifying that the ignition source of the water heater is elevated "
                "a minimum of 18 inches above the garage floor per CPC \u00a7501.2."
            ),
            confidence=0.82,
            requires_licensed_review=_is_critical("PLMB-WH-ELEVATION-001"),
        )
    ]


# ---------------------------------------------------------------------------
# Rule registry — ordered, all deterministic
# ---------------------------------------------------------------------------

_RULES = [
    rule_plmb_utility_site_001,
    rule_plmb_fixture_count_001,
    rule_plmb_wh_location_001,
    rule_plmb_shower_ctrl_001,
    rule_plmb_wh_dedicated_001,
    rule_plmb_backflow_001,
    rule_plmb_wh_elevation_001,
]


# ---------------------------------------------------------------------------
# PlumbingReviewer — orchestrator
# ---------------------------------------------------------------------------


class PlumbingReviewer:
    """Deterministic plumbing reviewer (CPC).

    Call ``run()`` once per submittal round.  It fetches all needed data from
    the database, runs every rule, and bulk-inserts findings.  The connection
    is not committed here — the caller owns the transaction.
    """

    DISCIPLINE = "plumbing"

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
        """Run all plumbing rules and persist findings.

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
                logger.exception("Plumbing rule %s failed", rule_fn.__name__)

        if not all_findings:
            return []

        return emit_findings_aa(
            conn,
            ctx,
            all_findings,
            self.DISCIPLINE,
            extractor_versions_used,
        )
