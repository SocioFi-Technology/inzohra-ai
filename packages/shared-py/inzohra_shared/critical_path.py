"""Critical-path rule IDs. See docs/17-invariants-and-risks.md invariant #6.

Any rule in this set always sets ``requires_licensed_review = true``.
Any rule not in this set must not set the flag.
"""
from __future__ import annotations

CRITICAL_PATH_RULES: frozenset[str] = frozenset(
    {
        # Structural
        "STR-SHEAR-ADEQUACY",
        "STR-HOLDOWN-CAPACITY",
        "STR-FRAMING-SIZING-ADEQUACY",
        "STR-FOUNDATION-ADEQUACY",
        # Architectural
        "ARCH-OCCUPANT-LOAD-CALC",
        "ARCH-EGRESS-CAPACITY-HIGH-LOAD",
        # Fire / Life Safety
        "FIRE-SEP-RATING-ADEQUACY",
        "FIRE-R21-TYPE-V-ONE-HOUR",
        "FIRE-OPENING-PROTECTIVE-ADEQUACY",
        # Electrical
        "ELEC-SERVICE-SIZE-ADEQUACY",
        # Mechanical
        "MECH-LOAD-CALC-ADEQUACY",
        # Fire / Life Safety — Phase 05
        "FIRE-NFPA13R-REQUIRED",
        "FIRE-ALARM-REQUIRED",
        "FIRE-HSC13131-TYPE-V",
        "FIRE-SEP-RATING-508",
        # Structural — Phase 05
        "STR-HEADER-SIZING",
        "STR-PLUMB-WALL-STUDS",
        # Mechanical — Phase 05
        "MECH-HVAC-DEDICATED",
        # Energy — Phase 05
        "EN-HERS-SIGNED-DECL",
    }
)


def requires_licensed_review(rule_id: str) -> bool:
    return rule_id in CRITICAL_PATH_RULES
