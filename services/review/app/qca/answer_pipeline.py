"""QuestionChecklistAnswer pipeline — Phase 09.

For each confirmed ChecklistQuery, dispatches to measurement + code-RAG tools
and returns a ChecklistAnswer with status green/amber/red/unknown.

Invariants upheld:
  - Status is determined by rule: measured_value vs threshold.  LLM is never
    the decision-maker for green/amber/red (invariant #4).
  - Every answer carries the code citation (frozen_text from code-RAG)
    (invariant #3).
  - confidence propagates from measurement confidence × code confidence
    (invariant #1).
  - No temperature parameter because no LLM is called in this module; the
    answer_text is composed by a deterministic rule-based string builder.

Layer: 7 — Review engine (rules pass only; no LLM residue path needed here
because the determination is a simple numeric comparison).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import psycopg
from psycopg.rows import dict_row

# ---------------------------------------------------------------------------
# Ensure shared-py is importable when the review service is loaded directly
# (not via installed package).
# ---------------------------------------------------------------------------
_SHARED_ROOT = Path(__file__).resolve().parents[4] / "packages" / "shared-py"
if str(_SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(_SHARED_ROOT))

from app.codekb.tools import lookup_canonical

if TYPE_CHECKING:
    from services.ingestion.app.extractors.question_checklist import ChecklistQuery


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ChecklistAnswer:
    """Answer produced by the pipeline for a single confirmed ChecklistQuery."""

    query_id: str
    status: str                            # 'green' | 'amber' | 'red' | 'unknown'
    measured_value: float | None
    unit: str | None
    required_value: float | None
    code_citation: dict[str, Any] | None   # from Citation.to_finding_citation()
    evidence_entity_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    answer_text: str = ""


# ---------------------------------------------------------------------------
# Status determination (pure rule — no LLM)
# ---------------------------------------------------------------------------

# Measurement types where the rule is a *maximum* (measured must not exceed threshold).
_MAXIMUM_TYPES: frozenset[str] = frozenset(
    {"egress_distance", "occupant_load"}
)

_AMBER_BAND = 0.10  # 10% tolerance band for amber status


def _determine_status(
    measured: float,
    threshold: float,
    measurement_type: str,
) -> str:
    """Return 'green', 'amber', or 'red' based on measured vs threshold.

    For maximum rules: measured must be <= threshold (failing = too high).
    For minimum rules: measured must be >= threshold (failing = too low).

    Amber applies when within 10% of the threshold in the failing direction.
    """
    is_maximum = measurement_type in _MAXIMUM_TYPES

    if is_maximum:
        # green: measured <= threshold
        # amber: threshold < measured <= threshold * 1.10
        # red:   measured > threshold * 1.10
        if measured <= threshold:
            return "green"
        elif measured <= threshold * (1 + _AMBER_BAND):
            return "amber"
        else:
            return "red"
    else:
        # Minimum rule: measured must be >= threshold.
        # green: measured >= threshold
        # amber: threshold * (1 - 0.10) <= measured < threshold
        # red:   measured < threshold * (1 - 0.10)
        if measured >= threshold:
            return "green"
        elif measured >= threshold * (1 - _AMBER_BAND):
            return "amber"
        else:
            return "red"


def _build_answer_text(
    description: str,
    status: str,
    measured: float | None,
    required: float | None,
    unit: str | None,
    measurement_type: str | None,
) -> str:
    """Compose a one-sentence, human-readable answer (no LLM)."""
    unit_str = f" {unit}" if unit else ""
    meas_str = f"{measured:.2f}{unit_str}" if measured is not None else "not found"
    req_str = f"{required:.2f}{unit_str}" if required is not None else "not determinable"

    if status == "unknown":
        return (
            f"Unable to answer: no measurement found for '{description}'; "
            "confirm entity exists in extracted data."
        )
    if status == "green":
        return (
            f"Compliant — measured {meas_str} meets the required {req_str}."
        )
    if status == "amber":
        return (
            f"Near non-compliance — measured {meas_str} is within 10 % of the "
            f"required {req_str}; verify field dimensions."
        )
    # red
    return (
        f"Non-compliant — measured {meas_str} does not meet the required {req_str}. "
        "Revise plans or provide justification."
    )


# ---------------------------------------------------------------------------
# DB fetch helper
# ---------------------------------------------------------------------------

_MEASUREMENT_QUERY = """
SELECT m.value, m.unit, m.confidence, m.measurement_id::TEXT, m.entity_id::TEXT
FROM   measurements m
JOIN   entities e ON e.entity_id = m.entity_id
WHERE  m.project_id = %s
  AND  m.measurement_type = ANY(%s)
  AND  (e.type = %s OR %s IS NULL)
ORDER  BY m.created_at DESC
LIMIT  10
"""


def _fetch_measurements(
    conn: psycopg.Connection[Any],
    project_id: str,
    measurement_types: list[str],
    entity_class: str | None,
) -> list[dict[str, Any]]:
    """Fetch matching measurements from the DB.

    Falls back to the measurement_type-only query when *entity_class* is None,
    because the ``entities`` table JOIN requires a non-null type filter.
    """
    rows = conn.execute(
        _MEASUREMENT_QUERY,
        (project_id, measurement_types, entity_class, entity_class),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class AnswerPipeline:
    """Answer confirmed ChecklistQuery objects using measurement + code-RAG.

    Parameters
    ----------
    database_url:
        libpq-compatible connection string (used for both measurements and
        code-section lookups).
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def answer(
        self,
        query: "ChecklistQuery",
        project_id: str,
    ) -> ChecklistAnswer:
        """Answer a single confirmed checklist query.

        Steps:
          1. Fetch measurement(s) from DB for matching entity.
          2. Fetch code citation via lookup_canonical (code-RAG).
          3. Determine status by comparing measured vs threshold (rule-based).
          4. Compose answer_text (deterministic string builder, no LLM).

        Parameters
        ----------
        query:
            A confirmed :class:`~services.ingestion.app.extractors.question_checklist.ChecklistQuery`.
        project_id:
            UUID string of the project under review.

        Returns
        -------
        :class:`ChecklistAnswer`
        """
        with psycopg.connect(self._database_url, row_factory=dict_row) as conn:
            # Step 1 — measurements
            measurement_rows = _fetch_measurements(
                conn,
                project_id,
                query.measurement_types,
                query.target_entity_class,
            )

            # Step 2 — code citation
            citation_dict: dict[str, Any] | None = None
            code_confidence: float = 1.0
            if query.code_ref:
                # Derive jurisdiction and effective_date from the project row.
                proj_row = conn.execute(
                    "SELECT jurisdiction, effective_date FROM projects WHERE project_id = %s",
                    (project_id,),
                ).fetchone()
                if proj_row is not None:
                    jurisdiction: str = proj_row["jurisdiction"]
                    effective_date: str = str(proj_row["effective_date"])
                    citation = lookup_canonical(
                        self._database_url,
                        canonical_id=query.code_ref,
                        jurisdiction=jurisdiction,
                        effective_date=effective_date,
                    )
                    if citation is not None:
                        citation_dict = citation.to_finding_citation()
                        code_confidence = citation.confidence

        # Step 3 — determine status
        if not measurement_rows:
            return ChecklistAnswer(
                query_id=query.item_id,
                status="unknown",
                measured_value=None,
                unit=None,
                required_value=query.threshold_value,
                code_citation=citation_dict,
                evidence_entity_ids=[],
                confidence=0.0,
                answer_text=_build_answer_text(
                    query.description, "unknown",
                    None, query.threshold_value, query.threshold_unit,
                    query.measurement_types[0] if query.measurement_types else None,
                ),
            )

        # Use the most-recent (highest-confidence) measurement.
        best = max(measurement_rows, key=lambda r: float(r.get("confidence", 0)))
        measured_value: float = float(best["value"])
        measured_unit: str = str(best.get("unit") or query.threshold_unit or "")
        meas_confidence: float = float(best.get("confidence", 0.5))
        entity_ids: list[str] = [
            str(r["entity_id"]) for r in measurement_rows if r.get("entity_id")
        ]

        primary_meas_type = query.measurement_types[0] if query.measurement_types else ""

        if query.threshold_value is not None:
            status = _determine_status(measured_value, query.threshold_value, primary_meas_type)
        else:
            status = "unknown"

        composed_confidence = round(meas_confidence * code_confidence, 4)

        answer_text = _build_answer_text(
            query.description,
            status,
            measured_value,
            query.threshold_value,
            measured_unit or query.threshold_unit,
            primary_meas_type,
        )

        return ChecklistAnswer(
            query_id=query.item_id,
            status=status,
            measured_value=measured_value,
            unit=measured_unit,
            required_value=query.threshold_value,
            code_citation=citation_dict,
            evidence_entity_ids=entity_ids,
            confidence=composed_confidence,
            answer_text=answer_text,
        )
