"""Fixture-driven unit tests for Phase 09: QuestionChecklistAgent.

Tests cover:
  1. Plain-text parse of an egress-window line → ChecklistQuery with correct fields.
  2. JSON checklist parse → multiple ChecklistQuery objects.
  3. AnswerPipeline.answer() with mocked DB: measured 4.2 sqft vs 5.7 threshold → red.
  4. Measured 5.8 sqft vs 5.7 threshold → green.
  5. Measured 5.3 sqft (within 10 %) vs 5.7 threshold → amber.
  6. No measurement rows in DB → unknown.

All DB calls are patched via unittest.mock — no live DB required.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure the review service root is on sys.path (mirrors conftest.py behaviour)
# ---------------------------------------------------------------------------
_SVC_ROOT = Path(__file__).resolve().parent.parent
if str(_SVC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SVC_ROOT))

# Ensure ingestion service root is on sys.path so we can import the parser.
_ING_ROOT = _SVC_ROOT.parent / "ingestion"
if str(_ING_ROOT) not in sys.path:
    sys.path.insert(0, str(_ING_ROOT))

from app.extractors.question_checklist import ChecklistQuery, QuestionChecklistParser
from app.qca.answer_pipeline import AnswerPipeline, ChecklistAnswer, _determine_status


# ---------------------------------------------------------------------------
# Helper: build a mock measurement row dict
# ---------------------------------------------------------------------------

def _meas_row(value: float, unit: str = "sqft", confidence: float = 0.90) -> dict:
    return {
        "value": value,
        "unit": unit,
        "confidence": confidence,
        "measurement_id": "00000000-0000-0000-0000-000000000001",
        "entity_id": "00000000-0000-0000-0000-000000000002",
    }


def _project_row() -> dict:
    return {"jurisdiction": "santa_rosa", "effective_date": "2023-01-01"}


# ---------------------------------------------------------------------------
# 1. Plain-text parse — egress window line
# ---------------------------------------------------------------------------

class TestQuestionChecklistParserText:
    def test_egress_window_parse(self) -> None:
        """A single plain-text egress-window line produces a correct ChecklistQuery."""
        parser = QuestionChecklistParser()
        results = parser.parse(
            "Verify egress window NCO ≥ 5.7 sqft in all bedrooms"
        )
        assert len(results) == 1
        q = results[0]
        assert isinstance(q, ChecklistQuery)
        assert q.target_entity_class == "window"
        assert q.code_ref == "CRC-R310.2.1"
        assert "window_nco" in q.measurement_types
        # Threshold should be extracted from the text
        assert q.threshold_value == pytest.approx(5.7)
        assert q.threshold_unit == "sqft"

    def test_skips_blank_and_comment_lines(self) -> None:
        text = "\n# This is a comment\n\nVerify door clear width ≥ 32 inches\n"
        parser = QuestionChecklistParser()
        results = parser.parse(text)
        assert len(results) == 1
        assert results[0].target_entity_class == "door"

    def test_unknown_keyword_returns_query_with_none_class(self) -> None:
        parser = QuestionChecklistParser()
        results = parser.parse("Check that the drawings are stamped by the architect")
        assert len(results) == 1
        assert results[0].target_entity_class is None
        assert results[0].code_ref is None

    def test_multiple_lines(self) -> None:
        text = (
            "Verify egress window NCO ≥ 5.7 sqft\n"
            "Verify door clear width ≥ 32 inches\n"
            "Verify ceiling height ≥ 90 inches\n"
        )
        parser = QuestionChecklistParser()
        results = parser.parse(text)
        assert len(results) == 3
        classes = [q.target_entity_class for q in results]
        assert "window" in classes
        assert "door" in classes
        assert "room" in classes


# ---------------------------------------------------------------------------
# 2. JSON checklist parse
# ---------------------------------------------------------------------------

class TestQuestionChecklistParserJSON:
    def test_json_array_multiple_items(self) -> None:
        """JSON array of items produces one ChecklistQuery per non-blank item."""
        items = [
            {"item_id": "sfr-001", "description": "Verify egress window NCO ≥ 5.7 sqft"},
            {"item_id": "sfr-002", "description": "Verify door clear width ≥ 32 inches"},
            {"item_id": "sfr-003", "description": "Verify travel distance ≤ 200 feet"},
        ]
        parser = QuestionChecklistParser()
        results = parser.parse(json.dumps(items))
        assert len(results) == 3
        assert results[0].item_id == "sfr-001"
        assert results[0].target_entity_class == "window"
        assert results[1].target_entity_class == "door"
        assert results[2].target_entity_class == "egress_path"

    def test_json_object_with_items_key(self) -> None:
        """JSON object with 'items' key is handled."""
        payload = {
            "checklist_id": "abc",
            "items": [
                {"item_id": "q-001", "description": "Verify ceiling height ≥ 90 inches"},
            ],
        }
        parser = QuestionChecklistParser()
        results = parser.parse(json.dumps(payload))
        assert len(results) == 1
        assert results[0].target_entity_class == "room"
        assert results[0].code_ref == "CRC-R305.1"

    def test_json_pre_specified_fields_override_pattern(self) -> None:
        """When JSON supplies target_entity_class, the pattern is not applied."""
        items = [
            {
                "item_id": "custom-001",
                "description": "Custom measurement check",
                "target_entity_class": "room",
                "measurement_types": ["custom_metric"],
                "code_ref": "CBC-999.9",
                "threshold_value": 42.0,
                "threshold_unit": "sqft",
                "filter_predicates": [{"field": "tag", "op": "=", "value": "R-101"}],
            }
        ]
        parser = QuestionChecklistParser()
        results = parser.parse(json.dumps(items))
        assert len(results) == 1
        q = results[0]
        assert q.target_entity_class == "room"
        assert q.measurement_types == ["custom_metric"]
        assert q.code_ref == "CBC-999.9"
        assert q.threshold_value == pytest.approx(42.0)
        assert q.filter_predicates == [{"field": "tag", "op": "=", "value": "R-101"}]

    def test_empty_json_array(self) -> None:
        parser = QuestionChecklistParser()
        assert parser.parse("[]") == []

    def test_items_with_missing_description_skipped(self) -> None:
        items = [
            {"item_id": "bad-001"},  # no description
            {"item_id": "ok-001", "description": "Verify egress window NCO ≥ 5.7 sqft"},
        ]
        parser = QuestionChecklistParser()
        results = parser.parse(json.dumps(items))
        assert len(results) == 1
        assert results[0].item_id == "ok-001"


# ---------------------------------------------------------------------------
# Helpers shared by AnswerPipeline tests
# ---------------------------------------------------------------------------

def _make_query(
    threshold: float = 5.7,
    meas_type: str = "window_nco",
    entity_class: str | None = "window",
) -> ChecklistQuery:
    return ChecklistQuery(
        item_id="test-001",
        description="Verify egress window NCO ≥ 5.7 sqft in all bedrooms",
        target_entity_class=entity_class,
        filter_predicates=[],
        measurement_types=[meas_type],
        code_ref="CRC-R310.2.1",
        threshold_value=threshold,
        threshold_unit="sqft",
    )


def _make_pipeline() -> AnswerPipeline:
    return AnswerPipeline(database_url="postgresql://test/test")


def _mock_conn_context(meas_rows: list[dict], proj_row: dict | None = None) -> MagicMock:
    """Build a mock psycopg connection context manager.

    The mock supports:
      - conn.execute(...).fetchall()  → meas_rows  (first call: measurements)
      - conn.execute(...).fetchone()  → proj_row    (second call: project)
    """
    call_count: list[int] = [0]

    def side_effect(*args: object, **kwargs: object) -> MagicMock:
        cursor = MagicMock()
        if call_count[0] == 0:
            # First execute: measurement query
            cursor.fetchall.return_value = meas_rows
        else:
            # Second execute: project query
            cursor.fetchone.return_value = proj_row
        call_count[0] += 1
        return cursor

    conn = MagicMock()
    conn.execute.side_effect = side_effect
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn


# ---------------------------------------------------------------------------
# 3–6. AnswerPipeline tests
# ---------------------------------------------------------------------------

class TestAnswerPipeline:
    """Tests for AnswerPipeline.answer() with mocked DB calls."""

    # ------------------------------------------------------------------
    # 3. Measured 4.2 sqft vs 5.7 threshold → red
    # ------------------------------------------------------------------
    def test_measured_below_threshold_red(self) -> None:
        query = _make_query(threshold=5.7)
        pipeline = _make_pipeline()
        mock_conn = _mock_conn_context(
            meas_rows=[_meas_row(4.2)],
            proj_row=_project_row(),
        )
        with (
            patch("psycopg.connect", return_value=mock_conn),
            patch("app.qca.answer_pipeline.lookup_canonical", return_value=None),
        ):
            answer = pipeline.answer(query, project_id="proj-uuid")

        assert isinstance(answer, ChecklistAnswer)
        assert answer.status == "red"
        assert answer.measured_value == pytest.approx(4.2)
        assert answer.required_value == pytest.approx(5.7)
        assert answer.query_id == "test-001"

    # ------------------------------------------------------------------
    # 4. Measured 5.8 sqft vs 5.7 threshold → green
    # ------------------------------------------------------------------
    def test_measured_above_threshold_green(self) -> None:
        query = _make_query(threshold=5.7)
        pipeline = _make_pipeline()
        mock_conn = _mock_conn_context(
            meas_rows=[_meas_row(5.8)],
            proj_row=_project_row(),
        )
        with (
            patch("psycopg.connect", return_value=mock_conn),
            patch("app.qca.answer_pipeline.lookup_canonical", return_value=None),
        ):
            answer = pipeline.answer(query, project_id="proj-uuid")

        assert answer.status == "green"
        assert answer.measured_value == pytest.approx(5.8)

    # ------------------------------------------------------------------
    # 5. Measured 5.3 sqft (within 10 % of 5.7) → amber
    # ------------------------------------------------------------------
    def test_measured_within_amber_band(self) -> None:
        # 5.7 * 0.90 = 5.13; 5.3 is between 5.13 and 5.7 → amber
        query = _make_query(threshold=5.7)
        pipeline = _make_pipeline()
        mock_conn = _mock_conn_context(
            meas_rows=[_meas_row(5.3)],
            proj_row=_project_row(),
        )
        with (
            patch("psycopg.connect", return_value=mock_conn),
            patch("app.qca.answer_pipeline.lookup_canonical", return_value=None),
        ):
            answer = pipeline.answer(query, project_id="proj-uuid")

        assert answer.status == "amber"
        assert answer.measured_value == pytest.approx(5.3)

    # ------------------------------------------------------------------
    # 6. No measurement found → unknown
    # ------------------------------------------------------------------
    def test_no_measurement_returns_unknown(self) -> None:
        query = _make_query(threshold=5.7)
        pipeline = _make_pipeline()
        mock_conn = _mock_conn_context(
            meas_rows=[],
            proj_row=_project_row(),
        )
        with (
            patch("psycopg.connect", return_value=mock_conn),
            patch("app.qca.answer_pipeline.lookup_canonical", return_value=None),
        ):
            answer = pipeline.answer(query, project_id="proj-uuid")

        assert answer.status == "unknown"
        assert answer.measured_value is None
        assert answer.confidence == 0.0
        assert "Unable to answer" in answer.answer_text

    # ------------------------------------------------------------------
    # Additional: answer_text content
    # ------------------------------------------------------------------
    def test_answer_text_green_is_compliant(self) -> None:
        query = _make_query(threshold=5.7)
        pipeline = _make_pipeline()
        mock_conn = _mock_conn_context(
            meas_rows=[_meas_row(6.0)],
            proj_row=_project_row(),
        )
        with (
            patch("psycopg.connect", return_value=mock_conn),
            patch("app.qca.answer_pipeline.lookup_canonical", return_value=None),
        ):
            answer = pipeline.answer(query, project_id="proj-uuid")

        assert answer.status == "green"
        assert "Compliant" in answer.answer_text

    def test_answer_text_red_is_non_compliant(self) -> None:
        query = _make_query(threshold=5.7)
        pipeline = _make_pipeline()
        mock_conn = _mock_conn_context(
            meas_rows=[_meas_row(3.0)],
            proj_row=_project_row(),
        )
        with (
            patch("psycopg.connect", return_value=mock_conn),
            patch("app.qca.answer_pipeline.lookup_canonical", return_value=None),
        ):
            answer = pipeline.answer(query, project_id="proj-uuid")

        assert answer.status == "red"
        assert "Non-compliant" in answer.answer_text

    # ------------------------------------------------------------------
    # _determine_status unit tests (no DB needed)
    # ------------------------------------------------------------------
    def test_determine_status_minimum_green(self) -> None:
        assert _determine_status(6.0, 5.7, "window_nco") == "green"

    def test_determine_status_minimum_amber(self) -> None:
        # 5.7 * 0.90 = 5.13; 5.3 is in range [5.13, 5.7)
        assert _determine_status(5.3, 5.7, "window_nco") == "amber"

    def test_determine_status_minimum_red(self) -> None:
        # 4.2 < 5.7 * 0.90 = 5.13
        assert _determine_status(4.2, 5.7, "window_nco") == "red"

    def test_determine_status_maximum_green(self) -> None:
        # egress_distance is a maximum rule
        assert _determine_status(150.0, 200.0, "egress_distance") == "green"

    def test_determine_status_maximum_amber(self) -> None:
        # 200 * 1.10 = 220; 210 is in range (200, 220]
        assert _determine_status(210.0, 200.0, "egress_distance") == "amber"

    def test_determine_status_maximum_red(self) -> None:
        # 250 > 200 * 1.10 = 220
        assert _determine_status(250.0, 200.0, "egress_distance") == "red"
