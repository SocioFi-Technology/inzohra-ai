"""HeightInference — Phase 09.

Infers ceiling/header heights from elevation and section drawings when
floor plan data is insufficient.

Returns heights in INCHES.  Every result carries the source entity_id
and the sheet_id it was read from (may differ from the floor plan sheet).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.rows import dict_row

from pdf_quality import CONFIDENCE_PENALTIES

logger = logging.getLogger(__name__)


@dataclass
class HeightResult:
    value_inches: float
    source_sheet_id: str
    source_entity_id: str
    measurement_type: str  # 'ceiling_height' | 'door_header_height' | 'window_sill_height'
    confidence: float
    trace: list[str]


class HeightInference:
    """Infer ceiling/header heights from elevation and section drawings (no LLM)."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def infer_ceiling_height(
        self,
        project_id: str,
        room_entity_id: str,
    ) -> HeightResult | None:
        """Infer ceiling height for a room.

        Priority:
          1. payload['ceiling_height_raw'] on the entity itself.
          2. section/elevation entities on the same project that reference
             the same room label (matched via payload['room_label']).
          3. Return None if no data found.
        """
        room_row = self._fetch_entity(room_entity_id)
        if room_row is None:
            logger.warning("infer_ceiling_height: entity_id=%s not found", room_entity_id)
            return None

        payload: dict[str, Any] = room_row.get("payload") or {}
        sheet_id: str = room_row.get("sheet_id", "")
        pdf_quality_class: str = room_row.get("pdf_quality_class") or "vector"

        # Priority 1 — ceiling_height_raw on the entity itself
        raw_height = payload.get("ceiling_height_raw")
        if raw_height is not None:
            try:
                value_inches = float(raw_height)
            except (TypeError, ValueError):
                logger.warning(
                    "infer_ceiling_height: unparseable ceiling_height_raw=%r for entity_id=%s",
                    raw_height,
                    room_entity_id,
                )
            else:
                penalty = CONFIDENCE_PENALTIES.get(pdf_quality_class, 1.0)
                confidence = round(0.95 * penalty, 4)
                return HeightResult(
                    value_inches=value_inches,
                    source_sheet_id=sheet_id,
                    source_entity_id=room_entity_id,
                    measurement_type="ceiling_height",
                    confidence=confidence,
                    trace=[
                        f"source=payload.ceiling_height_raw",
                        f"entity_id={room_entity_id}",
                        f"sheet_id={sheet_id}",
                        f"pdf_quality_class={pdf_quality_class}",
                        f"value_inches={value_inches}",
                        f"confidence={confidence}",
                    ],
                )

        # Priority 2 — section/elevation entities referencing same room label
        room_label: str | None = payload.get("room_label")
        if room_label:
            result = self._search_elevation_for_ceiling(
                project_id=project_id,
                room_label=room_label,
            )
            if result is not None:
                return result

        logger.info(
            "infer_ceiling_height: no data found for entity_id=%s project_id=%s",
            room_entity_id,
            project_id,
        )
        return None

    def infer_door_header_height(
        self,
        project_id: str,
        door_entity_id: str,
    ) -> HeightResult | None:
        """Infer door header height from door schedule or elevation."""
        door_row = self._fetch_entity(door_entity_id)
        if door_row is None:
            logger.warning("infer_door_header_height: entity_id=%s not found", door_entity_id)
            return None

        payload: dict[str, Any] = door_row.get("payload") or {}
        sheet_id: str = door_row.get("sheet_id", "")
        pdf_quality_class: str = door_row.get("pdf_quality_class") or "vector"

        # Priority 1 — header_height_raw on the entity itself
        raw_height = payload.get("header_height_raw")
        if raw_height is not None:
            try:
                value_inches = float(raw_height)
            except (TypeError, ValueError):
                logger.warning(
                    "infer_door_header_height: unparseable header_height_raw=%r for entity_id=%s",
                    raw_height,
                    door_entity_id,
                )
            else:
                penalty = CONFIDENCE_PENALTIES.get(pdf_quality_class, 1.0)
                confidence = round(0.93 * penalty, 4)
                return HeightResult(
                    value_inches=value_inches,
                    source_sheet_id=sheet_id,
                    source_entity_id=door_entity_id,
                    measurement_type="door_header_height",
                    confidence=confidence,
                    trace=[
                        f"source=payload.header_height_raw",
                        f"entity_id={door_entity_id}",
                        f"sheet_id={sheet_id}",
                        f"pdf_quality_class={pdf_quality_class}",
                        f"value_inches={value_inches}",
                        f"confidence={confidence}",
                    ],
                )

        # Priority 2 — door schedule or elevation entities matching door_tag
        door_tag: str | None = payload.get("door_tag") or payload.get("tag")
        if door_tag:
            result = self._search_schedule_for_door_header(
                project_id=project_id,
                door_tag=door_tag,
            )
            if result is not None:
                return result

        logger.info(
            "infer_door_header_height: no data found for entity_id=%s project_id=%s",
            door_entity_id,
            project_id,
        )
        return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_entity(self, entity_id: str) -> dict[str, Any] | None:
        """Fetch a single entity row joined with its sheet's pdf_quality_class."""
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT e.entity_id, e.sheet_id, e.type, e.payload,
                           s.pdf_quality_class
                    FROM entities e
                    LEFT JOIN sheets s ON s.sheet_id = e.sheet_id
                    WHERE e.entity_id = %s
                    """,
                    (entity_id,),
                )
                return cur.fetchone()  # type: ignore[return-value]

    def _search_elevation_for_ceiling(
        self,
        project_id: str,
        room_label: str,
    ) -> HeightResult | None:
        """Search elevation/section entities for ceiling height referencing room_label."""
        rows = self._fetch_elevation_rows(
            project_id=project_id,
            room_label=room_label,
            door_tag=None,
        )

        for row in rows:
            payload: dict[str, Any] = row.get("payload") or {}
            raw_height = payload.get("ceiling_height_raw") or payload.get("height_raw")
            if raw_height is None:
                continue
            try:
                value_inches = float(raw_height)
            except (TypeError, ValueError):
                continue

            pdf_quality_class: str = row.get("pdf_quality_class") or "vector"
            penalty = CONFIDENCE_PENALTIES.get(pdf_quality_class, 1.0)
            confidence = round(0.82 * penalty, 4)
            source_sheet_id: str = row.get("sheet_id", "")
            source_entity_id: str = row.get("entity_id", "")

            return HeightResult(
                value_inches=value_inches,
                source_sheet_id=source_sheet_id,
                source_entity_id=source_entity_id,
                measurement_type="ceiling_height",
                confidence=confidence,
                trace=[
                    f"source=elevation/section entity",
                    f"room_label={room_label}",
                    f"source_entity_id={source_entity_id}",
                    f"source_sheet_id={source_sheet_id}",
                    f"pdf_quality_class={pdf_quality_class}",
                    f"value_inches={value_inches}",
                    f"confidence={confidence}",
                ],
            )
        return None

    def _search_schedule_for_door_header(
        self,
        project_id: str,
        door_tag: str,
    ) -> HeightResult | None:
        """Search door schedule / elevation entities for door header height."""
        rows = self._fetch_elevation_rows(
            project_id=project_id,
            room_label=None,
            door_tag=door_tag,
        )

        for row in rows:
            payload: dict[str, Any] = row.get("payload") or {}
            raw_height = (
                payload.get("header_height_raw")
                or payload.get("door_height_raw")
                or payload.get("height_raw")
            )
            if raw_height is None:
                continue
            try:
                value_inches = float(raw_height)
            except (TypeError, ValueError):
                continue

            pdf_quality_class: str = row.get("pdf_quality_class") or "vector"
            penalty = CONFIDENCE_PENALTIES.get(pdf_quality_class, 1.0)
            confidence = round(0.85 * penalty, 4)
            source_sheet_id: str = row.get("sheet_id", "")
            source_entity_id: str = row.get("entity_id", "")

            return HeightResult(
                value_inches=value_inches,
                source_sheet_id=source_sheet_id,
                source_entity_id=source_entity_id,
                measurement_type="door_header_height",
                confidence=confidence,
                trace=[
                    f"source=door_schedule/elevation entity",
                    f"door_tag={door_tag}",
                    f"source_entity_id={source_entity_id}",
                    f"source_sheet_id={source_sheet_id}",
                    f"pdf_quality_class={pdf_quality_class}",
                    f"value_inches={value_inches}",
                    f"confidence={confidence}",
                ],
            )
        return None

    def _fetch_elevation_rows(
        self,
        project_id: str,
        room_label: str | None,
        door_tag: str | None,
    ) -> list[dict[str, Any]]:
        """Fetch elevation/section/schedule entities matching room_label or door_tag."""
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT e.entity_id, e.sheet_id, e.payload, s.pdf_quality_class
                    FROM entities e
                    JOIN sheets s ON s.sheet_id = e.sheet_id
                    WHERE e.project_id = %s
                      AND e.type IN ('elevation_detail', 'section_detail', 'door_schedule_row')
                      AND (
                          e.payload ->> 'room_label' = %s
                          OR e.payload ->> 'door_tag' = %s
                      )
                    """,
                    (project_id, room_label, door_tag),
                )
                return list(cur.fetchall())
