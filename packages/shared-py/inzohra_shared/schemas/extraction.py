"""Pydantic schemas for extraction outputs.

Every field that was extracted from a document carries a bbox (in PDF points,
origin top-left), confidence, and source_track. This is invariant #1 —
provenance is sacred.
"""
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field


SourceTrack = Literal["text", "vision", "merged"]


class BBoxField(BaseModel):
    """A single extracted field with provenance."""

    value: str | None = None
    bbox: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    confidence: float = Field(ge=0.0, le=1.0)
    source_track: SourceTrack = "text"

    # When text and vision disagree, both raw values are stored here.
    text_raw: str | None = None
    vision_raw: str | None = None


class TitleBlockExtraction(BaseModel):
    """Structured output of TitleBlockAgent.

    All bbox coordinates are in PDF points (1/72 inch), origin at top-left
    of the page (PyMuPDF coordinate system).
    """

    VERSION: ClassVar[str] = "1.0.0"

    # Core identification
    project_name: BBoxField
    project_address: BBoxField
    apn: BBoxField
    permit_number: BBoxField

    # Sheet identification
    sheet_identifier_raw: BBoxField  # e.g. "A-1.1"
    sheet_title: BBoxField            # e.g. "FLOOR PLAN"

    # Design team
    designer_of_record: BBoxField
    stamp_present: bool = False

    # Dates / scale
    date_issued: BBoxField
    scale_declared: BBoxField  # e.g. "1/4\" = 1'-0\""

    # Optional — north arrow bounding box (None if not found)
    north_arrow_bbox: list[float] | None = None

    # Address mismatch flag — set True when this sheet's address differs
    # from the canonical project address (catches "1966 Dennis Ln" bug).
    address_mismatch: bool = False

    def to_entity_payload(self) -> dict:  # type: ignore[type-arg]
        """Serialise for the ``entities.payload`` JSONB column."""
        return self.model_dump()


class SheetIdentifier(BaseModel):
    """Structured output of SheetIdentifierParser.

    Derived deterministically from ``TitleBlockExtraction.sheet_identifier_raw``
    plus the declared / inferred sheet title.
    """

    VERSION: ClassVar[str] = "1.0.0"

    raw_id: str | None                    # what the title block actually said
    canonical_id: str | None              # normalised (e.g. "A-1.1")
    discipline_letter: str | None         # "A", "S", "E", ...
    sheet_number: str | None              # "1.1"
    sheet_type: str                        # e.g. "floor_plan" (see taxonomy)
    sheet_title: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])

    def to_entity_payload(self) -> dict:  # type: ignore[type-arg]
        return self.model_dump()


class SheetIndexEntry(BaseModel):
    """A single row extracted from a cover-sheet sheet-index table."""

    declared_id: str
    declared_title: str | None = None
    bbox: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)


class SheetIndex(BaseModel):
    """Full declared sheet-index from the cover sheet."""

    VERSION: ClassVar[str] = "1.0.0"

    source_sheet_id: str                   # which sheet this index came from
    entries: list[SheetIndexEntry]
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)

    def to_entity_payload(self) -> dict:  # type: ignore[type-arg]
        return self.model_dump()


# ---------------------------------------------------------------------------
# Phase 02 — Schedule extraction
# ---------------------------------------------------------------------------

class ScheduleRow(BaseModel):
    """A single data row extracted from any schedule table."""
    row_index: int
    tag: str | None = None                  # MARK / TAG column value
    cells: dict[str, str | None]            # { header_name: cell_value }
    bbox: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)


class DoorScheduleRow(ScheduleRow):
    """Typed overlay for door-schedule rows (common columns pre-parsed)."""
    width_raw: str | None = None            # e.g. "3'0\""
    height_raw: str | None = None           # e.g. "6'8\""
    door_type: str | None = None
    material: str | None = None
    fire_rating: str | None = None          # "20 min", "45 min", "1 hr", "N/A"
    hardware_group: str | None = None


class WindowScheduleRow(ScheduleRow):
    """Typed overlay for window-schedule rows."""
    width_raw: str | None = None
    height_raw: str | None = None
    window_type: str | None = None
    u_factor: float | None = None
    shgc: float | None = None
    egress_compliant: bool | None = None
    nco_area: float | None = None           # net clear opening area (sq ft)


class ScheduleExtraction(BaseModel):
    """Output of ScheduleAgent for one schedule table."""
    VERSION: ClassVar[str] = "1.0.0"

    schedule_type: str        # "door_schedule" | "window_schedule"
                              # | "fastener_schedule" | "holdown_schedule" | "wall_schedule"
    sheet_id: str
    headers: list[str]
    rows: list[ScheduleRow]
    extraction_method: str    # "native_table" | "vision"
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)

    def to_entity_payload(self) -> dict:  # type: ignore[type-arg]
        return self.model_dump()


# ---------------------------------------------------------------------------
# Phase 02 — Code-note extraction
# ---------------------------------------------------------------------------

class CodeNoteItem(BaseModel):
    reference: str | None = None    # e.g. "2022 CBC", "CBC §107.2.1"
    statement: str
    bbox: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)


class CodeNoteExtraction(BaseModel):
    """One code-note block (e.g. 'APPLICABLE CODES' or 'DESIGN CRITERIA')."""
    VERSION: ClassVar[str] = "1.0.0"

    block_type: str                 # "applicable_codes" | "design_criteria"
                                    # | "occupancy" | "construction_type" | "other"
    block_title: str | None = None
    items: list[CodeNoteItem]
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)

    def to_entity_payload(self) -> dict:  # type: ignore[type-arg]
        return self.model_dump()


# ---------------------------------------------------------------------------
# Phase 02 — Title 24 / CF1R extraction
# ---------------------------------------------------------------------------

class T24Surface(BaseModel):
    surface_type: str               # "roof" | "wall" | "floor" | "window" | "skylight"
    assembly_id: str | None = None
    area: float | None = None       # sq ft
    u_factor: float | None = None
    r_value: float | None = None    # stated directly or derived 1/u_factor
    assembly_description: str | None = None
    meets_prescriptive: bool | None = None


class T24HvacSystem(BaseModel):
    system_id: str | None = None
    system_type: str | None = None
    seer: float | None = None
    eer: float | None = None
    afue: float | None = None
    hspf: float | None = None
    cooling_btu: float | None = None
    heating_btu: float | None = None


class T24Dhw(BaseModel):
    fuel_type: str | None = None
    tank_size_gal: float | None = None
    ef: float | None = None
    uef: float | None = None


class Title24Extraction(BaseModel):
    """Output of Title24FormAgent for one CF1R / RMS-1 / MF1R document."""
    VERSION: ClassVar[str] = "1.0.0"

    form_type: str                           # "CF1R-PRF-01-E" | "RMS-1" | "MF1R" | "unknown"
    project_name: str | None = None
    project_address: str | None = None
    climate_zone: str | None = None
    permit_date: str | None = None
    conditioned_floor_area: float | None = None
    compliance_result: str | None = None     # "PASS" | "FAIL" | "N/A"
    envelope_surfaces: list[T24Surface] = Field(default_factory=list)
    hvac_systems: list[T24HvacSystem] = Field(default_factory=list)
    dhw_systems: list[T24Dhw] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.80)

    def to_entity_payload(self) -> dict:  # type: ignore[type-arg]
        return self.model_dump()


# ---------------------------------------------------------------------------
# Phase 02 — Review-letter comment (one row → external_review_comments)
# ---------------------------------------------------------------------------

class ReviewLetterComment(BaseModel):
    comment_number: int
    discipline_group: str | None = None    # BV section header, e.g. "ARCHITECTURE"
    discipline: str | None = None          # normalised, e.g. "architectural"
    review_round: int = 1
    typography: str | None = None          # "italic" | "bold" | "underlined"
    comment_text: str
    citation_text: str | None = None       # e.g. "CBC §107.2.1"
    sheet_reference: str | None = None     # e.g. "Sheet A-1.1"
    page_number: int = 1
    bbox: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)


class ReviewLetterExtraction(BaseModel):
    """Output of ReviewLetterAgent for one plan-check letter PDF."""
    VERSION: ClassVar[str] = "1.0.0"

    project_name: str | None = None
    project_address: str | None = None
    permit_number: str | None = None
    reviewer_name: str | None = None
    review_date: str | None = None
    total_comment_count: int = 0
    comments: list[ReviewLetterComment] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.80)

    def to_entity_payload(self) -> dict:  # type: ignore[type-arg]
        return self.model_dump()
