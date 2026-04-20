"""Citation canonicalisation utilities.

Every finding includes a citation with a ``canonical_id`` string. The same
section can be referenced in many ways: "§107.2", "CBC 107.2", "Table 508.4",
"§11B-404.2.3", "R310.2.1". This module produces a single stable ID.

Rules (per ``skills/code-rag/SKILL.md``):
- ``§1017.2`` → ``CBC-1017.2``
- ``Table 508.4`` → ``CBC-TBL-508.4``
- ``§11B-404.2.3`` → ``CBC-11B-404.2.3``
- ``R310.2.1`` → ``CRC-R310.2.1``
- ``§150.0(f)`` → ``CEnC-150.0-f``

Unresolvable inputs return ``None``.  **Never** guess.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Normalisation patterns (checked in order; first match wins)
# ---------------------------------------------------------------------------

# Residential codes: R prefix (R310.2.1)
_RESIDENTIAL_RE = re.compile(r"^(?:CRC\s*§?\s*)?R(\d+(?:\.\d+)*)$", re.IGNORECASE)

# Energy code subsection parenthetical: 150.0(f)
_ENERGY_SUB_RE = re.compile(
    r"^(?:CEnC|Title\s*24\s*Part\s*6)?\s*§?\s*(\d+\.\d+)\s*\(([a-z0-9]+)\)$",
    re.IGNORECASE,
)

# Accessibility (Chapter 11B): §11B-404.2.3
_ACCESS_RE = re.compile(
    r"^(?:CBC\s*)?§?\s*11B[-\s]?(\d+(?:\.\d+)*)$",
    re.IGNORECASE,
)

# Tables: Table 508.4 or Table 716.1(2)
_TABLE_RE = re.compile(
    r"^(?:(CBC|CRC|CMC|CPC|CEC|CFC|CEnC|CalGreen)\s*)?"
    r"Table\s+"
    r"(\d+(?:\.\d+)*(?:\([^)]+\))?)$",
    re.IGNORECASE,
)

# Generic CBC/administrative: §107.2 or CBC 107.2.1 or [A]107.1
_CBC_RE = re.compile(
    r"^(?:(CBC|CRC|CMC|CPC|CEC|CFC|CEnC|CalGreen)\s*)?"
    r"\[?[A-Z]?\]?\s*§?\s*"
    r"(\d+(?:\.\d+)*)$",
    re.IGNORECASE,
)


_DEFAULT_CODE = "CBC"


def resolve_citation(citation_string: str) -> str | None:
    """Return a canonical section ID, or ``None`` when unparseable."""
    if not citation_string:
        return None
    s = citation_string.strip()

    # Strip trailing punctuation / whitespace / code-book labels
    s = re.sub(r"[;,\s]+$", "", s)

    m = _RESIDENTIAL_RE.match(s)
    if m:
        return f"CRC-R{m.group(1)}"

    m = _ENERGY_SUB_RE.match(s)
    if m:
        return f"CEnC-{m.group(1)}-{m.group(2).lower()}"

    m = _ACCESS_RE.match(s)
    if m:
        return f"CBC-11B-{m.group(1)}"

    m = _TABLE_RE.match(s)
    if m:
        code = (m.group(1) or _DEFAULT_CODE).upper()
        sect = m.group(2).replace(" ", "")
        return f"{code}-TBL-{sect}"

    m = _CBC_RE.match(s)
    if m:
        code = (m.group(1) or _DEFAULT_CODE).upper()
        return f"{code}-{m.group(2)}"

    return None


def format_section_number(canonical_id: str) -> str:
    """Pretty-print for display: ``CBC-107.2`` → ``CBC §107.2``."""
    if "-TBL-" in canonical_id:
        code, _, number = canonical_id.partition("-TBL-")
        return f"{code} Table {number}"
    if canonical_id.startswith("CRC-R"):
        return f"CRC §{canonical_id[5:]}"
    if canonical_id.startswith("CBC-11B-"):
        return f"CBC §11B-{canonical_id[len('CBC-11B-'):]}"
    if canonical_id.startswith("CEnC-") and "-" in canonical_id[5:]:
        rest = canonical_id[5:]
        base, _, sub = rest.rpartition("-")
        return f"CEnC §{base}({sub})"
    code, _, number = canonical_id.partition("-")
    return f"{code} §{number}"
