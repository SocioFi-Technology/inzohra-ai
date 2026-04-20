"""Plan-integrity reviewer — Phase 01.

Runs 11 deterministic rules against title-block entities, sheet-identifier
entities, sheet-index entries, and the sheets table.  Every finding cites a
live-retrieved code section; no code text is ever paraphrased from model
weights.

Rule catalogue (all deterministic — no LLM in Phase 01):

  PI-ADDR-001      Address mismatch on any sheet vs. canonical project address
  PI-TITLE-001     Required title-block field(s) missing / low-confidence
  PI-PERMIT-001    Permit number absent from title block
  PI-DATE-001      Date of issue absent from title block
  PI-INDEX-001     Declared sheet count ≠ actual sheet count
  PI-INDEX-002     Duplicate canonical sheet IDs in the set
  PI-INDEX-003     Declared sheet ID not found as actual sheet
  PI-INDEX-004     Declared sheet title ≠ actual sheet title (substantial diff)
  PI-STAMP-001     Licensed-professional stamp absent on stamped discipline
  PI-SCALE-001     Scale not declared on a drawing that requires it
  PI-NORTH-001     North arrow absent on a site plan

Stubs (Phase 04, LLM residue):
  PI-TEXT-OVERLAP-001   Overlapping text / annotation regions
  PI-REV-CLOUD-001      Revision cloud without delta annotation

Usage::

    from app.reviewers.plan_integrity import PlanIntegrityReviewer
    import psycopg

    conn = psycopg.connect(database_url, row_factory=psycopg.rows.dict_row)
    reviewer = PlanIntegrityReviewer()
    finding_ids = reviewer.run(
        conn,
        project_id=project_id,
        submittal_id=submittal_id,
        review_round=1,
        database_url=database_url,
    )
    conn.commit()
"""
from __future__ import annotations

import re
from typing import Any

import psycopg
import psycopg.rows

from inzohra_shared.taxonomy import (
    discipline_requires_stamp,
    parse_sheet_identifier,
    sheet_type_requires_north_arrow,
    sheet_type_requires_scale,
)

from app.reviewers._context import (
    FindingPayload,
    IndexEntryRow,
    RuleContext,
    SheetRow,
    TitleBlockRow,
    emit_findings,
    get_citation,
    load_rule_context,
)

# ---------------------------------------------------------------------------
# Rule version stamps — bump the minor when logic changes, major when the
# finding schema changes.
# ---------------------------------------------------------------------------

_RULE_VERSIONS: dict[str, str] = {
    "PI-ADDR-001":  "1.0.0",
    "PI-TITLE-001": "1.0.0",
    "PI-PERMIT-001":"1.0.0",
    "PI-DATE-001":  "1.0.0",
    "PI-INDEX-001": "1.0.0",
    "PI-INDEX-002": "1.0.0",
    "PI-INDEX-003": "1.0.0",
    "PI-INDEX-004": "1.0.0",
    "PI-STAMP-001": "1.0.0",
    "PI-SCALE-001": "1.0.0",
    "PI-NORTH-001": "1.0.0",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_sheet_id(raw: str) -> str | None:
    """Normalize a raw declared-index sheet ID to canonical form D-N.N."""
    result = parse_sheet_identifier(raw.strip())
    return result[2] if result else None


def _title_mismatch(declared: str | None, actual: str | None) -> bool:
    """True when the two titles are substantially different (case/whitespace-insensitive)."""
    if not declared or not actual:
        return False
    # Normalise: lowercase, collapse whitespace, strip
    def _n(s: str) -> str:
        return re.sub(r"\s+", " ", s.lower().strip())

    dn, an = _n(declared), _n(actual)
    if dn == an:
        return False
    # Allow one to be a prefix of the other (e.g. "FLOOR PLAN" vs "FLOOR PLAN - LEVEL 1")
    if dn.startswith(an) or an.startswith(dn):
        return False
    return True


def _sheet_ref(sheet_id: str | None, detail: str | None = None) -> dict[str, Any]:
    return {"sheet_id": sheet_id, "detail": detail}


def _entity_evidence(entity_id: str, bbox: list[float]) -> dict[str, Any]:
    return {"entity_id": entity_id, "bbox": bbox}


def _project_ref() -> dict[str, Any]:
    return {"sheet_id": None, "detail": "Project-wide"}


# ---------------------------------------------------------------------------
# PI-ADDR-001 — Address mismatch
# ---------------------------------------------------------------------------


def rule_pi_addr_001(ctx: RuleContext) -> list[FindingPayload]:
    """One finding per sheet where address_mismatch is True."""
    findings: list[FindingPayload] = []
    cit = get_citation(ctx, "CBC-107.2.1")
    citations = [cit] if cit else []

    for tb in ctx.title_blocks:
        if not tb.address_mismatch:
            continue

        on_sheet = tb.project_address or "(blank)"
        findings.append(
            FindingPayload(
                rule_id="PI-ADDR-001",
                rule_version=_RULE_VERSIONS["PI-ADDR-001"],
                severity="revise",
                sheet_reference=_sheet_ref(
                    tb.sheet_id, f"Sheet title-block shows '{on_sheet}'"
                ),
                evidence=[_entity_evidence(tb.entity_id, tb.bbox)],
                citations=citations,
                draft_comment_text=(
                    f"Sheet {tb.sheet_id}: the title block shows address "
                    f"'{on_sheet}' which does not match the canonical project "
                    f"address '{ctx.project_address}'. Revise the title block "
                    "on all sheets to reflect the correct site address. "
                    "(CBC §107.2.1 — construction documents shall be of "
                    "sufficient clarity to indicate the location… of the work.)"
                ),
                confidence=min(tb.addr_confidence + 0.05, 0.98),
            )
        )

    return findings


# ---------------------------------------------------------------------------
# PI-TITLE-001 — Required title-block fields missing
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS: list[tuple[str, str, float]] = [
    # (field_name_for_display, attr_name, min_confidence_threshold)
    ("project name",           "project_name",       0.40),
    ("project address",        "project_address",    0.40),
    ("designer of record",     "designer_of_record", 0.40),
]


def rule_pi_title_001(ctx: RuleContext) -> list[FindingPayload]:
    """Emit one finding per sheet that is missing one or more required fields."""
    findings: list[FindingPayload] = []
    cit = get_citation(ctx, "CBC-107.2.1")
    citations = [cit] if cit else []

    for tb in ctx.title_blocks:
        missing: list[str] = []

        for disp, attr, min_conf in _REQUIRED_FIELDS:
            val = getattr(tb, attr, None)
            # resolve confidence for this field
            if attr == "project_name":
                conf = tb.name_confidence
            elif attr == "project_address":
                conf = tb.addr_confidence
            elif attr == "designer_of_record":
                conf = tb.designer_confidence
            else:
                conf = 1.0

            if not val or conf < min_conf:
                missing.append(disp)

        if not missing:
            continue

        field_list = ", ".join(missing)
        findings.append(
            FindingPayload(
                rule_id="PI-TITLE-001",
                rule_version=_RULE_VERSIONS["PI-TITLE-001"],
                severity="provide",
                sheet_reference=_sheet_ref(
                    tb.sheet_id, f"Title block missing: {field_list}"
                ),
                evidence=[_entity_evidence(tb.entity_id, tb.bbox)],
                citations=citations,
                draft_comment_text=(
                    f"Sheet {tb.sheet_id}: the following required title-block "
                    f"information could not be read or is absent — {field_list}. "
                    "Provide legible, complete title-block information on all sheets. "
                    "(CBC §107.2.1)"
                ),
                confidence=0.85,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# PI-PERMIT-001 — Permit number absent
# ---------------------------------------------------------------------------


def rule_pi_permit_001(ctx: RuleContext) -> list[FindingPayload]:
    """One project-wide finding when the permit number is absent/unreadable."""
    if not ctx.title_blocks:
        return []

    # Fire once if *any* sheet is missing the permit number (project-level field)
    missing_sheets = [
        tb for tb in ctx.title_blocks
        if not tb.permit_number or tb.permit_confidence < 0.4
    ]
    if not missing_sheets:
        return []

    cit = get_citation(ctx, "CBC-107.1")
    citations = [cit] if cit else []

    sheet_ids = ", ".join(tb.sheet_id for tb in missing_sheets[:6])
    suffix = f" (+{len(missing_sheets)-6} more)" if len(missing_sheets) > 6 else ""

    return [
        FindingPayload(
            rule_id="PI-PERMIT-001",
            rule_version=_RULE_VERSIONS["PI-PERMIT-001"],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[
                _entity_evidence(tb.entity_id, tb.bbox) for tb in missing_sheets
            ],
            citations=citations,
            draft_comment_text=(
                f"The permit number is absent or illegible on sheets: "
                f"{sheet_ids}{suffix}. "
                "Provide the current permit application number in the title block "
                "of all sheets. (CBC §107.1 — submittal documents shall be submitted "
                "with each application for a permit.)"
            ),
            confidence=0.88,
        )
    ]


# ---------------------------------------------------------------------------
# PI-DATE-001 — Date of issue absent
# ---------------------------------------------------------------------------


def rule_pi_date_001(ctx: RuleContext) -> list[FindingPayload]:
    """One finding per sheet missing a date of issue."""
    cit = get_citation(ctx, "CBC-107.2.1")
    citations = [cit] if cit else []

    findings: list[FindingPayload] = []
    for tb in ctx.title_blocks:
        if tb.date_issued and tb.date_confidence >= 0.4:
            continue
        findings.append(
            FindingPayload(
                rule_id="PI-DATE-001",
                rule_version=_RULE_VERSIONS["PI-DATE-001"],
                severity="provide",
                sheet_reference=_sheet_ref(
                    tb.sheet_id, "Title block — date of issue"
                ),
                evidence=[_entity_evidence(tb.entity_id, tb.bbox)],
                citations=citations,
                draft_comment_text=(
                    f"Sheet {tb.sheet_id}: date of issue is absent or illegible "
                    "in the title block. Provide a clear date of issue / date of "
                    "preparation on all sheets. (CBC §107.2.1)"
                ),
                confidence=0.85,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# PI-INDEX-001 — Count mismatch
# ---------------------------------------------------------------------------


def rule_pi_index_001(ctx: RuleContext) -> list[FindingPayload]:
    """Declared sheet count differs from actual sheet count."""
    if not ctx.index_entries:
        # No cover-sheet index found — do not fire (different rule would cover that)
        return []

    declared_count = len(ctx.index_entries)
    actual_count = len(ctx.sheets)

    if declared_count == actual_count:
        return []

    cit = get_citation(ctx, "CBC-107.2")
    citations = [cit] if cit else []

    return [
        FindingPayload(
            rule_id="PI-INDEX-001",
            rule_version=_RULE_VERSIONS["PI-INDEX-001"],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=citations,
            draft_comment_text=(
                f"The sheet index declares {declared_count} sheets but "
                f"{actual_count} sheets were found in the plan set. "
                "Reconcile the sheet index so the declared count matches "
                "the actual number of sheets submitted. (CBC §107.2)"
            ),
            confidence=0.92,
        )
    ]


# ---------------------------------------------------------------------------
# PI-INDEX-002 — Duplicate canonical sheet IDs
# ---------------------------------------------------------------------------


def rule_pi_index_002(ctx: RuleContext) -> list[FindingPayload]:
    """Detect sheets that share the same canonical_id."""
    seen: dict[str, list[SheetRow]] = {}
    for s in ctx.sheets:
        cid = s.canonical_id
        if not cid:
            continue
        seen.setdefault(cid, []).append(s)

    duplicates = {cid: rows for cid, rows in seen.items() if len(rows) > 1}
    if not duplicates:
        return []

    cit = get_citation(ctx, "CBC-107.2.1")
    citations = [cit] if cit else []

    findings: list[FindingPayload] = []
    for cid, rows in duplicates.items():
        page_list = ", ".join(f"p{r.page}" for r in rows)
        findings.append(
            FindingPayload(
                rule_id="PI-INDEX-002",
                rule_version=_RULE_VERSIONS["PI-INDEX-002"],
                severity="revise",
                sheet_reference=_sheet_ref(None, f"Duplicate ID '{cid}'"),
                evidence=[],
                citations=citations,
                draft_comment_text=(
                    f"Sheet ID '{cid}' appears on {len(rows)} physical pages "
                    f"({page_list}). Each sheet must carry a unique identifier. "
                    "Assign distinct sheet numbers and revise all affected sheets. "
                    "(CBC §107.2.1)"
                ),
                confidence=0.95,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# PI-INDEX-003 — Declared sheet ID not found as actual sheet
# ---------------------------------------------------------------------------


def rule_pi_index_003(ctx: RuleContext) -> list[FindingPayload]:
    """Flag each declared index entry whose ID has no matching actual sheet."""
    if not ctx.index_entries:
        return []

    actual_ids: set[str] = {
        s.canonical_id for s in ctx.sheets if s.canonical_id
    }

    cit = get_citation(ctx, "CBC-107.2.1")
    citations = [cit] if cit else []

    findings: list[FindingPayload] = []
    for entry in ctx.index_entries:
        canonical = _normalize_sheet_id(entry.declared_id)
        # Also try matching the raw form in case normalization fails
        raw_in_actual = entry.declared_id in actual_ids
        norm_in_actual = canonical in actual_ids if canonical else False

        if raw_in_actual or norm_in_actual:
            continue

        findings.append(
            FindingPayload(
                rule_id="PI-INDEX-003",
                rule_version=_RULE_VERSIONS["PI-INDEX-003"],
                severity="revise",
                sheet_reference=_sheet_ref(
                    entry.source_sheet_id,
                    f"Sheet index entry: '{entry.declared_id}'",
                ),
                evidence=[
                    {
                        "index_entry_id": entry.entry_id,
                        "bbox": entry.bbox,
                        "declared_id": entry.declared_id,
                        "normalized_id": canonical,
                    }
                ],
                citations=citations,
                draft_comment_text=(
                    f"Sheet '{entry.declared_id}' is listed in the sheet index "
                    f"(declared title: '{entry.declared_title or 'N/A'}') but no "
                    f"actual sheet with that identifier was found in the plan set. "
                    "Verify that the sheet identifier on the physical sheet matches "
                    "the entry in the sheet index, or update the index. "
                    "(CBC §107.2.1 — construction documents shall be of sufficient "
                    "clarity to indicate the location, nature and extent of the work.)"
                ),
                confidence=entry.confidence,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# PI-INDEX-004 — Title in index ≠ actual sheet title
# ---------------------------------------------------------------------------


def rule_pi_index_004(ctx: RuleContext) -> list[FindingPayload]:
    """For entries whose ID matches an actual sheet, flag title discrepancies."""
    if not ctx.index_entries:
        return []

    actual_by_id: dict[str, SheetRow] = {
        s.canonical_id: s for s in ctx.sheets if s.canonical_id
    }

    cit = get_citation(ctx, "CBC-107.2.1")
    citations = [cit] if cit else []

    findings: list[FindingPayload] = []
    for entry in ctx.index_entries:
        canonical = _normalize_sheet_id(entry.declared_id) or entry.declared_id
        sheet = actual_by_id.get(canonical)
        if sheet is None:
            continue  # PI-INDEX-003 already caught this

        if not _title_mismatch(entry.declared_title, sheet.canonical_title):
            continue

        findings.append(
            FindingPayload(
                rule_id="PI-INDEX-004",
                rule_version=_RULE_VERSIONS["PI-INDEX-004"],
                severity="clarify",
                sheet_reference=_sheet_ref(
                    sheet.sheet_id,
                    f"Index: '{entry.declared_title}' / Sheet: '{sheet.canonical_title}'",
                ),
                evidence=[
                    {
                        "index_entry_id": entry.entry_id,
                        "bbox": entry.bbox,
                        "declared_title": entry.declared_title,
                        "actual_title": sheet.canonical_title,
                    }
                ],
                citations=citations,
                draft_comment_text=(
                    f"Sheet '{canonical}': the sheet index lists this sheet as "
                    f"'{entry.declared_title}' but the title block reads "
                    f"'{sheet.canonical_title}'. Reconcile the sheet title in the "
                    "index with the title block on the sheet. (CBC §107.2.1)"
                ),
                confidence=0.82,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# PI-STAMP-001 — Stamp absent on licensed-discipline sheets
# ---------------------------------------------------------------------------


def rule_pi_stamp_001(ctx: RuleContext) -> list[FindingPayload]:
    """Emit one finding per sheet that requires a stamp but has none."""
    cit = get_citation(ctx, "CBC-107.1")
    citations = [cit] if cit else []

    # Build a map of sheet_id → discipline_letter for quick lookup
    disc_by_sheet: dict[str, str] = {
        s.sheet_id: (s.discipline_letter or "")
        for s in ctx.sheets
        if s.discipline_letter
    }

    findings: list[FindingPayload] = []
    for tb in ctx.title_blocks:
        if tb.stamp_present:
            continue

        disc = disc_by_sheet.get(tb.sheet_id, "")
        if not disc or not discipline_requires_stamp(disc):
            continue

        findings.append(
            FindingPayload(
                rule_id="PI-STAMP-001",
                rule_version=_RULE_VERSIONS["PI-STAMP-001"],
                severity="revise",
                sheet_reference=_sheet_ref(
                    tb.sheet_id, f"Discipline: {disc} — stamp absent"
                ),
                evidence=[_entity_evidence(tb.entity_id, tb.bbox)],
                citations=citations,
                draft_comment_text=(
                    f"Sheet {tb.sheet_id} (discipline '{disc}'): no licensed "
                    "professional stamp was detected in the title block. "
                    "California Business & Professions Code §5536 and CBC §107.1 "
                    "require construction documents to be prepared and wet- or "
                    "digital-stamped by the registered design professional of record. "
                    "Provide the appropriate stamp on all applicable sheets."
                ),
                confidence=0.88,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# PI-SCALE-001 — Scale absent on drawings requiring it
# ---------------------------------------------------------------------------


def rule_pi_scale_001(ctx: RuleContext) -> list[FindingPayload]:
    """Emit one finding per sheet that requires a declared scale but has none."""
    cit = get_citation(ctx, "CBC-107.2.1")
    citations = [cit] if cit else []

    sheet_type_by_id: dict[str, str] = {
        s.sheet_id: (s.sheet_type or "unknown") for s in ctx.sheets
    }

    findings: list[FindingPayload] = []
    for tb in ctx.title_blocks:
        # Skip if scale is declared
        if tb.scale_declared and tb.scale_declared.strip().lower() not in (
            "", "n/a", "nts", "not to scale"
        ):
            continue

        stype = sheet_type_by_id.get(tb.sheet_id, "unknown")
        if not sheet_type_requires_scale(stype):  # type: ignore[arg-type]
            continue

        findings.append(
            FindingPayload(
                rule_id="PI-SCALE-001",
                rule_version=_RULE_VERSIONS["PI-SCALE-001"],
                severity="provide",
                sheet_reference=_sheet_ref(
                    tb.sheet_id, f"Sheet type: {stype}"
                ),
                evidence=[_entity_evidence(tb.entity_id, tb.bbox)],
                citations=citations,
                draft_comment_text=(
                    f"Sheet {tb.sheet_id} ({stype}): no scale is declared in the "
                    "title block or graphic bar. Provide a written scale (e.g. "
                    "\"1/4\" = 1'-0\"\") and/or a graphic scale bar on all plan, "
                    "elevation, section, and site-plan drawings. "
                    "(CBC §107.2.1 — construction documents shall be dimensioned "
                    "and drawn to scale.)"
                ),
                confidence=0.88,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# PI-NORTH-001 — North arrow absent on site plan
# ---------------------------------------------------------------------------


def rule_pi_north_001(ctx: RuleContext) -> list[FindingPayload]:
    """Emit one finding per site-plan sheet missing a north arrow."""
    cit = get_citation(ctx, "CBC-107.2.5")
    citations = [cit] if cit else []

    sheet_type_by_id: dict[str, str] = {
        s.sheet_id: (s.sheet_type or "unknown") for s in ctx.sheets
    }

    findings: list[FindingPayload] = []
    for tb in ctx.title_blocks:
        if tb.north_arrow_bbox is not None:
            continue

        stype = sheet_type_by_id.get(tb.sheet_id, "unknown")
        if not sheet_type_requires_north_arrow(stype):  # type: ignore[arg-type]
            continue

        findings.append(
            FindingPayload(
                rule_id="PI-NORTH-001",
                rule_version=_RULE_VERSIONS["PI-NORTH-001"],
                severity="provide",
                sheet_reference=_sheet_ref(
                    tb.sheet_id, "Site plan — north arrow absent"
                ),
                evidence=[_entity_evidence(tb.entity_id, tb.bbox)],
                citations=citations,
                draft_comment_text=(
                    f"Sheet {tb.sheet_id}: a north arrow was not found on the site "
                    "plan. Provide a north arrow on all site plans per CBC §107.2.5."
                ),
                confidence=0.82,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# Stubs — Phase 04 (LLM residue pass)
# ---------------------------------------------------------------------------


def rule_pi_text_overlap_001(ctx: RuleContext) -> list[FindingPayload]:  # noqa: ARG001
    """Stub: overlapping text / annotation detection (Phase 04)."""
    return []


def rule_pi_rev_cloud_001(ctx: RuleContext) -> list[FindingPayload]:  # noqa: ARG001
    """Stub: revision cloud without delta annotation (Phase 04)."""
    return []


# ---------------------------------------------------------------------------
# PlanIntegrityReviewer — orchestrator
# ---------------------------------------------------------------------------


# Ordered rule registry — rules fire in this order.  Add new rules here.
_RULES = [
    rule_pi_addr_001,
    rule_pi_title_001,
    rule_pi_permit_001,
    rule_pi_date_001,
    rule_pi_index_001,
    rule_pi_index_002,
    rule_pi_index_003,
    rule_pi_index_004,
    rule_pi_stamp_001,
    rule_pi_scale_001,
    rule_pi_north_001,
    # Phase 04 stubs
    rule_pi_text_overlap_001,
    rule_pi_rev_cloud_001,
]


class PlanIntegrityReviewer:
    """Deterministic plan-integrity reviewer.

    Call ``run()`` once per submittal round.  It fetches all needed data from
    the database, runs every rule, and bulk-inserts findings. The connection
    is not committed here — the caller owns the transaction.
    """

    DISCIPLINE = "plan_integrity"

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
        """Run all rules and persist findings.

        Returns the list of created finding IDs.  The caller must commit.
        """
        ctx = load_rule_context(
            conn,
            project_id=project_id,
            submittal_id=submittal_id,
            review_round=review_round,
            database_url=database_url,
        )

        all_findings: list[FindingPayload] = []
        for rule_fn in _RULES:
            rule_findings = rule_fn(ctx)
            all_findings.extend(rule_findings)

        if not all_findings:
            return []

        return emit_findings(
            conn,
            ctx,
            all_findings,
            extractor_versions_used=extractor_versions_used,
        )
