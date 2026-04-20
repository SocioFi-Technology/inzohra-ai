"""Reviewer context: fetched project data + emit helpers.

``RuleContext`` is the single object passed to every rule function.  It is
populated once via ``load_rule_context()`` before any rule runs, and carries
all DB-sourced data the plan-integrity rules need so rules are pure functions
(no additional DB round-trips required; the KB lookup is the sole exception).

``emit_findings()`` bulk-inserts the accumulated finding payloads produced by
all rules into the ``findings`` table.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from app.codekb.tools import Citation, lookup_canonical


# ---------------------------------------------------------------------------
# Typed row objects (mirrors DB columns we actually use)
# ---------------------------------------------------------------------------


@dataclass
class TitleBlockRow:
    entity_id: str
    sheet_id: str
    page: int
    bbox: list[float]
    # decoded from entities.payload
    project_address: str | None
    address_mismatch: bool
    stamp_present: bool
    scale_declared: str | None
    north_arrow_bbox: list[float] | None
    permit_number: str | None
    date_issued: str | None
    project_name: str | None
    designer_of_record: str | None
    sheet_title: str | None
    # field-level confidences (0 means absent/unknown)
    addr_confidence: float
    permit_confidence: float
    date_confidence: float
    name_confidence: float
    designer_confidence: float
    # overall entity
    confidence: float
    extractor_version: str


@dataclass
class SheetRow:
    sheet_id: str
    page: int
    canonical_id: str | None
    discipline_letter: str | None
    sheet_type: str | None
    canonical_title: str | None
    sheet_identifier_confidence: float | None


@dataclass
class IndexEntryRow:
    entry_id: str
    declared_id: str
    declared_title: str | None
    bbox: list[float]
    source_sheet_id: str
    confidence: float


@dataclass
class FloorPlanEntityRow:
    entity_id: str
    sheet_id: str
    page: int
    entity_type: str          # "door" | "window" | "room" | "stair" | "exit"
    tag: str | None
    room_label: str | None
    room_use: str | None
    bbox: list[float]
    confidence: float
    geometry_notes: str | None
    schedule_ref: str | None


@dataclass
class MeasurementRow:
    measurement_id: str
    sheet_id: str
    type: str                 # "door_clear_width" | "window_nco" | "room_area" | "egress_distance"
    value: float
    unit: str
    confidence: float
    tag: str | None
    entity_id: str | None
    bbox: list[float] | None


# ---------------------------------------------------------------------------
# FindingPayload — the structured record each rule returns
# ---------------------------------------------------------------------------


@dataclass
class FindingPayload:
    rule_id: str
    rule_version: str
    severity: str  # 'revise' | 'provide' | 'clarify' | 'reference_only'
    sheet_reference: dict[str, Any]
    evidence: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    draft_comment_text: str
    confidence: float = 0.9
    requires_licensed_review: bool = False
    llm_reasoner_id: str | None = None
    prompt_hash: str | None = None


# ---------------------------------------------------------------------------
# RuleContext
# ---------------------------------------------------------------------------


@dataclass
class RuleContext:
    """All data needed by plan-integrity rules, fetched once."""

    project_id: str
    submittal_id: str
    review_round: int
    jurisdiction: str
    effective_date: str   # ISO date string (e.g. "2025-01-01")
    project_address: str  # canonical address from projects table
    database_url: str     # for Code-KB lookups (same DB)

    sheets: list[SheetRow] = field(default_factory=list)
    title_blocks: list[TitleBlockRow] = field(default_factory=list)
    index_entries: list[IndexEntryRow] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Context loader
# ---------------------------------------------------------------------------


def load_rule_context(
    conn: psycopg.Connection,  # type: ignore[type-arg]
    *,
    project_id: str,
    submittal_id: str,
    review_round: int,
    database_url: str,
) -> RuleContext:
    """Fetch all data needed by plan-integrity rules in one pass."""

    # --- project metadata ---
    proj = conn.execute(
        "SELECT address, jurisdiction, effective_date FROM projects WHERE project_id = %s",
        (project_id,),
    ).fetchone()
    if proj is None:
        raise ValueError(f"project {project_id!r} not found")

    ctx = RuleContext(
        project_id=project_id,
        submittal_id=submittal_id,
        review_round=review_round,
        jurisdiction=str(proj["jurisdiction"]),
        effective_date=str(proj["effective_date"]),
        project_address=str(proj["address"]),
        database_url=database_url,
    )

    # --- sheets ---
    sheet_rows = conn.execute(
        """SELECT sheet_id, page, canonical_id, discipline_letter, sheet_type,
                  canonical_title, sheet_identifier_confidence
             FROM sheets
            WHERE project_id = %s
            ORDER BY page""",
        (project_id,),
    ).fetchall()
    for r in sheet_rows:
        ctx.sheets.append(
            SheetRow(
                sheet_id=str(r["sheet_id"]),
                page=int(r["page"]),
                canonical_id=r.get("canonical_id"),
                discipline_letter=r.get("discipline_letter"),
                sheet_type=r.get("sheet_type"),
                canonical_title=r.get("canonical_title"),
                sheet_identifier_confidence=r.get("sheet_identifier_confidence"),
            )
        )

    # --- title_block entities ---
    tb_rows = conn.execute(
        """SELECT entity_id, sheet_id, page, bbox, confidence, extractor_version,
                  payload
             FROM entities
            WHERE project_id = %s AND type = 'title_block'
            ORDER BY page""",
        (project_id,),
    ).fetchall()
    for r in tb_rows:
        p = r["payload"] or {}
        addr_f = p.get("project_address") or {}
        permit_f = p.get("permit_number") or {}
        date_f = p.get("date_issued") or {}
        name_f = p.get("project_name") or {}
        designer_f = p.get("designer_of_record") or {}
        sheet_title_f = p.get("sheet_title") or {}
        ctx.title_blocks.append(
            TitleBlockRow(
                entity_id=str(r["entity_id"]),
                sheet_id=str(r["sheet_id"]),
                page=int(r["page"]),
                bbox=list(r["bbox"] or [0, 0, 0, 0]),
                project_address=addr_f.get("value"),
                address_mismatch=bool(p.get("address_mismatch", False)),
                stamp_present=bool(p.get("stamp_present", False)),
                scale_declared=(
                    (p.get("scale_declared") or {}).get("value")
                ),
                north_arrow_bbox=p.get("north_arrow_bbox"),
                permit_number=permit_f.get("value"),
                date_issued=date_f.get("value"),
                project_name=name_f.get("value"),
                designer_of_record=designer_f.get("value"),
                sheet_title=sheet_title_f.get("value"),
                addr_confidence=float(addr_f.get("confidence", 0.0)),
                permit_confidence=float(permit_f.get("confidence", 0.0)),
                date_confidence=float(date_f.get("confidence", 0.0)),
                name_confidence=float(name_f.get("confidence", 0.0)),
                designer_confidence=float(designer_f.get("confidence", 0.0)),
                confidence=float(r["confidence"]),
                extractor_version=str(r["extractor_version"]),
            )
        )

    # --- sheet index entries ---
    idx_rows = conn.execute(
        """SELECT entry_id, declared_id, declared_title, bbox, source_sheet_id, confidence
             FROM sheet_index_entries
            WHERE project_id = %s
            ORDER BY entry_id""",
        (project_id,),
    ).fetchall()
    for r in idx_rows:
        ctx.index_entries.append(
            IndexEntryRow(
                entry_id=str(r["entry_id"]),
                declared_id=str(r["declared_id"]),
                declared_title=r.get("declared_title"),
                bbox=list(r["bbox"] or [0, 0, 0, 0]),
                source_sheet_id=str(r["source_sheet_id"]),
                confidence=float(r["confidence"]),
            )
        )

    return ctx


# ---------------------------------------------------------------------------
# Citation helper
# ---------------------------------------------------------------------------


def get_citation(ctx: RuleContext, canonical_id: str) -> dict[str, Any] | None:
    """Retrieve a code section from the KB and return a finding-citation dict.

    Returns ``None`` if the section is not found (should never happen for the
    seed sections, but we must not hallucinate if retrieval fails).
    """
    cit: Citation | None = lookup_canonical(
        ctx.database_url,
        canonical_id=canonical_id,
        jurisdiction=ctx.jurisdiction,
        effective_date=ctx.effective_date,
    )
    if cit is None:
        return None
    return cit.to_finding_citation()


# ---------------------------------------------------------------------------
# Emit helper
# ---------------------------------------------------------------------------


def emit_findings(
    conn: psycopg.Connection,  # type: ignore[type-arg]
    ctx: RuleContext,
    findings: list[FindingPayload],
    extractor_versions_used: list[str] | None = None,
) -> list[str]:
    """Bulk-insert finding payloads into the ``findings`` table.

    Returns the list of inserted ``finding_id`` UUIDs.
    """
    ext_versions = extractor_versions_used or []
    finding_ids: list[str] = []

    for fp in findings:
        fid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO findings (
                finding_id, project_id, submittal_id, review_round,
                discipline, rule_id, rule_version,
                llm_reasoner_id, prompt_hash,
                severity, requires_licensed_review,
                sheet_reference, evidence, citations,
                draft_comment_text, confidence,
                extractor_versions_used
               ) VALUES (
                %s, %s, %s, %s,
                'plan_integrity', %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s,
                %s
               )""",
            (
                fid,
                ctx.project_id,
                ctx.submittal_id,
                ctx.review_round,
                fp.rule_id,
                fp.rule_version,
                fp.llm_reasoner_id,
                fp.prompt_hash,
                fp.severity,
                fp.requires_licensed_review,
                Jsonb(fp.sheet_reference),
                Jsonb(fp.evidence),
                Jsonb(fp.citations),
                fp.draft_comment_text,
                fp.confidence,
                ext_versions,
            ),
        )
        finding_ids.append(fid)

    return finding_ids


# ---------------------------------------------------------------------------
# Phase-04: ArchAccessRuleContext + loaders + helpers
# ---------------------------------------------------------------------------


@dataclass
class ArchAccessRuleContext:
    """Superset of RuleContext plus measurement data for Arch + Access reviewers."""

    # core — copy of RuleContext fields
    project_id: str
    submittal_id: str
    review_round: int
    jurisdiction: str
    effective_date: str
    project_address: str
    database_url: str
    sheets: list[SheetRow] = field(default_factory=list)
    title_blocks: list[TitleBlockRow] = field(default_factory=list)
    index_entries: list[IndexEntryRow] = field(default_factory=list)
    # phase-04 additions
    floor_plan_entities: list[FloorPlanEntityRow] = field(default_factory=list)
    measurements: list[MeasurementRow] = field(default_factory=list)

    @property
    def rooms(self) -> list[FloorPlanEntityRow]:
        return [e for e in self.floor_plan_entities if e.entity_type == "room"]

    @property
    def doors(self) -> list[FloorPlanEntityRow]:
        return [e for e in self.floor_plan_entities if e.entity_type == "door"]

    @property
    def windows(self) -> list[FloorPlanEntityRow]:
        return [e for e in self.floor_plan_entities if e.entity_type == "window"]

    @property
    def bedroom_rooms(self) -> list[FloorPlanEntityRow]:
        return [e for e in self.floor_plan_entities if e.room_use == "bedroom"]


def load_arch_access_context(
    conn: psycopg.Connection,  # type: ignore[type-arg]
    *,
    project_id: str,
    submittal_id: str,
    review_round: int,
    database_url: str,
) -> ArchAccessRuleContext:
    """Load RuleContext + floor plan entities + measurements."""
    base = load_rule_context(
        conn,
        project_id=project_id,
        submittal_id=submittal_id,
        review_round=review_round,
        database_url=database_url,
    )
    ctx = ArchAccessRuleContext(
        project_id=base.project_id,
        submittal_id=base.submittal_id,
        review_round=base.review_round,
        jurisdiction=base.jurisdiction,
        effective_date=base.effective_date,
        project_address=base.project_address,
        database_url=base.database_url,
        sheets=base.sheets,
        title_blocks=base.title_blocks,
        index_entries=base.index_entries,
    )

    # floor plan entities
    fp_rows = conn.execute(
        """SELECT entity_id, sheet_id, page, payload, confidence
             FROM entities
            WHERE project_id = %s AND type = 'floor_plan_entity'
            ORDER BY page""",
        (project_id,),
    ).fetchall()
    for r in fp_rows:
        p = r["payload"] or {}
        ctx.floor_plan_entities.append(
            FloorPlanEntityRow(
                entity_id=str(r["entity_id"]),
                sheet_id=str(r["sheet_id"]),
                page=int(r["page"]),
                entity_type=p.get("entity_type", "unknown"),
                tag=p.get("tag"),
                room_label=p.get("room_label"),
                room_use=p.get("room_use"),
                bbox=list(p.get("bbox") or [0, 0, 0, 0]),
                confidence=float(r["confidence"]),
                geometry_notes=p.get("geometry_notes"),
                schedule_ref=p.get("schedule_ref"),
            )
        )

    # measurements
    m_rows = conn.execute(
        """SELECT measurement_id, sheet_id, type, value, unit, confidence,
                  tag, entity_id, bbox
             FROM measurements
            WHERE project_id = %s
            ORDER BY type, tag""",
        (project_id,),
    ).fetchall()
    for r in m_rows:
        ctx.measurements.append(
            MeasurementRow(
                measurement_id=str(r["measurement_id"]),
                sheet_id=str(r["sheet_id"]),
                type=str(r["type"]),
                value=float(r["value"]),
                unit=str(r["unit"]),
                confidence=float(r["confidence"]),
                tag=r.get("tag"),
                entity_id=str(r["entity_id"]) if r.get("entity_id") else None,
                bbox=list(r["bbox"]) if r.get("bbox") else None,
            )
        )

    return ctx


def get_citation_aa(
    ctx: ArchAccessRuleContext,
    canonical_id: str,
) -> dict[str, Any] | None:
    """Retrieve a code section from the KB for an ArchAccessRuleContext.

    Returns ``None`` if the section is not found.
    """
    cit: Citation | None = lookup_canonical(
        ctx.database_url,
        canonical_id=canonical_id,
        jurisdiction=ctx.jurisdiction,
        effective_date=ctx.effective_date,
    )
    if cit is None:
        return None
    return cit.to_finding_citation()


def emit_findings_aa(
    conn: psycopg.Connection,  # type: ignore[type-arg]
    ctx: ArchAccessRuleContext,
    findings: list[FindingPayload],
    discipline: str,
    extractor_versions_used: list[str] | None = None,
) -> list[str]:
    """Bulk-insert findings from an ArchAccessRuleContext.

    Same logic as ``emit_findings`` but ``discipline`` is a caller parameter
    (not hardcoded to ``'plan_integrity'``).

    Returns the list of inserted ``finding_id`` UUIDs.
    """
    ext_versions = extractor_versions_used or []
    finding_ids: list[str] = []
    for fp in findings:
        fid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO findings (
                finding_id, project_id, submittal_id, review_round,
                discipline, rule_id, rule_version,
                llm_reasoner_id, prompt_hash,
                severity, requires_licensed_review,
                sheet_reference, evidence, citations,
                draft_comment_text, confidence,
                extractor_versions_used
               ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s,
                %s
               )""",
            (
                fid,
                ctx.project_id,
                ctx.submittal_id,
                ctx.review_round,
                discipline,
                fp.rule_id,
                fp.rule_version,
                fp.llm_reasoner_id,
                fp.prompt_hash,
                fp.severity,
                fp.requires_licensed_review,
                Jsonb(fp.sheet_reference),
                Jsonb(fp.evidence),
                Jsonb(fp.citations),
                fp.draft_comment_text,
                fp.confidence,
                ext_versions,
            ),
        )
        finding_ids.append(fid)
    return finding_ids
