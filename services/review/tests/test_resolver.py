"""Unit tests for JurisdictionResolver.

psycopg.connect is patched so these tests never require a live database.
Each test controls exactly what the mocked cursor returns.

Run:
    pytest services/review/tests/test_resolver.py -v
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.codekb.resolver import AmendmentApplication, JurisdictionResolver, ResolvedSection

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DB_URL = "postgresql://test:test@localhost/test"
_JURISDICTION = "santa_rosa"
_EFF_DATE = "2023-01-01"
_SECTION_ID = str(uuid.uuid4())
_CANONICAL_ID = "CBC-R310.2.1"
_BASE_TEXT = "Emergency escape opening shall comply with this section."


def _make_section_row(
    section_id: str = _SECTION_ID,
    canonical_id: str = _CANONICAL_ID,
    body_text: str = _BASE_TEXT,
) -> dict[str, Any]:
    return {
        "section_id": section_id,
        "canonical_id": canonical_id,
        "code": "CBC",
        "section_number": "R310.2.1",
        "title": "Emergency escape openings",
        "body_text": body_text,
        "cross_references": [],
        "referenced_standards": [],
        "effective_date": date(2023, 1, 1),
    }


def _make_amendment(
    operation: str,
    text: str,
    effective_date: str = "2023-06-01",
    amendment_id: str | None = None,
) -> dict[str, Any]:
    return {
        "amendment_id": amendment_id or str(uuid.uuid4()),
        "operation": operation,
        "amendment_text": text,
        "effective_date": date.fromisoformat(effective_date),
    }


def _build_mock_conn(
    section_row: dict[str, Any] | None,
    amendment_rows: list[dict[str, Any]],
    policy_rows: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a mock psycopg connection whose execute() returns configured rows."""
    mock_conn = MagicMock()

    # We track execute() call order:
    #   call 0 → _fetch_section
    #   call 1 → _fetch_amendments
    #   call 2 → _fetch_policies
    results = [section_row, amendment_rows, policy_rows or []]
    call_count: list[int] = [0]

    def mock_execute(sql: str, params: Any = None) -> MagicMock:
        idx = call_count[0]
        call_count[0] += 1
        mock_cursor = MagicMock()
        if idx == 0:
            mock_cursor.fetchone.return_value = results[0]
        else:
            mock_cursor.fetchall.return_value = results[idx]
        return mock_cursor

    mock_conn.execute.side_effect = mock_execute
    # Support context-manager usage (with psycopg.connect(...) as conn:)
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    return mock_conn


# ---------------------------------------------------------------------------
# Test 1: Section found, no amendments → resolved_text == base_text, confidence == 1.0
# ---------------------------------------------------------------------------


def test_resolve_no_amendments() -> None:
    """When no amendments exist, resolved_text equals base_text and confidence is 1.0."""
    section_row = _make_section_row()
    mock_conn = _build_mock_conn(
        section_row=section_row,
        amendment_rows=[],
        policy_rows=[],
    )

    with patch("app.codekb.resolver.psycopg.connect", return_value=mock_conn):
        resolver = JurisdictionResolver(_DB_URL)
        result = resolver.resolve(
            code="CBC",
            section_number="R310.2.1",
            jurisdiction=_JURISDICTION,
            effective_date=_EFF_DATE,
        )

    assert result is not None
    assert isinstance(result, ResolvedSection)
    assert result.resolved_text == _BASE_TEXT
    assert result.base_text == _BASE_TEXT
    assert result.amendments_applied == []
    assert result.confidence == 1.0
    assert result.jurisdiction == _JURISDICTION
    assert result.canonical_id == _CANONICAL_ID
    # Precedence chain must mention the base section
    assert any("base_section" in step for step in result.precedence_chain)
    assert any("no_amendments" in step for step in result.precedence_chain)


# ---------------------------------------------------------------------------
# Test 2: Section found, one 'append' amendment
# ---------------------------------------------------------------------------


def test_resolve_append_amendment() -> None:
    """One append amendment concatenates to base_text with double newline."""
    section_row = _make_section_row()
    amendment_text = "California amendment: minimum net clear opening area shall be 5.7 sq ft."
    amd = _make_amendment("append", amendment_text)
    mock_conn = _build_mock_conn(
        section_row=section_row,
        amendment_rows=[amd],
        policy_rows=[],
    )

    with patch("app.codekb.resolver.psycopg.connect", return_value=mock_conn):
        resolver = JurisdictionResolver(_DB_URL)
        result = resolver.resolve(
            code="CBC",
            section_number="R310.2.1",
            jurisdiction=_JURISDICTION,
            effective_date=_EFF_DATE,
        )

    assert result is not None
    expected = _BASE_TEXT + "\n\n" + amendment_text
    assert result.resolved_text == expected
    assert result.base_text == _BASE_TEXT
    assert len(result.amendments_applied) == 1
    assert result.amendments_applied[0].operation == "append"
    assert result.amendments_applied[0].text == amendment_text
    assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# Test 3: Section found, one 'replace' amendment
# ---------------------------------------------------------------------------


def test_resolve_replace_amendment() -> None:
    """One replace amendment sets resolved_text to the amendment text."""
    section_row = _make_section_row()
    replacement_text = "Replaced: All emergency openings shall be minimum 5.7 sq ft net clear."
    amd = _make_amendment("replace", replacement_text)
    mock_conn = _build_mock_conn(
        section_row=section_row,
        amendment_rows=[amd],
        policy_rows=[],
    )

    with patch("app.codekb.resolver.psycopg.connect", return_value=mock_conn):
        resolver = JurisdictionResolver(_DB_URL)
        result = resolver.resolve(
            code="CBC",
            section_number="R310.2.1",
            jurisdiction=_JURISDICTION,
            effective_date=_EFF_DATE,
        )

    assert result is not None
    assert result.resolved_text == replacement_text
    assert result.base_text == _BASE_TEXT
    assert len(result.amendments_applied) == 1
    assert result.amendments_applied[0].operation == "replace"
    assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# Test 4: Section found, two 'replace' amendments → confidence == 0.7, last wins
# ---------------------------------------------------------------------------


def test_resolve_two_replace_amendments_conflict() -> None:
    """Two replace amendments lower confidence to 0.7; the last one (most recent) wins."""
    section_row = _make_section_row()
    first_text = "First replacement text."
    second_text = "Second (more recent) replacement text."
    # Ordered ASC by effective_date as the DB query guarantees
    amd1 = _make_amendment("replace", first_text, effective_date="2023-03-01")
    amd2 = _make_amendment("replace", second_text, effective_date="2023-09-01")
    mock_conn = _build_mock_conn(
        section_row=section_row,
        amendment_rows=[amd1, amd2],
        policy_rows=[],
    )

    with patch("app.codekb.resolver.psycopg.connect", return_value=mock_conn):
        resolver = JurisdictionResolver(_DB_URL)
        result = resolver.resolve(
            code="CBC",
            section_number="R310.2.1",
            jurisdiction=_JURISDICTION,
            effective_date=_EFF_DATE,
        )

    assert result is not None
    # Most-recent replace wins
    assert result.resolved_text == second_text
    assert result.base_text == _BASE_TEXT
    assert len(result.amendments_applied) == 2
    assert result.confidence == pytest.approx(0.7)
    # Conflict must appear in the precedence chain
    assert any("CONFLICT" in step for step in result.precedence_chain)


# ---------------------------------------------------------------------------
# Test 5: Section not found → returns None
# ---------------------------------------------------------------------------


def test_resolve_section_not_found() -> None:
    """When code_sections has no matching row, resolve() returns None."""
    mock_conn = _build_mock_conn(
        section_row=None,
        amendment_rows=[],
        policy_rows=[],
    )

    with patch("app.codekb.resolver.psycopg.connect", return_value=mock_conn):
        resolver = JurisdictionResolver(_DB_URL)
        result = resolver.resolve(
            code="CBC",
            section_number="R999.99.99",
            jurisdiction=_JURISDICTION,
            effective_date=_EFF_DATE,
        )

    assert result is None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pytest  # noqa: PLC0415

    pytest.main([__file__, "-v"])
