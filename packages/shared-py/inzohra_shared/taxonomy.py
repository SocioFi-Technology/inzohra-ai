"""Discipline + sheet-type taxonomy.

Keyed on the canonical California permit-set conventions:
    G — General / cover / index / abbreviations
    A — Architectural
    S — Structural
    M — Mechanical
    E — Electrical
    P — Plumbing
    T — Title 24 / energy
    F — Fire / life-safety
    C — Civil
    L — Landscape

Sheet-type vocabulary used by reviewers:
    cover          — G-0.x (index, abbreviations, code analysis summary)
    site_plan      — site/civil plan (north-arrow requirement applies)
    floor_plan     — architectural floor plan (scale requirement applies)
    elevation      — exterior / interior elevations
    section        — wall / building sections
    details        — construction details & schedules-as-drawings
    schedule       — door / window / finish schedule (tabular)
    code_notes     — notes, legends, accessibility diagrams
    egress_plan    — path-of-travel / exit plan
    structural     — framing / foundation / shear-wall plans
    mep            — mechanical / electrical / plumbing plans
    title24        — CF1R / energy-compliance sheet
    unknown        — fallback
"""
from __future__ import annotations

import re
from typing import Literal

DisciplineLetter = Literal[
    "G", "A", "S", "M", "E", "P", "T", "F", "C", "L", "?"
]

SheetType = Literal[
    "cover",
    "site_plan",
    "floor_plan",
    "elevation",
    "section",
    "details",
    "schedule",
    "code_notes",
    "egress_plan",
    "structural",
    "mep",
    "title24",
    "unknown",
]

DISCIPLINE_NAMES: dict[str, str] = {
    "G": "General",
    "A": "Architectural",
    "S": "Structural",
    "M": "Mechanical",
    "E": "Electrical",
    "P": "Plumbing",
    "T": "Title 24 / Energy",
    "F": "Fire / Life-Safety",
    "C": "Civil",
    "L": "Landscape",
    "?": "Unknown",
}

VALID_DISCIPLINE_LETTERS: frozenset[str] = frozenset("GASMEPTFCL")


# ---------------------------------------------------------------------------
# Sheet-type classification keywords — longest / most specific matched first.
# ---------------------------------------------------------------------------
_SHEET_TYPE_KEYWORDS: list[tuple[SheetType, tuple[str, ...]]] = [
    ("egress_plan",  ("path of travel", "exit plan", "egress plan")),
    ("title24",      ("title 24", "cf1r", "energy compliance", "t24")),
    ("schedule",     ("door schedule", "window schedule", "finish schedule",
                      "fixture schedule", "panel schedule")),
    ("elevation",    ("elevation",)),
    ("section",      ("section", "building section", "wall section")),
    ("details",      ("detail", "details")),
    ("cover",        ("cover", "sheet index", "index sheet", "abbreviation",
                      "general notes", "code analysis", "project data",
                      "sheet list")),
    ("site_plan",    ("site plan", "civil", "plot plan", "topograph")),
    ("floor_plan",   ("floor plan", "ground floor", "lower floor",
                      "first floor", "second floor", "partial plan",
                      "overall plan", "plan /")),
    ("code_notes",   ("code notes", "legend", "accessibility", "life safety",
                      "notes")),
    ("structural",   ("foundation", "framing", "shear", "roof plan")),
    ("mep",          ("mechanical plan", "electrical plan", "plumbing plan",
                      "lighting", "power plan", "hvac")),
]


# ---------------------------------------------------------------------------
# Canonical-ID parser.
# ---------------------------------------------------------------------------

# Matches: "A-1.1", "A1.1", "A 1.1", "G0.1", "E-1.0", "T-24", "S-01".
_ID_RE = re.compile(
    r"""
    ^\s*
    (?P<disc>[A-Z])       # discipline letter
    \s*[-\s\.]?\s*         # optional separator
    (?P<num>\d+(?:\.\d+)?)  # major(.minor)
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)


def parse_sheet_identifier(raw: str | None) -> tuple[str, str, str] | None:
    """Parse a raw title-block sheet identifier into (discipline, number, canonical).

    Returns ``None`` if the string cannot be interpreted as a sheet ID.

    Examples:
        "A-1.1"       -> ("A", "1.1",  "A-1.1")
        "A1.1"        -> ("A", "1.1",  "A-1.1")
        "a 1.1"       -> ("A", "1.1",  "A-1.1")
        "G-0.1"       -> ("G", "0.1",  "G-0.1")
        "T-24"        -> ("T", "24",   "T-24")
        "(none)"      -> None
        "1"           -> None   (no discipline letter)
        "x0.131"      -> None   (unknown discipline 'X')
    """
    if not raw:
        return None

    m = _ID_RE.match(raw)
    if not m:
        return None

    disc = m.group("disc").upper()
    if disc not in VALID_DISCIPLINE_LETTERS:
        return None

    num = m.group("num")
    canonical = f"{disc}-{num}"
    return disc, num, canonical


def classify_sheet_type(
    sheet_title: str | None,
    discipline_letter: str | None = None,
) -> SheetType:
    """Classify sheet type from (sheet title, discipline letter) heuristics.

    Keyword-based; deterministic. Falls back to discipline-letter defaults.
    """
    title = (sheet_title or "").lower().strip()

    # Direct keyword hit on the title
    for sheet_type, keywords in _SHEET_TYPE_KEYWORDS:
        for kw in keywords:
            if kw in title:
                return sheet_type

    # Discipline-letter fallbacks
    disc = (discipline_letter or "").upper()
    if disc == "G":
        return "cover"
    if disc == "S":
        return "structural"
    if disc in ("M", "E", "P"):
        return "mep"
    if disc == "T":
        return "title24"
    if disc == "C":
        return "site_plan"

    return "unknown"


def discipline_requires_stamp(discipline_letter: str) -> bool:
    """Return True when the sheet is on a discipline that requires a licensed stamp.

    Per CBC §107.3 / California Business & Professions Code §5536:
    Architectural, Structural, and MEP drawings generally require a
    licensed-professional stamp. General / cover sheets commonly carry the
    architect stamp but are not *independently* required.
    """
    return discipline_letter.upper() in {"A", "S", "M", "E", "P"}


def sheet_type_requires_scale(sheet_type: SheetType) -> bool:
    """Plans that must declare a scale per CBC §107.2.1."""
    return sheet_type in {"floor_plan", "elevation", "section",
                           "site_plan", "egress_plan", "structural"}


def sheet_type_requires_north_arrow(sheet_type: SheetType) -> bool:
    """Site plans carry a north arrow per CBC §107.2.5."""
    return sheet_type == "site_plan"
