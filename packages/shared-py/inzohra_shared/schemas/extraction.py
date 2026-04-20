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
