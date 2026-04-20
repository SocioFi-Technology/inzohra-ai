"""Tests for PDF quality integration — Phase 09.

Covers:
  - apply_quality_penalty: penalty math and skip-reason logic
  - EgressRouter: empty-entities case and two-room/one-exit path case
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup: allow importing from services/measurement/app without installing
# ---------------------------------------------------------------------------
APP_DIR = Path(__file__).parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from pdf_quality import apply_quality_penalty  # noqa: E402
from egress_router import EgressRouter  # noqa: E402


# ===========================================================================
# apply_quality_penalty tests
# ===========================================================================


def test_apply_quality_penalty_vector_no_penalty() -> None:
    """vector class: no penalty applied, skip_reason is None."""
    adjusted, skip_reason = apply_quality_penalty("door_clear_width", 0.9, "vector")
    assert adjusted == 0.9
    assert skip_reason is None


def test_apply_quality_penalty_hybrid() -> None:
    """hybrid class: confidence multiplied by 0.92."""
    adjusted, skip_reason = apply_quality_penalty("door_clear_width", 0.9, "hybrid")
    expected = round(0.9 * 0.92, 4)
    assert adjusted == expected
    assert skip_reason is None


def test_apply_quality_penalty_disabled_on_low_quality_scan() -> None:
    """egress_distance on low_quality_scan: confidence 0.0, skip_reason non-None."""
    adjusted, skip_reason = apply_quality_penalty("egress_distance", 0.85, "low_quality_scan")
    assert adjusted == 0.0
    assert skip_reason is not None
    assert "low_quality_scan" in skip_reason


def test_apply_quality_penalty_window_nco_low_quality_scan() -> None:
    """window_nco on low_quality_scan: penalty applied (not in DISABLED set)."""
    adjusted, skip_reason = apply_quality_penalty("window_nco", 0.9, "low_quality_scan")
    expected = round(0.9 * 0.55, 4)
    assert adjusted == expected
    assert skip_reason is None


# ===========================================================================
# EgressRouter tests — mock psycopg connection
# ===========================================================================


def _build_mock_conn(entities: list[dict[str, Any]]) -> MagicMock:
    """Build a MagicMock psycopg connection that returns `entities` on fetchall()
    and returns a row with pdf_quality_class='vector' for sheets queries.
    """
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    # Sheet-level query (fetchone) returns 'vector'
    mock_cursor.fetchone.return_value = {"pdf_quality_class": "vector"}
    # Entity-level query (fetchall) returns the provided entities list
    mock_cursor.fetchall.return_value = entities

    # Support context manager protocol for cursor
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor

    return mock_conn


def _make_egress_router_with_mock(
    entities: list[dict[str, Any]],
    pdf_quality_class: str = "vector",
    px_per_inch: float = 72.0,
) -> EgressRouter:
    """Return an EgressRouter whose DB calls are fully mocked."""
    router = EgressRouter.__new__(EgressRouter)
    router._database_url = "postgresql://mock"  # type: ignore[attr-defined]

    router._fetch_pdf_quality = MagicMock(return_value=pdf_quality_class)  # type: ignore[attr-defined]
    router._fetch_sheet_scale = MagicMock(return_value=px_per_inch)  # type: ignore[attr-defined]
    router._fetch_entities = MagicMock(return_value=entities)  # type: ignore[attr-defined]

    return router


def test_egress_router_empty_entities_returns_none() -> None:
    """With no entities on the sheet, route() must return None."""
    router = _make_egress_router_with_mock(entities=[])
    result = router.route(
        project_id="proj-001",
        sheet_id="sheet-A1",
        start_entity_id="room-001",
    )
    assert result is None


def test_egress_router_finds_path_to_exit() -> None:
    """Two room nodes + one adjacent exit door → path found with distance > 0."""
    # Layout (pixel coordinates): three boxes arranged horizontally
    # room-001: [0, 0, 100, 100]   (centroid 50, 50)
    # corridor: [90, 0, 200, 100]  (centroid 145, 50) — overlaps room-001
    # exit-door: [190, 0, 290, 100] (centroid 240, 50) — overlaps corridor, is_exit=True

    entities: list[dict[str, Any]] = [
        {
            "entity_id": "room-001",
            "type": "room",
            "payload": {},
            "bbox": [0.0, 0.0, 100.0, 100.0],
        },
        {
            "entity_id": "corridor-001",
            "type": "corridor",
            "payload": {},
            "bbox": [90.0, 0.0, 200.0, 100.0],
        },
        {
            "entity_id": "exit-door-001",
            "type": "door",
            "payload": {"is_exit": "true"},
            "bbox": [190.0, 0.0, 290.0, 100.0],
        },
    ]

    router = _make_egress_router_with_mock(entities=entities, px_per_inch=72.0)

    result = router.route(
        project_id="proj-001",
        sheet_id="sheet-A1",
        start_entity_id="room-001",
    )

    assert result is not None, "Expected a path to be found"
    assert result.end_entity_id == "exit-door-001"
    assert result.distance_inches > 0.0
    assert "room-001" in result.path_entity_ids
    assert "exit-door-001" in result.path_entity_ids
    assert result.confidence > 0.0
    assert result.pdf_quality_class == "vector"
