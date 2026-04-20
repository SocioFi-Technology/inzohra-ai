"""Fixture-driven unit tests for plan-integrity rule functions.

Each test constructs a ``RuleContext`` from hard-coded fixture data and calls
the rule function directly — no DB, no LLM required.  The ``get_citation``
call is patched out so the rule logic is exercised in pure Python.

Fixture scenario mirrors the 2008 Dennis Ln / B25-2734 plan set:

  - Page 1  : G-0.1  cover sheet (has sheet index)
  - Page 2  : A-1.1  floor plan (address mismatch "1966 Dennis Ln"; stamp absent)
  - Page 3  : A-1.5  floor plan (title in index says "SITE PLAN"; stamp absent)
  - Page 4  : E-1.0  electrical plan (but sheet index also declares "A-1.1" for this slot)
  - Page 5  : A-3.1  elevation (missing scale, stamp absent)
  - Page 6  : C-1.1  site plan (missing north arrow, scale absent)

Sheet index entries (from G-0.1):
  G-0.1  Cover Sheet
  A-1.1  Floor Plan               ← matches actual A-1.1 ✓
  A-1.5  SITE PLAN                ← actual A-1.5 says "FLOOR PLAN" → PI-INDEX-004
  E-1.0  Electrical Plan          ← no actual sheet E-1.0 exists  → PI-INDEX-003
  A-3.1  Elevations
  C-1.1  Site Plan

Tests are parametric where possible to document both positive and negative
cases.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.reviewers._context import (
    FindingPayload,
    IndexEntryRow,
    RuleContext,
    SheetRow,
    TitleBlockRow,
)
from app.reviewers.plan_integrity import (
    _normalize_sheet_id,
    _title_mismatch,
    rule_pi_addr_001,
    rule_pi_date_001,
    rule_pi_index_001,
    rule_pi_index_002,
    rule_pi_index_003,
    rule_pi_index_004,
    rule_pi_north_001,
    rule_pi_permit_001,
    rule_pi_scale_001,
    rule_pi_stamp_001,
    rule_pi_title_001,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROJ_ADDR = "2008 Dennis Ln, Santa Rosa, CA"
_PROJ_ID = "00000000-0000-0000-0000-000000000099"
_SUBMITTAL_ID = "00000000-0000-0000-0000-000000000098"
_DB_URL = "postgresql://test:test@localhost/test"  # never actually connected


def _tb(
    *,
    entity_id: str = "ent-001",
    sheet_id: str = "doc:p001",
    page: int = 1,
    address: str | None = _PROJ_ADDR,
    address_mismatch: bool = False,
    stamp: bool = True,
    scale: str | None = "1/4\" = 1'-0\"",
    north_arrow: list[float] | None = None,
    permit: str | None = "B25-2734",
    date: str | None = "2025-03-15",
    project_name: str | None = "2008 Dennis Ln Remodel",
    designer: str | None = "Jane Architect",
    sheet_title: str | None = "FLOOR PLAN",
    addr_conf: float = 0.90,
    permit_conf: float = 0.90,
    date_conf: float = 0.90,
    name_conf: float = 0.90,
    designer_conf: float = 0.90,
    confidence: float = 0.88,
    extractor_version: str = "title_block:1.0.0+sid:1.0.0",
    bbox: list[float] | None = None,
) -> TitleBlockRow:
    return TitleBlockRow(
        entity_id=entity_id,
        sheet_id=sheet_id,
        page=page,
        bbox=bbox or [0.0, 720.0, 612.0, 792.0],
        project_address=address,
        address_mismatch=address_mismatch,
        stamp_present=stamp,
        scale_declared=scale,
        north_arrow_bbox=north_arrow,
        permit_number=permit,
        date_issued=date,
        project_name=project_name,
        designer_of_record=designer,
        sheet_title=sheet_title,
        addr_confidence=addr_conf,
        permit_confidence=permit_conf,
        date_confidence=date_conf,
        name_confidence=name_conf,
        designer_confidence=designer_conf,
        confidence=confidence,
        extractor_version=extractor_version,
    )


def _sheet(
    *,
    sheet_id: str = "doc:p001",
    page: int = 1,
    canonical_id: str | None = "A-1.1",
    discipline: str | None = "A",
    sheet_type: str | None = "floor_plan",
    canonical_title: str | None = "FLOOR PLAN",
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


def _idx(
    *,
    entry_id: str = "idx-001",
    declared_id: str = "A-1.1",
    declared_title: str | None = "FLOOR PLAN",
    source_sheet_id: str = "doc:p001",
    conf: float = 0.85,
    bbox: list[float] | None = None,
) -> IndexEntryRow:
    return IndexEntryRow(
        entry_id=entry_id,
        declared_id=declared_id,
        declared_title=declared_title,
        bbox=bbox or [0.0, 0.0, 100.0, 20.0],
        source_sheet_id=source_sheet_id,
        confidence=conf,
    )


def _ctx(**overrides: object) -> RuleContext:
    """Build a default RuleContext with optional overrides."""
    base: dict[str, object] = {
        "project_id": _PROJ_ID,
        "submittal_id": _SUBMITTAL_ID,
        "review_round": 1,
        "jurisdiction": "santa_rosa",
        "effective_date": "2025-01-01",
        "project_address": _PROJ_ADDR,
        "database_url": _DB_URL,
        "sheets": [],
        "title_blocks": [],
        "index_entries": [],
    }
    base.update(overrides)
    return RuleContext(**base)  # type: ignore[arg-type]


# Patch out Code-KB lookups for all tests — rule logic must work without DB
_MOCK_CITATION = {
    "code": "CBC",
    "section": "107.2.1",
    "canonical_id": "CBC-107.2.1",
    "jurisdiction": "santa_rosa",
    "effective_date": "2023-01-01",
    "title": "Information on construction documents",
    "frozen_text": "Construction documents shall be dimensioned and drawn to scale…",
    "amendments": [],
    "agency_policies": [],
    "cross_references": [],
    "referenced_standards": [],
    "retrieval_chain": ["mock"],
    "confidence": 1.0,
}

_PATCH = "app.reviewers._context.lookup_canonical"


# ===========================================================================
# Helpers unit tests
# ===========================================================================


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("A-1.1",  "A-1.1"),
        ("A1.1",   "A-1.1"),
        ("A 1.1",  "A-1.1"),
        ("E-1.0",  "E-1.0"),
        ("G-0.1",  "G-0.1"),
        ("C-1.1",  "C-1.1"),
        ("",       None),
        ("1.1",    None),    # no discipline letter
        ("ZZ-1.1", None),    # invalid discipline
    ],
)
def test_normalize_sheet_id(raw: str, expected: str | None) -> None:
    assert _normalize_sheet_id(raw) == expected


@pytest.mark.parametrize(
    "a, b, expect_mismatch",
    [
        ("FLOOR PLAN", "FLOOR PLAN",           False),
        ("floor plan", "FLOOR PLAN",           False),
        ("FLOOR PLAN", "FLOOR PLAN - LEVEL 1", False),  # prefix → ok
        ("SITE PLAN",  "FLOOR PLAN",           True),
        ("ELEVATION",  "SECTION",              True),
        (None, "FLOOR PLAN",                   False),  # missing → not flagged
        ("FLOOR PLAN", None,                   False),
    ],
)
def test_title_mismatch(a: str | None, b: str | None, expect_mismatch: bool) -> None:
    assert _title_mismatch(a, b) == expect_mismatch


# ===========================================================================
# PI-ADDR-001
# ===========================================================================


def test_pi_addr_001_fires_on_mismatch() -> None:
    tb = _tb(address="1966 Dennis Ln, Santa Rosa, CA", address_mismatch=True,
             sheet_id="doc:p002", entity_id="ent-002")
    ctx = _ctx(title_blocks=[tb])

    with patch(_PATCH, return_value=None):
        results = rule_pi_addr_001(ctx)

    assert len(results) == 1
    f = results[0]
    assert f.rule_id == "PI-ADDR-001"
    assert f.severity == "revise"
    assert "1966 Dennis Ln" in f.draft_comment_text
    assert "2008 Dennis Ln" in f.draft_comment_text


def test_pi_addr_001_no_finding_when_match() -> None:
    tb = _tb(address=_PROJ_ADDR, address_mismatch=False)
    ctx = _ctx(title_blocks=[tb])

    with patch(_PATCH, return_value=None):
        results = rule_pi_addr_001(ctx)

    assert results == []


def test_pi_addr_001_multiple_mismatches() -> None:
    tbs = [
        _tb(address="1966 Dennis Ln", address_mismatch=True,
            sheet_id=f"doc:p{i:03d}", entity_id=f"ent-{i:03d}")
        for i in range(1, 4)
    ]
    ctx = _ctx(title_blocks=tbs)

    with patch(_PATCH, return_value=None):
        results = rule_pi_addr_001(ctx)

    assert len(results) == 3


# ===========================================================================
# PI-TITLE-001
# ===========================================================================


def test_pi_title_001_fires_when_fields_missing() -> None:
    tb = _tb(project_name=None, name_conf=0.0, address=None, addr_conf=0.0,
             designer=None, designer_conf=0.0)
    ctx = _ctx(title_blocks=[tb])

    with patch(_PATCH, return_value=None):
        results = rule_pi_title_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "PI-TITLE-001"
    assert results[0].severity == "provide"


def test_pi_title_001_no_finding_when_complete() -> None:
    tb = _tb()  # all defaults are populated and high-confidence
    ctx = _ctx(title_blocks=[tb])

    with patch(_PATCH, return_value=None):
        results = rule_pi_title_001(ctx)

    assert results == []


def test_pi_title_001_fires_on_low_confidence() -> None:
    tb = _tb(designer="?", designer_conf=0.20)  # below threshold
    ctx = _ctx(title_blocks=[tb])

    with patch(_PATCH, return_value=None):
        results = rule_pi_title_001(ctx)

    assert len(results) == 1
    assert "designer" in results[0].draft_comment_text


# ===========================================================================
# PI-PERMIT-001
# ===========================================================================


def test_pi_permit_001_fires_when_missing() -> None:
    tb = _tb(permit=None, permit_conf=0.0)
    ctx = _ctx(title_blocks=[tb])

    with patch(_PATCH, return_value=None):
        results = rule_pi_permit_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "PI-PERMIT-001"


def test_pi_permit_001_no_finding_when_present() -> None:
    tb = _tb(permit="B25-2734", permit_conf=0.95)
    ctx = _ctx(title_blocks=[tb])

    with patch(_PATCH, return_value=None):
        results = rule_pi_permit_001(ctx)

    assert results == []


# ===========================================================================
# PI-DATE-001
# ===========================================================================


def test_pi_date_001_fires_when_missing() -> None:
    tb = _tb(date=None, date_conf=0.0)
    ctx = _ctx(title_blocks=[tb])

    with patch(_PATCH, return_value=None):
        results = rule_pi_date_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "PI-DATE-001"


def test_pi_date_001_no_finding_when_present() -> None:
    tb = _tb(date="2025-03-15", date_conf=0.92)
    ctx = _ctx(title_blocks=[tb])

    with patch(_PATCH, return_value=None):
        results = rule_pi_date_001(ctx)

    assert results == []


# ===========================================================================
# PI-INDEX-001
# ===========================================================================


def test_pi_index_001_fires_on_count_mismatch() -> None:
    sheets = [_sheet(sheet_id=f"doc:p{i:03d}", page=i) for i in range(1, 4)]  # 3 actual
    entries = [_idx(entry_id=f"idx-{i:03d}", declared_id=f"A-1.{i}") for i in range(1, 5)]  # 4 declared

    ctx = _ctx(sheets=sheets, index_entries=entries)

    with patch(_PATCH, return_value=None):
        results = rule_pi_index_001(ctx)

    assert len(results) == 1
    assert "4 sheets" in results[0].draft_comment_text
    assert "3 sheets" in results[0].draft_comment_text


def test_pi_index_001_no_finding_when_matching() -> None:
    sheets = [_sheet(sheet_id=f"doc:p{i:03d}", page=i) for i in range(1, 4)]
    entries = [_idx(entry_id=f"idx-{i:03d}", declared_id=f"A-1.{i}") for i in range(1, 4)]

    ctx = _ctx(sheets=sheets, index_entries=entries)

    with patch(_PATCH, return_value=None):
        results = rule_pi_index_001(ctx)

    assert results == []


def test_pi_index_001_no_finding_when_no_index() -> None:
    """Without a sheet index we cannot fire a count mismatch."""
    sheets = [_sheet(sheet_id=f"doc:p{i:03d}", page=i) for i in range(1, 4)]
    ctx = _ctx(sheets=sheets, index_entries=[])

    with patch(_PATCH, return_value=None):
        results = rule_pi_index_001(ctx)

    assert results == []


# ===========================================================================
# PI-INDEX-002
# ===========================================================================


def test_pi_index_002_fires_on_duplicate() -> None:
    sheets = [
        _sheet(sheet_id="doc:p001", canonical_id="A-1.1", page=1),
        _sheet(sheet_id="doc:p002", canonical_id="A-1.1", page=2),  # duplicate!
        _sheet(sheet_id="doc:p003", canonical_id="A-2.1", page=3),
    ]
    ctx = _ctx(sheets=sheets)

    with patch(_PATCH, return_value=None):
        results = rule_pi_index_002(ctx)

    assert len(results) == 1
    assert "A-1.1" in results[0].draft_comment_text
    assert results[0].severity == "revise"


def test_pi_index_002_no_finding_when_unique() -> None:
    sheets = [
        _sheet(sheet_id=f"doc:p{i:03d}", canonical_id=f"A-{i}.1", page=i)
        for i in range(1, 5)
    ]
    ctx = _ctx(sheets=sheets)

    with patch(_PATCH, return_value=None):
        results = rule_pi_index_002(ctx)

    assert results == []


# ===========================================================================
# PI-INDEX-003
# ===========================================================================


def test_pi_index_003_fires_when_declared_id_missing_from_actual() -> None:
    """'E-1.0' in index but no actual sheet with that ID — BV Comment 1."""
    sheets = [
        _sheet(sheet_id="doc:p001", canonical_id="G-0.1"),
        _sheet(sheet_id="doc:p002", canonical_id="A-1.1"),
    ]
    entries = [
        _idx(declared_id="G-0.1"),
        _idx(declared_id="E-1.0", declared_title="Electrical Plan",
             entry_id="idx-002"),  # no match!
    ]
    ctx = _ctx(sheets=sheets, index_entries=entries)

    with patch(_PATCH, return_value=None):
        results = rule_pi_index_003(ctx)

    assert len(results) == 1
    f = results[0]
    assert f.rule_id == "PI-INDEX-003"
    assert f.severity == "revise"
    assert "E-1.0" in f.draft_comment_text


def test_pi_index_003_no_finding_when_all_match() -> None:
    sheets = [
        _sheet(sheet_id="doc:p001", canonical_id="G-0.1"),
        _sheet(sheet_id="doc:p002", canonical_id="A-1.1"),
    ]
    entries = [
        _idx(declared_id="G-0.1"),
        _idx(declared_id="A-1.1", entry_id="idx-002"),
    ]
    ctx = _ctx(sheets=sheets, index_entries=entries)

    with patch(_PATCH, return_value=None):
        results = rule_pi_index_003(ctx)

    assert results == []


def test_pi_index_003_normalizes_format() -> None:
    """'A1.1' in the index should match 'A-1.1' actual sheet."""
    sheets = [_sheet(sheet_id="doc:p001", canonical_id="A-1.1")]
    entries = [_idx(declared_id="A1.1")]  # no dash but should normalize
    ctx = _ctx(sheets=sheets, index_entries=entries)

    with patch(_PATCH, return_value=None):
        results = rule_pi_index_003(ctx)

    assert results == []  # matched after normalization


# ===========================================================================
# PI-INDEX-004
# ===========================================================================


def test_pi_index_004_fires_on_title_mismatch() -> None:
    """Index says 'SITE PLAN', sheet title-block says 'FLOOR PLAN' — BV Comment 18."""
    sheets = [
        _sheet(sheet_id="doc:p003", canonical_id="A-1.5",
               canonical_title="FLOOR PLAN", page=3),
    ]
    entries = [
        _idx(declared_id="A-1.5", declared_title="SITE PLAN",
             entry_id="idx-003"),
    ]
    ctx = _ctx(sheets=sheets, index_entries=entries)

    with patch(_PATCH, return_value=None):
        results = rule_pi_index_004(ctx)

    assert len(results) == 1
    f = results[0]
    assert f.rule_id == "PI-INDEX-004"
    assert f.severity == "clarify"
    assert "SITE PLAN" in f.draft_comment_text
    assert "FLOOR PLAN" in f.draft_comment_text


def test_pi_index_004_no_finding_when_titles_match() -> None:
    sheets = [_sheet(sheet_id="doc:p002", canonical_id="A-1.1",
                     canonical_title="FLOOR PLAN")]
    entries = [_idx(declared_id="A-1.1", declared_title="FLOOR PLAN")]
    ctx = _ctx(sheets=sheets, index_entries=entries)

    with patch(_PATCH, return_value=None):
        results = rule_pi_index_004(ctx)

    assert results == []


def test_pi_index_004_no_finding_when_prefix_match() -> None:
    """'FLOOR PLAN' and 'FLOOR PLAN - LEVEL 1' are compatible."""
    sheets = [_sheet(canonical_id="A-1.2", canonical_title="FLOOR PLAN - LEVEL 1")]
    entries = [_idx(declared_id="A-1.2", declared_title="FLOOR PLAN")]
    ctx = _ctx(sheets=sheets, index_entries=entries)

    with patch(_PATCH, return_value=None):
        results = rule_pi_index_004(ctx)

    assert results == []


# ===========================================================================
# PI-STAMP-001
# ===========================================================================


def test_pi_stamp_001_fires_on_architectural_without_stamp() -> None:
    """Architectural sheet (disc A) without stamp → revise."""
    tb = _tb(sheet_id="doc:p002", entity_id="ent-002", stamp=False)
    s = _sheet(sheet_id="doc:p002", canonical_id="A-1.1", discipline="A")
    ctx = _ctx(title_blocks=[tb], sheets=[s])

    with patch(_PATCH, return_value=None):
        results = rule_pi_stamp_001(ctx)

    assert len(results) == 1
    f = results[0]
    assert f.rule_id == "PI-STAMP-001"
    assert f.severity == "revise"


def test_pi_stamp_001_no_finding_when_stamp_present() -> None:
    tb = _tb(stamp=True)
    s = _sheet(discipline="A")
    ctx = _ctx(title_blocks=[tb], sheets=[s])

    with patch(_PATCH, return_value=None):
        results = rule_pi_stamp_001(ctx)

    assert results == []


def test_pi_stamp_001_no_finding_for_cover_sheet() -> None:
    """G (general/cover) discipline does not require an independent stamp."""
    tb = _tb(stamp=False, sheet_id="doc:p001")
    s = _sheet(sheet_id="doc:p001", canonical_id="G-0.1", discipline="G")
    ctx = _ctx(title_blocks=[tb], sheets=[s])

    with patch(_PATCH, return_value=None):
        results = rule_pi_stamp_001(ctx)

    assert results == []


@pytest.mark.parametrize("disc", ["S", "M", "E", "P"])
def test_pi_stamp_001_fires_for_all_stamped_disciplines(disc: str) -> None:
    tb = _tb(stamp=False, sheet_id="doc:p001")
    s = _sheet(sheet_id="doc:p001", discipline=disc)
    ctx = _ctx(title_blocks=[tb], sheets=[s])

    with patch(_PATCH, return_value=None):
        results = rule_pi_stamp_001(ctx)

    assert len(results) == 1, f"expected stamp finding for discipline {disc}"


# ===========================================================================
# PI-SCALE-001
# ===========================================================================


def test_pi_scale_001_fires_on_floor_plan_without_scale() -> None:
    tb = _tb(scale=None, sheet_id="doc:p002")
    s = _sheet(sheet_id="doc:p002", sheet_type="floor_plan")
    ctx = _ctx(title_blocks=[tb], sheets=[s])

    with patch(_PATCH, return_value=None):
        results = rule_pi_scale_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "PI-SCALE-001"
    assert results[0].severity == "provide"


def test_pi_scale_001_no_finding_when_scale_present() -> None:
    tb = _tb(scale="1/4\" = 1'-0\"")
    s = _sheet(sheet_type="floor_plan")
    ctx = _ctx(title_blocks=[tb], sheets=[s])

    with patch(_PATCH, return_value=None):
        results = rule_pi_scale_001(ctx)

    assert results == []


def test_pi_scale_001_no_finding_for_schedule() -> None:
    """Schedules do not require a scale."""
    tb = _tb(scale=None, sheet_id="doc:p005")
    s = _sheet(sheet_id="doc:p005", sheet_type="schedule")
    ctx = _ctx(title_blocks=[tb], sheets=[s])

    with patch(_PATCH, return_value=None):
        results = rule_pi_scale_001(ctx)

    assert results == []


@pytest.mark.parametrize("sheet_type", [
    "floor_plan", "elevation", "section", "site_plan", "egress_plan", "structural"
])
def test_pi_scale_001_fires_for_all_required_types(sheet_type: str) -> None:
    tb = _tb(scale=None, sheet_id="doc:p001")
    s = _sheet(sheet_id="doc:p001", sheet_type=sheet_type)
    ctx = _ctx(title_blocks=[tb], sheets=[s])

    with patch(_PATCH, return_value=None):
        results = rule_pi_scale_001(ctx)

    assert len(results) == 1, f"expected scale finding for type {sheet_type}"


# ===========================================================================
# PI-NORTH-001
# ===========================================================================


def test_pi_north_001_fires_on_site_plan_without_north_arrow() -> None:
    tb = _tb(north_arrow=None, sheet_id="doc:p006")
    s = _sheet(sheet_id="doc:p006", canonical_id="C-1.1", sheet_type="site_plan",
               discipline="C")
    ctx = _ctx(title_blocks=[tb], sheets=[s])

    with patch(_PATCH, return_value=None):
        results = rule_pi_north_001(ctx)

    assert len(results) == 1
    assert results[0].rule_id == "PI-NORTH-001"
    assert results[0].severity == "provide"


def test_pi_north_001_no_finding_when_north_arrow_present() -> None:
    tb = _tb(north_arrow=[100.0, 200.0, 130.0, 230.0], sheet_id="doc:p006")
    s = _sheet(sheet_id="doc:p006", sheet_type="site_plan")
    ctx = _ctx(title_blocks=[tb], sheets=[s])

    with patch(_PATCH, return_value=None):
        results = rule_pi_north_001(ctx)

    assert results == []


def test_pi_north_001_no_finding_for_floor_plan() -> None:
    """Floor plans do not require a north arrow."""
    tb = _tb(north_arrow=None, sheet_id="doc:p002")
    s = _sheet(sheet_id="doc:p002", sheet_type="floor_plan")
    ctx = _ctx(title_blocks=[tb], sheets=[s])

    with patch(_PATCH, return_value=None):
        results = rule_pi_north_001(ctx)

    assert results == []


# ===========================================================================
# Citation plumbing (mock gives a real citation dict)
# ===========================================================================


def test_rule_includes_citation_when_retrieval_succeeds() -> None:
    tb = _tb(address="1966 Dennis Ln", address_mismatch=True)
    ctx = _ctx(title_blocks=[tb])

    with patch(_PATCH, return_value=None) as mock_lc:
        # Simulate a successful KB lookup returning a mock Citation
        from unittest.mock import MagicMock
        mock_cit = MagicMock()
        mock_cit.to_finding_citation.return_value = _MOCK_CITATION
        mock_lc.return_value = mock_cit

        results = rule_pi_addr_001(ctx)

    assert len(results) == 1
    assert len(results[0].citations) == 1
    assert results[0].citations[0]["canonical_id"] == "CBC-107.2.1"


def test_rule_gracefully_handles_citation_miss() -> None:
    """When the KB lookup returns None, the rule still fires without a citation."""
    tb = _tb(address="1966 Dennis Ln", address_mismatch=True)
    ctx = _ctx(title_blocks=[tb])

    with patch(_PATCH, return_value=None):
        results = rule_pi_addr_001(ctx)

    assert len(results) == 1
    assert results[0].citations == []


# ===========================================================================
# Full fixture scenario (integration-style, no DB)
# ===========================================================================


def test_full_fixture_scenario() -> None:
    """Run all rules against a representative fixture and verify finding counts."""
    sheets = [
        _sheet(sheet_id="doc:p001", canonical_id="G-0.1", discipline="G",
               sheet_type="cover", canonical_title="Cover Sheet", page=1),
        _sheet(sheet_id="doc:p002", canonical_id="A-1.1", discipline="A",
               sheet_type="floor_plan", canonical_title="FLOOR PLAN", page=2),
        _sheet(sheet_id="doc:p003", canonical_id="A-1.5", discipline="A",
               sheet_type="floor_plan", canonical_title="FLOOR PLAN", page=3),
        _sheet(sheet_id="doc:p004", canonical_id="E-1.0", discipline="E",
               sheet_type="mep", canonical_title="ELECTRICAL PLAN", page=4),
        _sheet(sheet_id="doc:p005", canonical_id="A-3.1", discipline="A",
               sheet_type="elevation", canonical_title="ELEVATIONS", page=5),
        _sheet(sheet_id="doc:p006", canonical_id="C-1.1", discipline="C",
               sheet_type="site_plan", canonical_title="SITE PLAN", page=6),
    ]

    title_blocks = [
        # G-0.1 cover — stamp not required, OK
        _tb(sheet_id="doc:p001", entity_id="ent-001", stamp=True, scale=None),
        # A-1.1 — address mismatch, no stamp
        _tb(sheet_id="doc:p002", entity_id="ent-002",
            address="1966 Dennis Ln, Santa Rosa, CA", address_mismatch=True,
            stamp=False, scale="1/4\" = 1'-0\""),
        # A-1.5 — OK address, no stamp
        _tb(sheet_id="doc:p003", entity_id="ent-003", stamp=False,
            scale="1/4\" = 1'-0\""),
        # E-1.0 — OK
        _tb(sheet_id="doc:p004", entity_id="ent-004", stamp=True,
            scale="1/4\" = 1'-0\""),
        # A-3.1 — missing scale, no stamp
        _tb(sheet_id="doc:p005", entity_id="ent-005", stamp=False, scale=None),
        # C-1.1 site plan — missing north arrow, missing scale
        _tb(sheet_id="doc:p006", entity_id="ent-006", north_arrow=None,
            scale=None, stamp=False),
    ]

    index_entries = [
        _idx(declared_id="G-0.1",  declared_title="Cover Sheet",    entry_id="idx-001"),
        _idx(declared_id="A-1.1",  declared_title="FLOOR PLAN",     entry_id="idx-002"),
        _idx(declared_id="A-1.5",  declared_title="SITE PLAN",      entry_id="idx-003"),  # title mismatch
        _idx(declared_id="X-9.9",  declared_title="Mystery Sheet",  entry_id="idx-004"),  # not in actual
        _idx(declared_id="A-3.1",  declared_title="ELEVATIONS",     entry_id="idx-005"),
        # C-1.1 not in index → but PI-INDEX-003 fires on X-9.9 being declared but absent
    ]

    ctx = _ctx(sheets=sheets, title_blocks=title_blocks, index_entries=index_entries)

    from app.reviewers.plan_integrity import (
        rule_pi_addr_001, rule_pi_index_002, rule_pi_index_003,
        rule_pi_index_004, rule_pi_stamp_001, rule_pi_scale_001,
        rule_pi_north_001,
    )

    all_findings: list[FindingPayload] = []
    with patch(_PATCH, return_value=None):
        for fn in [
            rule_pi_addr_001, rule_pi_index_002, rule_pi_index_003,
            rule_pi_index_004, rule_pi_stamp_001, rule_pi_scale_001,
            rule_pi_north_001,
        ]:
            all_findings.extend(fn(ctx))

    rule_ids = [f.rule_id for f in all_findings]

    # PI-ADDR-001: A-1.1 address mismatch
    assert rule_ids.count("PI-ADDR-001") >= 1

    # PI-INDEX-003: X-9.9 declared but absent
    assert rule_ids.count("PI-INDEX-003") >= 1

    # PI-INDEX-004: A-1.5 title mismatch (SITE PLAN vs FLOOR PLAN)
    assert rule_ids.count("PI-INDEX-004") >= 1

    # PI-STAMP-001: A-1.1, A-1.5, A-3.1, E-1.0(OK), C-1.1(no stamp required)
    stamp_findings = [f for f in all_findings if f.rule_id == "PI-STAMP-001"]
    assert len(stamp_findings) >= 2  # at minimum A-1.1, A-1.5, A-3.1

    # PI-SCALE-001: A-3.1, C-1.1
    scale_findings = [f for f in all_findings if f.rule_id == "PI-SCALE-001"]
    assert len(scale_findings) >= 2

    # PI-NORTH-001: C-1.1
    assert rule_ids.count("PI-NORTH-001") >= 1

    # No duplicates (all canonical IDs are unique in this fixture)
    assert rule_ids.count("PI-INDEX-002") == 0
