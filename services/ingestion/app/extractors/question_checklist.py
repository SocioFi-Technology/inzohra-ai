"""QuestionChecklistAgent — Phase 09.

Parses a checklist document (plain text, or JSON from submittal_checklists table)
into structured ChecklistQuery objects.  Each query is:
  - A plain-English description
  - A target entity class (door/window/room/egress_path/null)
  - Filter predicates (e.g. 'tag = W-1')
  - Measurement types to fetch
  - A governing code section (canonical_id) and threshold

The agent presents parsed queries for user confirmation before answering.
No LLM calls in this module — parsing is rule-based.

Layer: 3 — Extraction (rule-based parser, no LLM).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Data contract
# ---------------------------------------------------------------------------

@dataclass
class ChecklistQuery:
    """Structured representation of a single checklist item."""

    item_id: str
    description: str
    target_entity_class: str | None       # 'door' | 'window' | 'room' | 'egress_path' | None
    filter_predicates: list[dict[str, str]]  # [{field, op, value}]
    measurement_types: list[str]
    code_ref: str | None                  # canonical_id like 'CRC-R310.2.1'
    threshold_value: float | None
    threshold_unit: str | None


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

# Each pattern entry:
#   (keyword_substring, target_entity_class, measurement_types, code_ref, threshold_unit)
#
# Keyword matching is case-insensitive substring search; first match wins.
# Patterns are ordered from most-specific to least-specific.

_PATTERNS: list[tuple[str, str | None, list[str], str | None, str | None]] = [
    # Egress / emergency escape windows (NCO)
    ("egress window",   "window",      ["window_nco"],        "CRC-R310.2.1",   "sqft"),
    ("emergency escape","window",      ["window_nco"],        "CRC-R310.2.1",   "sqft"),
    ("rescue opening",  "window",      ["window_nco"],        "CRC-R310.2.1",   "sqft"),
    # Door clear width
    ("door width",      "door",        ["door_clear_width"],  "CBC-11B-404.2.3","inches"),
    ("door clear",      "door",        ["door_clear_width"],  "CBC-11B-404.2.3","inches"),
    ("door hardware",   "door",        ["door_clear_width"],  "CBC-11B-404.2.4","inches"),
    # Accessible / accessible route
    ("accessible route","egress_path", ["accessible_route"],  "CBC-11B-402.2",  "inches"),
    ("accessibility",   "egress_path", ["accessible_route"],  "CBC-11B-402.2",  "inches"),
    # Ceiling height
    ("ceiling height",  "room",        ["ceiling_height"],    "CRC-R305.1",     "inches"),
    ("ceiling",         "room",        ["ceiling_height"],    "CRC-R305.1",     "inches"),
    # Travel / egress distance
    ("travel distance", "egress_path", ["egress_distance"],   "CBC-1017.2",     "feet"),
    ("egress path",     "egress_path", ["egress_distance"],   "CBC-1017.2",     "feet"),
    ("exit distance",   "egress_path", ["egress_distance"],   "CBC-1017.2",     "feet"),
    # Corridor width
    ("corridor width",  "room",        ["corridor_width"],    "CBC-1020.2",     "inches"),
    ("hallway width",   "room",        ["corridor_width"],    "CBC-1020.2",     "inches"),
    # Stairway width
    ("stairway width",  "egress_path", ["stair_width"],       "CRC-R311.7.1",   "inches"),
    ("stair width",     "egress_path", ["stair_width"],       "CRC-R311.7.1",   "inches"),
    # Handrail height
    ("handrail height", "egress_path", ["handrail_height"],   "CRC-R311.7.8.1", "inches"),
    ("handrail",        "egress_path", ["handrail_height"],   "CRC-R311.7.8.1", "inches"),
    # Occupant load
    ("occupant load",   "room",        ["occupant_load"],     "CBC-1004.1",     "persons"),
    ("occupancy load",  "room",        ["occupant_load"],     "CBC-1004.1",     "persons"),
]

# Common numeric threshold patterns found in checklist lines:
#   "≥ 5.7 sqft", ">= 44 inches", "min 36\"", "maximum 200 feet"
_THRESHOLD_RE = re.compile(
    r"""
    (?:(?:≥|>=|min(?:imum)?|at\s+least|not\s+less\s+than)\s*)?   # qualifier (optional)
    (?P<value>\d+(?:\.\d+)?)                                        # numeric value
    \s*
    (?P<unit>sqft|sq\.?\s*ft\.?|sf|in(?:ch(?:es)?)?|"|feet|ft\.?|persons?|people)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_UNIT_NORMALISE: dict[str, str] = {
    "sqft": "sqft", "sq ft": "sqft", "sq.ft": "sqft", "sq. ft.": "sqft", "sf": "sqft",
    "inches": "inches", "inch": "inches", "in": "inches", '"': "inches",
    "feet": "feet", "ft": "feet", "ft.": "feet",
    "persons": "persons", "person": "persons", "people": "persons",
}


def _normalise_unit(raw: str) -> str:
    key = raw.strip().lower().rstrip(".")
    return _UNIT_NORMALISE.get(key, key)


def _extract_threshold(line: str) -> tuple[float | None, str | None]:
    """Parse the first numeric threshold from a line; return (value, unit)."""
    m = _THRESHOLD_RE.search(line)
    if m is None:
        return None, None
    value = float(m.group("value"))
    unit = _normalise_unit(m.group("unit"))
    return value, unit


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class QuestionChecklistParser:
    """Rule-based parser for checklist items.

    Converts a plain-text or JSON checklist document into a list of
    :class:`ChecklistQuery` objects suitable for storage in ``checklist_queries``
    and subsequent processing by :class:`AnswerPipeline`.

    No LLM calls — all parsing is deterministic keyword matching.
    """

    PATTERNS: list[tuple[str, str | None, list[str], str | None, str | None]] = _PATTERNS

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def parse(self, checklist_text: str) -> list[ChecklistQuery]:
        """Parse a plain-text or JSON checklist into ChecklistQuery objects.

        If *checklist_text* starts with ``[`` or ``{`` it is treated as the
        ``submittal_checklists`` JSONB ``items`` array; otherwise each non-blank
        line becomes one query.
        """
        stripped = checklist_text.strip()
        if stripped.startswith(("[", "{")):
            return self._parse_json(stripped)
        return self._parse_text(stripped)

    # ------------------------------------------------------------------
    # Plain-text branch
    # ------------------------------------------------------------------

    def _parse_text(self, text: str) -> list[ChecklistQuery]:
        """Parse newline-separated checklist items (one per line)."""
        queries: list[ChecklistQuery] = []
        for i, line in enumerate(text.splitlines()):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            query = self._match_line(f"item-{i + 1:03d}", line)
            queries.append(query)
        return queries

    # ------------------------------------------------------------------
    # JSON branch
    # ------------------------------------------------------------------

    def _parse_json(self, json_text: str) -> list[ChecklistQuery]:
        """Parse a submittal_checklists JSONB items array.

        Accepts either:
          - A JSON array of objects with at least ``{"description": "..."}``
          - A JSON object with an ``"items"`` key containing such an array

        Optional object keys consumed:
          ``item_id``, ``code_ref``, ``threshold_value``, ``threshold_unit``,
          ``target_entity_class``, ``measurement_types``, ``filter_predicates``
        """
        raw = json.loads(json_text)
        if isinstance(raw, dict):
            items: list[dict[str, object]] = raw.get("items", [])  # type: ignore[assignment]
        elif isinstance(raw, list):
            items = raw  # type: ignore[assignment]
        else:
            return []

        queries: list[ChecklistQuery] = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            description: str = str(item.get("description", "")).strip()
            if not description:
                continue

            item_id: str = str(item.get("item_id", f"item-{i + 1:03d}"))

            # Allow the JSON to pre-specify structured fields; fall back to
            # keyword matching when they are absent.
            if "target_entity_class" in item and item["target_entity_class"] is not None:
                target_cls: str | None = str(item["target_entity_class"])
                meas_types: list[str] = list(item.get("measurement_types", []))  # type: ignore[arg-type]
                code_ref: str | None = str(item["code_ref"]) if item.get("code_ref") else None
                threshold_value: float | None = (
                    float(item["threshold_value"]) if item.get("threshold_value") is not None else None
                )
                threshold_unit: str | None = (
                    str(item["threshold_unit"]) if item.get("threshold_unit") else None
                )
                filter_preds: list[dict[str, str]] = list(
                    item.get("filter_predicates", [])  # type: ignore[arg-type]
                )
            else:
                matched = self._match_line(item_id, description)
                target_cls = matched.target_entity_class
                meas_types = matched.measurement_types
                code_ref = matched.code_ref
                threshold_value = matched.threshold_value
                threshold_unit = matched.threshold_unit
                filter_preds = matched.filter_predicates

            queries.append(
                ChecklistQuery(
                    item_id=item_id,
                    description=description,
                    target_entity_class=target_cls,
                    filter_predicates=filter_preds,
                    measurement_types=meas_types,
                    code_ref=code_ref,
                    threshold_value=threshold_value,
                    threshold_unit=threshold_unit,
                )
            )
        return queries

    # ------------------------------------------------------------------
    # Matching logic
    # ------------------------------------------------------------------

    def _match_line(self, item_id: str, line: str) -> ChecklistQuery:
        """Match *line* against PATTERNS using keyword search (case-insensitive).

        Returns a :class:`ChecklistQuery` with as many fields filled as the
        pattern supplies; any threshold is extracted from the line text itself.
        """
        lower = line.lower()
        matched_cls: str | None = None
        matched_meas: list[str] = []
        matched_code: str | None = None
        matched_unit: str | None = None

        for keyword, entity_cls, meas_types, code_ref, unit in self.PATTERNS:
            if keyword.lower() in lower:
                matched_cls = entity_cls
                matched_meas = list(meas_types)
                matched_code = code_ref
                matched_unit = unit
                break

        # Try to pull a threshold out of the line text.
        threshold_value, threshold_unit = _extract_threshold(line)
        # If no unit was found in the line, fall back to the pattern's unit.
        if threshold_unit is None:
            threshold_unit = matched_unit

        return ChecklistQuery(
            item_id=item_id,
            description=line,
            target_entity_class=matched_cls,
            filter_predicates=[],
            measurement_types=matched_meas,
            code_ref=matched_code,
            threshold_value=threshold_value,
            threshold_unit=threshold_unit,
        )
