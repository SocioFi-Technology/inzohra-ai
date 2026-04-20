"""Fixture-driven unit tests for accessibility rule functions.

Each test constructs an ``ArchAccessRuleContext`` from hard-coded fixture data
and calls the rule function directly — no DB, no LLM required.  KB lookups are
patched so rule logic is exercised in pure Python.

Fixture scenario mirrors the 2008 Dennis Ln / B25-2734 plan set (addition/
alteration to existing R-2 dwelling):

  - Page 1  : G-0.1  cover sheet
  - Page 2  : A-1.1  floor plan (bathroom + kitchen rooms)
  - Page 3  : C-1.1  site plan (accessible parking required)

Measurements pre-loaded for positive-case tests:
  - door_clear_width = 30.0 in (below 32-inch threshold) → AC-DOOR-WIDTH-001
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.reviewers._context import (
    ArchAccessRuleContext,
    FindingPayload,
    FloorPlanEntityRow,
    IndexEntryRow,
    MeasurementRow,
    SheetRow,
    TitleBlockRow,
)
from app.reviewers.accessibility import (
    rule_ac_door_width_001,
    rule_ac_grab_001,
    rule_ac_htg_001,
    rule_ac_kitchen_001,
    rule_ac_parking_001,
    rule_ac_path_001,
    rule_ac_reach_001,
    rule_ac_sign_001,
    rule_ac_surface_001,
    rule_ac_toilet_001,
    rule_ac_tp_disp_001,
    rule_ac_trigger_001,
    rule_ac_turn_001,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROJ_ADDR = "2008 Dennis Ln, Santa Rosa, CA"
_PROJ_ID = "00000000-0000-0000-0000-000000000099"
_SUBMITTAL_ID = "00000000-0000-0000-0000-000000000098"
_DB_URL = "postgresql://test:test@localhost/test"

_PATCH = "app.reviewers._context.lookup_canonical"

# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------


def _sheet(
    *,
    sheet_id: str = "doc:p001",
    page: int = 1,
    canonical_id: str | None = "G-0.1",
    discipline: str | None = "G",
    sheet_type: str | None = "cover",
    canonical_title: str | None = "COVER SHEET",
    conf: float = 0.90,
) -> SheetRow:
    return SheetRow(
        sheet_id=sheet_id,
        page=page,
        canonical_id=canonical_id,
        discipline_letter=discipline,
        sheet_type=sheet_type,
        canonical_title=canonical_title,
        sheet_identifier_confidence=conf,
    )


def _tb(
    *,
    entity_id: str = "ent-001",
    sheet_id: str = "doc:p001",
    page: int = 1,
    sheet_title: str | None = "REMODEL FLOOR PLAN",
    stamp: bool = True,
    confidence: float = 0.88,
) -> TitleBlockRow:
    return TitleBlockRow(
        entity_id=entity_id,
        sheet_id=sheet_id,
        page=page,
        bbox=[0.0, 720.0, 612.0, 792.0],
        project_address=_PROJ_ADDR,
        address_mismatch=False,
        stamp_present=stamp,
        scale_declared="1/4\" = 1'-0\"",
        north_arrow_bbox=None,
        permit_number="B25-2734",
        date_issued="2025-03-15",
        project_name="2008 Dennis Ln Remodel",
        designer_of_record="Jane Architect",
        sheet_title=sheet_title,
        addr_confidence=0.90,
        permit_confidence=0.90,
        date_confidence=0.90,
        name_confidence=0.90,
        designer_confidence=0.90,
        confidence=confidence,
        extractor_version="title_block:1.0.0",
    )


def _fpe(
    *,
    entity_id: str = "fpe-001",
    sheet_id: str = "doc:p002",
    page: int = 2,
    entity_type: str = "room",
    tag: str | None = None,
    room_label: str | None = None,
    room_use: str | None = None,
    bbox: list[float] | None = None,
    confidence: float = 0.85,
    geometry_notes: str | None = None,
    schedule_ref: str | None = None,
) -> FloorPlanEntityRow:
    return FloorPlanEntityRow(
        entity_id=entity_id,
        sheet_id=sheet_id,
        page=page,
        entity_type=entity_type,
        tag=tag,
        room_label=room_label,
        room_use=room_use,
        bbox=bbox or [10.0, 10.0, 100.0, 100.0],
        confidence=confidence,
        geometry_notes=geometry_notes,
        schedule_ref=schedule_ref,
    )


def _meas(
    *,
    measurement_id: str = "meas-001",
    sheet_id: str = "doc:p002",
    mtype: str = "door_clear_width",
    value: float = 36.0,
    unit: str = "in",
    confidence: float = 0.90,
    tag: str | None = "D1",
    entity_id: str | None = None,
    bbox: list[float] | None = None,
) -> MeasurementRow:
    return MeasurementRow(
        measurement_id=measurement_id,
        sheet_id=sheet_id,
        type=mtype,
        value=value,
        unit=unit,
        confidence=confidence,
        tag=tag,
        entity_id=entity_id,
        bbox=bbox,
    )


def _ctx(
    *,
    sheets: list[SheetRow] | None = None,
    title_blocks: list[TitleBlockRow] | None = None,
    index_entries: list[IndexEntryRow] | None = None,
    floor_plan_entities: list[FloorPlanEntityRow] | None = None,
    measurements: list[MeasurementRow] | None = None,
) -> ArchAccessRuleContext:
    return ArchAccessRuleContext(
        project_id=_PROJ_ID,
        submittal_id=_SUBMITTAL_ID,
        review_round=1,
        jurisdiction="santa_rosa",
        effective_date="2025-01-01",
        project_address=_PROJ_ADDR,
        database_url=_DB_URL,
        sheets=sheets or [],
        title_blocks=title_blocks or [],
        index_entries=index_entries or [],
        floor_plan_entities=floor_plan_entities or [],
        measurements=measurements or [],
    )


# ===========================================================================
# AC-TRIGGER-001
# ===========================================================================


def test_ac_trigger_001_fires_when_floor_plan_entities_present() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bedroom"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_trigger_001(ctx)

    assert len(results) == 1
    f = results[0]
    assert f.rule_id == "AC-TRIGGER-001"
    assert f.severity == "reference_only"
    assert "addition or alteration" in f.draft_comment_text


def test_ac_trigger_001_fires_on_title_block_alteration_keyword() -> None:
    tb = _tb(sheet_title="ADDITION FLOOR PLAN")
    ctx = _ctx(title_blocks=[tb])
    with patch(_PATCH, return_value=None):
        results = rule_ac_trigger_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "AC-TRIGGER-001"


def test_ac_trigger_001_no_finding_when_no_entities_no_keywords() -> None:
    ctx = _ctx(title_blocks=[_tb(sheet_title="NEW CONSTRUCTION")])
    with patch(_PATCH, return_value=None):
        results = rule_ac_trigger_001(ctx)

    # "NEW CONSTRUCTION" has no alteration keyword and no floor_plan_entities
    assert results == []


# ===========================================================================
# AC-PATH-001
# ===========================================================================


def test_ac_path_001_fires_when_bath_present_no_route() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bathroom", entity_id="fpe-bath"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_path_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "AC-PATH-001"
    assert results[0].severity == "provide"


def test_ac_path_001_no_finding_when_route_exists() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bathroom", entity_id="fpe-bath"),
            _fpe(entity_type="accessible_route", entity_id="fpe-route"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_path_001(ctx)

    assert results == []


def test_ac_path_001_no_finding_when_no_bath() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bedroom"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_path_001(ctx)

    assert results == []


# ===========================================================================
# AC-DOOR-WIDTH-001
# ===========================================================================


def test_ac_door_width_001_fires_when_below_32() -> None:
    ctx = _ctx(measurements=[_meas(mtype="door_clear_width", value=30.0, tag="D1")])
    with patch(_PATCH, return_value=None):
        results = rule_ac_door_width_001(ctx)

    assert len(results) == 1
    f = results[0]
    assert f.rule_id == "AC-DOOR-WIDTH-001"
    assert f.severity == "revise"
    assert "30.0" in f.draft_comment_text
    assert "D1" in f.draft_comment_text
    assert f.confidence == 0.90


def test_ac_door_width_001_no_finding_at_exactly_32() -> None:
    ctx = _ctx(measurements=[_meas(mtype="door_clear_width", value=32.0)])
    with patch(_PATCH, return_value=None):
        results = rule_ac_door_width_001(ctx)

    assert results == []


def test_ac_door_width_001_no_finding_above_32() -> None:
    ctx = _ctx(measurements=[_meas(mtype="door_clear_width", value=36.0)])
    with patch(_PATCH, return_value=None):
        results = rule_ac_door_width_001(ctx)

    assert results == []


def test_ac_door_width_001_multiple_violations() -> None:
    ctx = _ctx(
        measurements=[
            _meas(mtype="door_clear_width", value=28.0, tag="D1", measurement_id="m1"),
            _meas(mtype="door_clear_width", value=30.0, tag="D2", measurement_id="m2"),
            _meas(mtype="door_clear_width", value=36.0, tag="D3", measurement_id="m3"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_door_width_001(ctx)

    assert len(results) == 2
    rule_ids = {f.rule_id for f in results}
    assert rule_ids == {"AC-DOOR-WIDTH-001"}


def test_ac_door_width_001_ignores_non_door_measurements() -> None:
    ctx = _ctx(measurements=[_meas(mtype="room_area", value=10.0)])
    with patch(_PATCH, return_value=None):
        results = rule_ac_door_width_001(ctx)

    assert results == []


# ===========================================================================
# AC-TURN-001
# ===========================================================================


def test_ac_turn_001_fires_when_bath_present_no_turning_measurement() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bathroom", room_label="BATHROOM"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_turn_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "AC-TURN-001"
    assert results[0].severity == "provide"
    assert "60-inch" in results[0].draft_comment_text


def test_ac_turn_001_no_finding_when_measurement_present() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bathroom"),
        ],
        measurements=[_meas(mtype="turning_diameter", value=62.0)],
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_turn_001(ctx)

    assert results == []


def test_ac_turn_001_fires_for_kitchen_too() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="kitchen", room_label="KITCHEN"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_turn_001(ctx)

    assert len(results) == 1
    assert "KITCHEN" in results[0].draft_comment_text


def test_ac_turn_001_no_finding_when_no_accessible_rooms() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bedroom"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_turn_001(ctx)

    assert results == []


# ===========================================================================
# AC-KITCHEN-001
# ===========================================================================


def test_ac_kitchen_001_fires_when_kitchen_present_no_note() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="kitchen", entity_id="fpe-kitchen"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_kitchen_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "AC-KITCHEN-001"
    assert results[0].severity == "provide"


def test_ac_kitchen_001_no_finding_when_code_note_present() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="kitchen"),
            _fpe(entity_type="code_note", room_label="kitchen clearance per 11B-804"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_kitchen_001(ctx)

    assert results == []


def test_ac_kitchen_001_no_finding_when_no_kitchen() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bedroom"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_kitchen_001(ctx)

    assert results == []


# ===========================================================================
# AC-TOILET-001
# ===========================================================================


def test_ac_toilet_001_fires_when_bath_no_details() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bathroom"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_toilet_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "AC-TOILET-001"
    assert results[0].severity == "provide"
    assert "water closet" in results[0].draft_comment_text


def test_ac_toilet_001_no_finding_when_accessible_note_present() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bathroom"),
            _fpe(entity_type="code_note", room_label="accessible toilet room per 11B-603"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_toilet_001(ctx)

    assert results == []


# ===========================================================================
# AC-TP-DISP-001
# ===========================================================================


def test_ac_tp_disp_001_fires_when_bath_no_annotation() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bathroom"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_tp_disp_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "AC-TP-DISP-001"
    assert "dispenser" in results[0].draft_comment_text.lower()


def test_ac_tp_disp_001_no_finding_when_measurement_exists() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bathroom"),
        ],
        measurements=[_meas(mtype="toilet_paper_dispenser_location", value=8.0)],
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_tp_disp_001(ctx)

    assert results == []


def test_ac_tp_disp_001_no_finding_when_code_note_present() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bathroom"),
            _fpe(entity_type="code_note", room_label="dispenser location per 11B-604.7"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_tp_disp_001(ctx)

    assert results == []


# ===========================================================================
# AC-GRAB-001
# ===========================================================================


def test_ac_grab_001_fires_when_bath_no_blocking_note() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bathroom"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_grab_001(ctx)

    assert len(results) == 1
    f = results[0]
    assert f.rule_id == "AC-GRAB-001"
    assert f.requires_licensed_review is True
    assert "blocking" in f.draft_comment_text.lower()


def test_ac_grab_001_no_finding_when_grab_bar_note_present() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bathroom"),
            _fpe(entity_type="code_note", room_label="grab bar blocking provided"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_grab_001(ctx)

    assert results == []


def test_ac_grab_001_no_finding_when_no_bath() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bedroom"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_grab_001(ctx)

    assert results == []


# ===========================================================================
# AC-REACH-001
# ===========================================================================


def test_ac_reach_001_fires_when_kitchen_no_reach_measurement() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="kitchen"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_reach_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "AC-REACH-001"
    assert "48 inches" in results[0].draft_comment_text


def test_ac_reach_001_no_finding_when_measurement_present() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="kitchen"),
        ],
        measurements=[_meas(mtype="appliance_reach_height", value=46.0)],
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_reach_001(ctx)

    assert results == []


def test_ac_reach_001_fires_for_laundry_too() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="laundry", room_label="LAUNDRY"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_reach_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "AC-REACH-001"


def test_ac_reach_001_no_finding_when_no_kitchen_or_laundry() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bedroom"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_reach_001(ctx)

    assert results == []


# ===========================================================================
# AC-SIGN-001
# ===========================================================================


def test_ac_sign_001_fires_when_3_plus_rooms_no_tactile_sign() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", entity_id=f"fpe-{i:03d}") for i in range(4)
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_sign_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "AC-SIGN-001"
    assert "60 inches" in results[0].draft_comment_text


def test_ac_sign_001_no_finding_when_tactile_sign_present() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", entity_id=f"fpe-{i:03d}") for i in range(4)
        ]
        + [_fpe(entity_type="tactile_sign", entity_id="fpe-sign")]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_sign_001(ctx)

    assert results == []


def test_ac_sign_001_no_finding_when_fewer_than_3_rooms() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", entity_id="fpe-001"),
            _fpe(entity_type="room", entity_id="fpe-002"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_sign_001(ctx)

    assert results == []


# ===========================================================================
# AC-PARKING-001
# ===========================================================================


def test_ac_parking_001_fires_when_site_plan_exists_no_parking_measurement() -> None:
    ctx = _ctx(
        sheets=[
            _sheet(sheet_id="doc:p003", sheet_type="site_plan", canonical_id="C-1.1"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_parking_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "AC-PARKING-001"
    assert "site plan" in results[0].draft_comment_text.lower()


def test_ac_parking_001_no_finding_when_parking_measurement_exists() -> None:
    ctx = _ctx(
        sheets=[
            _sheet(sheet_id="doc:p003", sheet_type="site_plan"),
        ],
        measurements=[
            _meas(mtype="accessible_parking_stall_width", value=144.0),
        ],
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_parking_001(ctx)

    assert results == []


def test_ac_parking_001_no_finding_when_no_site_plan() -> None:
    ctx = _ctx(
        sheets=[
            _sheet(sheet_id="doc:p002", sheet_type="floor_plan"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_parking_001(ctx)

    assert results == []


# ===========================================================================
# AC-SURFACE-001
# ===========================================================================


def test_ac_surface_001_fires_when_route_entity_no_slope() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="accessible_route"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_surface_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "AC-SURFACE-001"
    assert results[0].severity == "clarify"
    assert "1:20" in results[0].draft_comment_text


def test_ac_surface_001_fires_when_path_of_travel_code_note() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="code_note", room_label="path of travel to be made accessible"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_surface_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "AC-SURFACE-001"


def test_ac_surface_001_no_finding_when_slope_measured() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="accessible_route"),
        ],
        measurements=[_meas(mtype="running_slope", value=0.04)],
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_surface_001(ctx)

    assert results == []


def test_ac_surface_001_no_finding_when_no_route_indication() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bedroom"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_surface_001(ctx)

    assert results == []


# ===========================================================================
# AC-HTG-001
# ===========================================================================


def test_ac_htg_001_fires_when_kitchen_no_work_surface_height() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="kitchen"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_htg_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "AC-HTG-001"
    assert "28" in results[0].draft_comment_text
    assert "34 inches" in results[0].draft_comment_text


def test_ac_htg_001_no_finding_when_height_measured() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="kitchen"),
        ],
        measurements=[_meas(mtype="work_surface_height", value=32.0)],
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_htg_001(ctx)

    assert results == []


def test_ac_htg_001_fires_for_dining_too() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="dining", room_label="DINING"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_htg_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "AC-HTG-001"


def test_ac_htg_001_no_finding_when_no_kitchen_or_dining() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bedroom"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_htg_001(ctx)

    assert results == []


# ===========================================================================
# Citation plumbing
# ===========================================================================


def test_rule_uses_fallback_citation_when_kb_miss() -> None:
    """When lookup_canonical returns None, fallback citation is used (no hallucination)."""
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bathroom"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_toilet_001(ctx)

    assert len(results) == 1
    # Citation should be present even without KB
    assert len(results[0].citations) == 1
    cit = results[0].citations[0]
    # frozen_text is None when fallback
    assert cit.get("frozen_text") is None
    assert "note" in cit


def test_rule_uses_live_citation_when_kb_hit() -> None:
    """When the KB lookup succeeds, the live citation dict is used."""
    from unittest.mock import MagicMock

    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bathroom"),
        ]
    )
    mock_cit = MagicMock()
    mock_cit.to_finding_citation.return_value = {
        "code": "CBC",
        "section": "11B-603",
        "canonical_id": "CBC-11B-603",
        "jurisdiction": "santa_rosa",
        "effective_date": "2023-01-01",
        "frozen_text": "Toilet rooms and bathing rooms…",
    }

    with patch(_PATCH, return_value=mock_cit):
        results = rule_ac_toilet_001(ctx)

    assert len(results) == 1
    assert results[0].citations[0]["canonical_id"] == "CBC-11B-603"
    assert results[0].citations[0]["frozen_text"] is not None


# ===========================================================================
# requires_licensed_review
# ===========================================================================


def test_ac_grab_001_sets_requires_licensed_review() -> None:
    ctx = _ctx(
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bathroom"),
        ]
    )
    with patch(_PATCH, return_value=None):
        results = rule_ac_grab_001(ctx)

    assert results[0].requires_licensed_review is True


@pytest.mark.parametrize(
    "rule_fn",
    [
        rule_ac_trigger_001,
        rule_ac_path_001,
        rule_ac_turn_001,
        rule_ac_kitchen_001,
        rule_ac_toilet_001,
        rule_ac_tp_disp_001,
        rule_ac_reach_001,
        rule_ac_sign_001,
        rule_ac_parking_001,
        rule_ac_surface_001,
        rule_ac_htg_001,
    ],
)
def test_non_grab_rules_do_not_set_licensed_review(rule_fn: object) -> None:  # type: ignore[type-arg]
    """All non-grab rules must NOT set requires_licensed_review."""
    # Build a fully-populated context so rules fire
    ctx = _ctx(
        sheets=[
            _sheet(sheet_id="doc:p001", sheet_type="site_plan"),
        ],
        title_blocks=[_tb(sheet_title="ADDITION")],
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bathroom", entity_id="fpe-bath"),
            _fpe(entity_type="room", room_use="kitchen", entity_id="fpe-kitchen"),
            _fpe(entity_type="room", room_use="bedroom", entity_id="fpe-bed1"),
            _fpe(entity_type="room", room_use="bedroom", entity_id="fpe-bed2"),
        ],
    )
    import inspect
    fn = rule_fn  # type: ignore[assignment]
    with patch(_PATCH, return_value=None):
        results = fn(ctx)  # type: ignore[operator]

    for f in results:
        assert f.requires_licensed_review is False, (
            f"{fn.__name__} must not set requires_licensed_review"  # type: ignore[attr-defined]
        )


# ===========================================================================
# Full fixture scenario
# ===========================================================================


def test_full_fixture_scenario() -> None:
    """Run all accessibility rules against a representative fixture."""
    from app.reviewers.accessibility import _RULES

    ctx = _ctx(
        sheets=[
            _sheet(sheet_id="doc:p001", sheet_type="cover", canonical_id="G-0.1"),
            _sheet(sheet_id="doc:p002", sheet_type="floor_plan", canonical_id="A-1.1",
                   discipline="A"),
            _sheet(sheet_id="doc:p003", sheet_type="site_plan", canonical_id="C-1.1",
                   discipline="C"),
        ],
        title_blocks=[
            _tb(sheet_id="doc:p001", entity_id="ent-001",
                sheet_title="ADDITION FLOOR PLAN"),
        ],
        floor_plan_entities=[
            _fpe(entity_type="room", room_use="bathroom", room_label="BATHROOM",
                 sheet_id="doc:p002", entity_id="fpe-bath"),
            _fpe(entity_type="room", room_use="kitchen", room_label="KITCHEN",
                 sheet_id="doc:p002", entity_id="fpe-kitchen"),
            _fpe(entity_type="room", room_use="bedroom", room_label="BEDROOM 1",
                 sheet_id="doc:p002", entity_id="fpe-bed1"),
            _fpe(entity_type="room", room_use="bedroom", room_label="BEDROOM 2",
                 sheet_id="doc:p002", entity_id="fpe-bed2"),
        ],
        measurements=[
            # One door below threshold
            _meas(mtype="door_clear_width", value=28.0, tag="D1",
                  measurement_id="m-door"),
        ],
    )

    all_findings: list[FindingPayload] = []
    with patch(_PATCH, return_value=None):
        for rule_fn in _RULES:
            all_findings.extend(rule_fn(ctx))

    rule_ids = [f.rule_id for f in all_findings]

    # Alteration trigger must fire
    assert "AC-TRIGGER-001" in rule_ids

    # Accessible route not shown (bath present, no route entity)
    assert "AC-PATH-001" in rule_ids

    # Door below threshold
    assert "AC-DOOR-WIDTH-001" in rule_ids

    # Turning space not shown
    assert "AC-TURN-001" in rule_ids

    # Kitchen not dimensioned
    assert "AC-KITCHEN-001" in rule_ids

    # Toilet details absent
    assert "AC-TOILET-001" in rule_ids

    # TP dispenser not shown
    assert "AC-TP-DISP-001" in rule_ids

    # Grab bar blocking absent
    assert "AC-GRAB-001" in rule_ids

    # Appliance reach range absent
    assert "AC-REACH-001" in rule_ids

    # 4 rooms, no tactile sign
    assert "AC-SIGN-001" in rule_ids

    # Site plan present, no accessible parking dimensions
    assert "AC-PARKING-001" in rule_ids

    # Work surface height absent
    assert "AC-HTG-001" in rule_ids

    # Grab-bar rule must be the only one flagging licensed review
    grab_findings = [f for f in all_findings if f.rule_id == "AC-GRAB-001"]
    assert all(f.requires_licensed_review for f in grab_findings)

    non_grab = [f for f in all_findings if f.rule_id != "AC-GRAB-001"]
    assert all(not f.requires_licensed_review for f in non_grab)
