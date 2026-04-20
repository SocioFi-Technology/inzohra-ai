"""Pydantic schemas for Phase 03 measurement stack.

Every measurement carries provenance: bbox, confidence, trace.
These schemas are shared across services/measurement and services/review.
"""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class FloorPlanEntity(BaseModel):
    """A single entity extracted from a floor plan sheet by vision model."""

    entity_type: Literal["door", "window", "room", "stair", "exit", "balcony"]
    tag: str | None = None          # Door tag "3", window tag "W-4"
    room_label: str | None = None   # "BEDROOM 1", "MASTER BATH", "LIVING ROOM"
    room_use: str | None = None     # normalized: "bedroom","bathroom","kitchen","living","corridor","garage","exit"
    bbox: list[float] = Field(min_length=4, max_length=4)  # [x1,y1,x2,y2] PDF points, top-left origin
    page: int
    confidence: float = Field(ge=0.0, le=1.0)
    is_new_construction: bool = True
    geometry_notes: str | None = None  # "swing left", "sliding", "double", "exterior"
    schedule_ref: str | None = None    # tag connecting to schedule_rows.tag


class FloorPlanExtraction(BaseModel):
    """Full extraction result from FloorPlanGeometryAgent for one page."""

    sheet_id: str
    page: int
    entities: list[FloorPlanEntity] = Field(default_factory=list)
    extraction_confidence: float = Field(ge=0.0, le=1.0)
    prompt_hash: str = ""
    model: str = ""
    total_doors: int = 0
    total_windows: int = 0
    total_rooms: int = 0


class SheetScaleResult(BaseModel):
    """Resolved scale for a sheet — output of ScaleResolver."""

    sheet_id: str
    declared: str | None = None
    pts_per_real_inch: float       # PDF pts / real world inch
    calibrated: bool = False
    calibration_confidence: float = 0.0
    source: Literal["title_block", "calibrated", "default"] = "default"
    confidence: float = Field(ge=0.0, le=1.0)


class MeasurementTrace(BaseModel):
    """Provenance trace for a single measurement."""

    sublayers: list[dict[str, object]] = Field(default_factory=list)
    formula: str = ""
    source_bboxes: list[list[float]] = Field(default_factory=list)
    composed_confidence: float = 0.0


class MeasurementResult(BaseModel):
    """A single computed measurement with full provenance."""

    measurement_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str   # "door_clear_width","window_nco","egress_distance","room_area","distance"
    value: float
    unit: str   # "in", "sqft", "ft"
    confidence: float = Field(ge=0.0, le=1.0)
    trace: MeasurementTrace = Field(default_factory=MeasurementTrace)
    bbox: list[float] | None = None
    tag: str | None = None
    entity_id: str | None = None
    sheet_id: str = ""
