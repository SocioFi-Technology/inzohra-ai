"""Accessibility reviewer — Phase 04.

Deterministic rules (pass 1):
  AC-TRIGGER-001    Project is an addition/alteration — 11B-202 triggered
  AC-PATH-001       No accessible route shown between required elements
  AC-DOOR-WIDTH-001 Door clear width < 32 inches measured (11B-404.2.3.1)
  AC-TURN-001       Turning space not shown in accessible rooms/baths (11B-304.3.1)
  AC-KITCHEN-001    Kitchen clearance / reach ranges not dimensioned (11B-804.2.1)
  AC-TOILET-001     Accessible toilet room details absent (11B-603)
  AC-TP-DISP-001    Toilet paper dispenser location not shown (11B-604.7)
  AC-GRAB-001       Grab bar blocking notes absent in bathroom walls (11B-604.5)
  AC-REACH-001      Appliance reach range not shown (11B-308)
  AC-SIGN-001       Tactile sign location not shown at accessible rooms (11B-703.4.1)
  AC-PARKING-001    Accessible parking spaces not shown/dimensioned (11B-208)
  AC-SURFACE-001    Accessible route surface not specified (11B-302)
  AC-HTG-001        Accessible work surface height not dimensioned (11B-902.3)

No LLM residue pass — accessibility is deterministic measurement vs. threshold.
"""
from __future__ import annotations

import logging
from typing import Any

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

_RULE_VERSIONS: dict[str, str] = {
    "AC-TRIGGER-001":    "1.0.0",
    "AC-PATH-001":       "1.0.0",
    "AC-DOOR-WIDTH-001": "1.0.0",
    "AC-TURN-001":       "1.0.0",
    "AC-KITCHEN-001":    "1.0.0",
    "AC-TOILET-001":     "1.0.0",
    "AC-TP-DISP-001":    "1.0.0",
    "AC-GRAB-001":       "1.0.0",
    "AC-REACH-001":      "1.0.0",
    "AC-SIGN-001":       "1.0.0",
    "AC-PARKING-001":    "1.0.0",
    "AC-SURFACE-001":    "1.0.0",
    "AC-HTG-001":        "1.0.0",
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


def _fallback_citation(canonical_id: str) -> dict[str, Any]:
    """Return a stub citation when the KB lookup returns None.

    Never invents text — frozen_text is explicitly None with a note.
    """
    section = canonical_id.split("-", 1)[1] if "-" in canonical_id else canonical_id
    return {
        "code": "CBC",
        "section": section,
        "frozen_text": None,
        "note": "Section not yet in KB",
    }


def _get_cit(ctx: ArchAccessRuleContext, canonical_id: str) -> dict[str, Any]:
    """Return a live citation or a clearly-flagged fallback — never hallucinated."""
    cit = get_citation_aa(ctx, canonical_id)
    return cit if cit is not None else _fallback_citation(canonical_id)


def _first_bath_sheet(entities: list[FloorPlanEntityRow]) -> str | None:
    """Return the sheet_id of the first bathroom/toilet room entity, or None."""
    for e in entities:
        use = (e.room_use or "").lower()
        label = (e.room_label or "").lower()
        if "bath" in use or "toilet" in use or "bath" in label or "toilet" in label:
            return e.sheet_id
    return None


def _first_kitchen_sheet(entities: list[FloorPlanEntityRow]) -> str | None:
    """Return the sheet_id of the first kitchen entity, or None."""
    for e in entities:
        use = (e.room_use or "").lower()
        label = (e.room_label or "").lower()
        if "kitchen" in use or "kitchen" in label:
            return e.sheet_id
    return None


def _bath_entities(ctx: ArchAccessRuleContext) -> list[FloorPlanEntityRow]:
    """All floor-plan entities that are bathroom / toilet rooms."""
    result: list[FloorPlanEntityRow] = []
    for e in ctx.floor_plan_entities:
        use = (e.room_use or "").lower()
        label = (e.room_label or "").lower()
        if "bath" in use or "toilet" in use or "bath" in label or "toilet" in label:
            result.append(e)
    return result


def _kitchen_entities(ctx: ArchAccessRuleContext) -> list[FloorPlanEntityRow]:
    """All floor-plan entities that are kitchens."""
    result: list[FloorPlanEntityRow] = []
    for e in ctx.floor_plan_entities:
        use = (e.room_use or "").lower()
        label = (e.room_label or "").lower()
        if "kitchen" in use or "kitchen" in label:
            result.append(e)
    return result


def _has_measurement_type(ctx: ArchAccessRuleContext, mtype: str) -> bool:
    return any(m.type == mtype for m in ctx.measurements)


def _has_entity_type(ctx: ArchAccessRuleContext, etype: str) -> bool:
    return any(e.entity_type == etype for e in ctx.floor_plan_entities)


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


# ---------------------------------------------------------------------------
# AC-TRIGGER-001 — Project is an addition/alteration
# ---------------------------------------------------------------------------


def rule_ac_trigger_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """One project-wide reference_only finding when the project is an addition or alteration.

    Triggers if:
    - Any title_block entity payload has project_type containing "addition" or "alteration", OR
    - Any floor_plan_entity exists (indicating active design work in the plans).
    """
    # Check title-block payloads for project_type field
    is_alteration = False
    for tb in ctx.title_blocks:
        # sheet_title is the closest proxy in TitleBlockRow; check it
        title = (tb.sheet_title or "").lower()
        if "addition" in title or "alteration" in title or "remodel" in title:
            is_alteration = True
            break

    # Fallback: any floor-plan entity present → active construction project
    if not is_alteration and ctx.floor_plan_entities:
        is_alteration = True

    if not is_alteration:
        return []

    cit = _get_cit(ctx, "CBC-11B-202")
    return [
        FindingPayload(
            rule_id="AC-TRIGGER-001",
            rule_version=_RULE_VERSIONS["AC-TRIGGER-001"],
            severity="reference_only",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "This project involves an addition or alteration to an existing "
                "building. All new construction and altered portions of the building "
                "shall comply with accessibility requirements per CBC Chapter 11B. "
                "The path of travel to the area of alteration shall also be made "
                "accessible to the extent required by \u00a711B-202.4."
            ),
            confidence=0.80,
        )
    ]


# ---------------------------------------------------------------------------
# AC-PATH-001 — No accessible route shown
# ---------------------------------------------------------------------------


def rule_ac_path_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when bathrooms are present but no accessible_route entity exists."""
    baths = _bath_entities(ctx)
    if not baths:
        return []

    if _has_entity_type(ctx, "accessible_route"):
        return []

    cit = _get_cit(ctx, "CBC-11B-202")
    return [
        FindingPayload(
            rule_id="AC-PATH-001",
            rule_version=_RULE_VERSIONS["AC-PATH-001"],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Provide a complete accessible path of travel diagram on the site "
                "plan and floor plans, showing the accessible route from public "
                "transportation/parking through the building entrance to all "
                "accessible facilities. (CBC \u00a711B-202)"
            ),
            confidence=0.80,
        )
    ]


# ---------------------------------------------------------------------------
# AC-DOOR-WIDTH-001 — Door clear width < 32 inches
# ---------------------------------------------------------------------------


def rule_ac_door_width_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """One finding per measured door_clear_width below 32 inches."""
    findings: list[FindingPayload] = []
    cit = _get_cit(ctx, "CBC-11B-404.2.3.1")

    for m in ctx.measurements:
        if m.type != "door_clear_width":
            continue
        if m.value >= 32.0:
            continue

        tag = m.tag or "unknown"
        findings.append(
            FindingPayload(
                rule_id="AC-DOOR-WIDTH-001",
                rule_version=_RULE_VERSIONS["AC-DOOR-WIDTH-001"],
                severity="revise",
                sheet_reference=_sheet_ref(m.sheet_id, f"Door {tag} — clear width"),
                evidence=[
                    {
                        "measurement_id": m.measurement_id,
                        "value": m.value,
                        "unit": m.unit,
                        "confidence": m.confidence,
                        "bbox": m.bbox or [],
                    }
                ],
                citations=[cit],
                draft_comment_text=(
                    f"Door {tag} on sheet {m.sheet_id}: clear width measures "
                    f"{m.value} inches, which is less than the 32-inch minimum "
                    "for accessible doorways. Revise to provide 32 inches minimum "
                    "clear width. (CBC \u00a711B-404.2.3.1)"
                ),
                confidence=0.90,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# AC-TURN-001 — Turning space not shown in accessible rooms/baths
# ---------------------------------------------------------------------------


def rule_ac_turn_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding per accessible bathroom/kitchen lacking a turning_diameter measurement."""
    baths = _bath_entities(ctx)
    kitchens = _kitchen_entities(ctx)
    accessible_rooms = baths + kitchens
    if not accessible_rooms:
        return []

    if _has_measurement_type(ctx, "turning_diameter"):
        return []

    cit = _get_cit(ctx, "CBC-11B-304.3.1")
    findings: list[FindingPayload] = []

    # Emit once per accessible-use room (bath or kitchen), referencing its sheet
    seen_pairs: set[tuple[str, str]] = set()
    for room in accessible_rooms:
        room_label = room.room_label or room.room_use or "accessible room"
        key = (room.sheet_id, room_label)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)

        findings.append(
            FindingPayload(
                rule_id="AC-TURN-001",
                rule_version=_RULE_VERSIONS["AC-TURN-001"],
                severity="provide",
                sheet_reference=_sheet_ref(
                    room.sheet_id, f"Turning space — {room_label}"
                ),
                evidence=[_entity_evidence(room.entity_id, room.bbox)],
                citations=[cit],
                draft_comment_text=(
                    f"Sheet {room.sheet_id}: provide turning space dimension "
                    f"annotation in {room_label}. A 60-inch minimum diameter clear "
                    "turning space is required in accessible toilet rooms and "
                    "kitchens. (CBC \u00a711B-304.3.1)"
                ),
                confidence=0.80,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# AC-KITCHEN-001 — Kitchen clearance / reach ranges not dimensioned
# ---------------------------------------------------------------------------


def rule_ac_kitchen_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when kitchens exist but no kitchen-related code_note annotation is present."""
    kitchens = _kitchen_entities(ctx)
    if not kitchens:
        return []

    # Check for any code_note or annotation containing kitchen-related text
    if _has_code_note_with_text(ctx, "kitchen"):
        return []

    cit = _get_cit(ctx, "CBC-11B-804.2.1")
    first_sheet = _first_kitchen_sheet(ctx.floor_plan_entities)

    return [
        FindingPayload(
            rule_id="AC-KITCHEN-001",
            rule_version=_RULE_VERSIONS["AC-KITCHEN-001"],
            severity="provide",
            sheet_reference=_sheet_ref(first_sheet, "Kitchen clearance dimensions"),
            evidence=[
                _entity_evidence(k.entity_id, k.bbox) for k in kitchens[:3]
            ],
            citations=[cit],
            draft_comment_text=(
                f"Sheet {first_sheet}: provide kitchen clearance dimensions on the "
                "plans. Accessible kitchens require documented clear floor space at "
                "sink, cooking surface, and work surfaces, with appliance reach "
                "ranges per CBC \u00a711B-804 and \u00a711B-308."
            ),
            confidence=0.80,
        )
    ]


# ---------------------------------------------------------------------------
# AC-TOILET-001 — Accessible toilet room details absent
# ---------------------------------------------------------------------------


def rule_ac_toilet_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when bathrooms exist but no accessible toilet room detail is present."""
    baths = _bath_entities(ctx)
    if not baths:
        return []

    # Check if any code_note mentions toilet room accessibility requirements
    if _has_code_note_with_text(ctx, "accessible") or _has_code_note_with_text(ctx, "11B-603"):
        return []

    # Try primary citation, fall back to 11B-202
    cit = get_citation_aa(ctx, "CBC-11B-603")
    if cit is None:
        cit = _get_cit(ctx, "CBC-11B-202")

    first_sheet = _first_bath_sheet(ctx.floor_plan_entities)

    return [
        FindingPayload(
            rule_id="AC-TOILET-001",
            rule_version=_RULE_VERSIONS["AC-TOILET-001"],
            severity="provide",
            sheet_reference=_sheet_ref(first_sheet, "Accessible toilet room details"),
            evidence=[
                _entity_evidence(b.entity_id, b.bbox) for b in baths[:3]
            ],
            citations=[cit],
            draft_comment_text=(
                "Provide accessible toilet room plan and/or detail sheet showing: "
                "water closet location, grab bar locations and dimensions, clear "
                "floor space, turning space, and lavatory position per CBC "
                "Chapter 11B."
            ),
            confidence=0.80,
        )
    ]


# ---------------------------------------------------------------------------
# AC-TP-DISP-001 — Toilet paper dispenser location not shown
# ---------------------------------------------------------------------------


def rule_ac_tp_disp_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when bathrooms exist but no toilet paper dispenser annotation is present."""
    baths = _bath_entities(ctx)
    if not baths:
        return []

    # Check for a measurement or code_note mentioning toilet paper dispenser
    if _has_measurement_type(ctx, "toilet_paper_dispenser_location"):
        return []
    if _has_code_note_with_text(ctx, "dispenser") or _has_code_note_with_text(ctx, "11B-604.7"):
        return []

    cit = _get_cit(ctx, "CBC-11B-604.7")
    first_sheet = _first_bath_sheet(ctx.floor_plan_entities)

    return [
        FindingPayload(
            rule_id="AC-TP-DISP-001",
            rule_version=_RULE_VERSIONS["AC-TP-DISP-001"],
            severity="provide",
            sheet_reference=_sheet_ref(first_sheet, "Toilet paper dispenser location"),
            evidence=[
                _entity_evidence(b.entity_id, b.bbox) for b in baths[:3]
            ],
            citations=[cit],
            draft_comment_text=(
                "On the accessible toilet room plan, dimension the toilet paper "
                "dispenser location. The dispenser shall be 7\u20139 inches in front "
                "of the water closet and 15\u201348 inches above the finish floor "
                "per CBC \u00a711B-604.7."
            ),
            confidence=0.80,
        )
    ]


# ---------------------------------------------------------------------------
# AC-GRAB-001 — Grab bar blocking notes absent
# ---------------------------------------------------------------------------


def rule_ac_grab_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding (with licensed review flag) when bathrooms exist but no grab bar blocking note."""
    baths = _bath_entities(ctx)
    if not baths:
        return []

    # Check for code_note mentioning grab bars or blocking
    if (
        _has_code_note_with_text(ctx, "grab bar")
        or _has_code_note_with_text(ctx, "blocking")
        or _has_code_note_with_text(ctx, "11B-604.5")
    ):
        return []

    # Try primary citation, fall back to 11B-202
    cit = get_citation_aa(ctx, "CBC-11B-604.5")
    if cit is None:
        cit = _get_cit(ctx, "CBC-11B-202")

    first_sheet = _first_bath_sheet(ctx.floor_plan_entities)

    return [
        FindingPayload(
            rule_id="AC-GRAB-001",
            rule_version=_RULE_VERSIONS["AC-GRAB-001"],
            severity="provide",
            sheet_reference=_sheet_ref(first_sheet, "Grab bar blocking notes"),
            evidence=[
                _entity_evidence(b.entity_id, b.bbox) for b in baths[:3]
            ],
            citations=[cit],
            draft_comment_text=(
                "Provide notes on the construction documents indicating that wall "
                "blocking for grab bars has been installed or will be installed in "
                "accessible toilet and bathing rooms. (CBC \u00a711B-604.5). "
                "NOTE: Structural adequacy of blocking \u2014 requires licensed review."
            ),
            confidence=0.80,
            requires_licensed_review=True,
        )
    ]


# ---------------------------------------------------------------------------
# AC-REACH-001 — Appliance reach range not shown
# ---------------------------------------------------------------------------


def rule_ac_reach_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when kitchens/laundry exist but no appliance_reach_height measurement."""
    kitchens = _kitchen_entities(ctx)

    # Also check for laundry entities
    laundry: list[FloorPlanEntityRow] = []
    for e in ctx.floor_plan_entities:
        use = (e.room_use or "").lower()
        label = (e.room_label or "").lower()
        if "laundry" in use or "laundry" in label or "utility" in use or "utility" in label:
            laundry.append(e)

    target_rooms = kitchens + laundry
    if not target_rooms:
        return []

    if _has_measurement_type(ctx, "appliance_reach_height"):
        return []

    cit = _get_cit(ctx, "CBC-11B-308.2.1")
    first_sheet = (
        _first_kitchen_sheet(ctx.floor_plan_entities)
        or (target_rooms[0].sheet_id if target_rooms else None)
    )

    return [
        FindingPayload(
            rule_id="AC-REACH-001",
            rule_version=_RULE_VERSIONS["AC-REACH-001"],
            severity="provide",
            sheet_reference=_sheet_ref(first_sheet, "Appliance reach range annotations"),
            evidence=[
                _entity_evidence(r.entity_id, r.bbox) for r in target_rooms[:3]
            ],
            citations=[cit],
            draft_comment_text=(
                "Provide reach range annotations for all appliances (cooktop, oven, "
                "refrigerator, washer/dryer) in accessible kitchens and laundry "
                "areas. High forward reach shall not exceed 48 inches per CBC "
                "\u00a711B-308.2.1."
            ),
            confidence=0.80,
        )
    ]


# ---------------------------------------------------------------------------
# AC-SIGN-001 — Tactile sign location not shown
# ---------------------------------------------------------------------------


def rule_ac_sign_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when 3+ room entities exist but no tactile_sign entity is present."""
    room_entities = [
        e for e in ctx.floor_plan_entities if e.entity_type == "room"
    ]
    if len(room_entities) < 3:
        return []

    if _has_entity_type(ctx, "tactile_sign"):
        return []

    cit = _get_cit(ctx, "CBC-11B-703.4.1")

    return [
        FindingPayload(
            rule_id="AC-SIGN-001",
            rule_version=_RULE_VERSIONS["AC-SIGN-001"],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Provide tactile sign details on the drawings for all accessible "
                "rooms and facilities. Signs with raised characters and Braille "
                "shall be mounted on the latch side of the door at 60 inches AFF "
                "to the centerline per CBC \u00a711B-703.4.1."
            ),
            confidence=0.80,
        )
    ]


# ---------------------------------------------------------------------------
# AC-PARKING-001 — Accessible parking spaces not shown/dimensioned
# ---------------------------------------------------------------------------


def rule_ac_parking_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when a site plan sheet exists but no accessible parking measurement."""
    site_sheets = [
        s for s in ctx.sheets
        if s.sheet_type and "site" in s.sheet_type.lower()
    ]
    if not site_sheets:
        return []

    # Check for accessible parking measurements or entities
    if _has_measurement_type(ctx, "accessible_parking_stall_width"):
        return []
    if _has_code_note_with_text(ctx, "parking"):
        return []

    # Try primary citation, fall back to 11B-202
    cit = get_citation_aa(ctx, "CBC-11B-208")
    if cit is None:
        cit = _get_cit(ctx, "CBC-11B-202")

    site_sheet_id = site_sheets[0].sheet_id

    return [
        FindingPayload(
            rule_id="AC-PARKING-001",
            rule_version=_RULE_VERSIONS["AC-PARKING-001"],
            severity="provide",
            sheet_reference=_sheet_ref(site_sheet_id, "Accessible parking"),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "On the site plan, provide accessible parking space dimensions, "
                "slope, surface specification, signage details, and aisle widths "
                "per CBC \u00a711B-208 and \u00a711B-502."
            ),
            confidence=0.80,
        )
    ]


# ---------------------------------------------------------------------------
# AC-SURFACE-001 — Accessible route surface not specified
# ---------------------------------------------------------------------------


def rule_ac_surface_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Clarify finding when accessible routes exist but no slope measurement is present."""
    has_route = _has_entity_type(ctx, "accessible_route")
    has_path_note = _has_code_note_with_text(ctx, "path of travel")

    if not has_route and not has_path_note:
        return []

    # Check for slope measurements
    if _has_measurement_type(ctx, "running_slope") or _has_measurement_type(ctx, "cross_slope"):
        return []

    cit = _get_cit(ctx, "CBC-11B-302")

    return [
        FindingPayload(
            rule_id="AC-SURFACE-001",
            rule_version=_RULE_VERSIONS["AC-SURFACE-001"],
            severity="clarify",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=[cit],
            draft_comment_text=(
                "Provide accessible route surface specification and slope information "
                "on the plans. Running slope shall not exceed 1:20 and cross slope "
                "shall not exceed 1:48 except within ramp sections. (CBC \u00a711B-302)"
            ),
            confidence=0.80,
        )
    ]


# ---------------------------------------------------------------------------
# AC-HTG-001 — Accessible work surface height not dimensioned
# ---------------------------------------------------------------------------


def rule_ac_htg_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when kitchens/dining exist but no work surface height measurement."""
    kitchens = _kitchen_entities(ctx)

    # Also check dining entities
    dining: list[FloorPlanEntityRow] = []
    for e in ctx.floor_plan_entities:
        use = (e.room_use or "").lower()
        label = (e.room_label or "").lower()
        if "dining" in use or "dining" in label or "breakfast" in use or "breakfast" in label:
            dining.append(e)

    target_rooms = kitchens + dining
    if not target_rooms:
        return []

    if _has_measurement_type(ctx, "work_surface_height"):
        return []

    cit = _get_cit(ctx, "CBC-11B-902.3")
    first_sheet = (
        _first_kitchen_sheet(ctx.floor_plan_entities)
        or (target_rooms[0].sheet_id if target_rooms else None)
    )

    return [
        FindingPayload(
            rule_id="AC-HTG-001",
            rule_version=_RULE_VERSIONS["AC-HTG-001"],
            severity="provide",
            sheet_reference=_sheet_ref(first_sheet, "Accessible work surface height"),
            evidence=[
                _entity_evidence(r.entity_id, r.bbox) for r in target_rooms[:3]
            ],
            citations=[cit],
            draft_comment_text=(
                "Provide height dimension for accessible work surfaces. Work "
                "surfaces shall be 28\u201334 inches above finish floor per CBC "
                "\u00a711B-902.3."
            ),
            confidence=0.80,
        )
    ]


# ---------------------------------------------------------------------------
# Rule registry — ordered, all deterministic
# ---------------------------------------------------------------------------

_RULES = [
    rule_ac_trigger_001,
    rule_ac_path_001,
    rule_ac_door_width_001,
    rule_ac_turn_001,
    rule_ac_kitchen_001,
    rule_ac_toilet_001,
    rule_ac_tp_disp_001,
    rule_ac_grab_001,
    rule_ac_reach_001,
    rule_ac_sign_001,
    rule_ac_parking_001,
    rule_ac_surface_001,
    rule_ac_htg_001,
]


# ---------------------------------------------------------------------------
# AccessibilityReviewer — orchestrator
# ---------------------------------------------------------------------------


class AccessibilityReviewer:
    """Deterministic accessibility reviewer (CBC Chapter 11B).

    Call ``run()`` once per submittal round.  It fetches all needed data from
    the database, runs every rule, and bulk-inserts findings.  The connection
    is not committed here — the caller owns the transaction.
    """

    DISCIPLINE = "accessibility"

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
        """Run all accessibility rules and persist findings.

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
