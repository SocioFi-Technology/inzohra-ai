# Architectural skill

## Scope
CBC Chapters 3, 4, 5, 7, 10. Egress, occupant load, mixed-occupancy separation, opening protection, code analysis, stair/ramp geometry.

### Covers
Egress (travel distance, common path, exit separation, corridor widths, dead-ends); occupant load per Table 1004.5; mixed-occupancy separation (§508); opening protection (Ch 7); stair/ramp geometry (Ch 10); code-analysis narrative consistency.

### Defers
Accessible route geometry → AccessibilityReviewer. Structural adequacy → StructuralReviewer. Fire-rated assembly adequacy → FireLifeSafetyReviewer (`requires_licensed_review`). Energy envelope → EnergyReviewer.

## Frequent citations (Santa Rosa)
- **CBC §1004** — Occupant load.
- **CBC §1005** — Means of egress sizing.
- **CBC §1006** — Number of exits and exit access doorways.
- **CBC §1017** — Exit access travel distance.
- **CBC §1020** — Corridors.
- **CBC §508** — Mixed occupancies.
- **CBC §712** — Vertical openings.
- **CBC Table 716.1(2)** — Opening fire protectives.
- **CRC R310** — Emergency escape and rescue openings.

## Gotchas
- R-2.1 with more than 6 occupants triggers HSC §13131.5 Type V one-hour — not obvious from CBC alone. Raise when the code-analysis narrative misclassifies.
- "Common path of travel" and "exit access travel distance" are distinct; both have limits and are commonly confused.
- Mixed-occupancy separation rating depends on the path chosen (separated vs non-separated); flag when plans assume one path but narrative declares the other.

## Worked examples

### Example 1 — Egress window NCO too small
Bedroom 2 egress window has NCO 4.2 sqft.
**Rule:** `ARCH-EGRESS-010`.
> *The egress window at Bedroom 2 (Sheet A-1.2) has a net clear opening of 4.2 sqft. CRC §R310.2.1 requires a minimum net clear opening of 5.7 sqft for emergency escape and rescue. Revise the window specification to comply.*

### Example 2 — Missing exit separation on upper floor
Two required exits measure 12 ft apart; overall diagonal 60 ft; required separation 30 ft.
**Rule:** `ARCH-EGRESS-020`.
> *The two required exits on the upper floor (Sheet A-1.2) are approximately 12 ft apart. CBC §1007.1.1 requires exit separation of at least half the overall diagonal (30 ft for this floor). Revise the exit layout to comply.*

## Decision tree
- Rule-emittable checks (clear-width, NCO, travel distance, exit separation) → deterministic rule with measurement backing → `revise`.
- Narrative-consistency checks → LLM tail → `clarify`.
- Occupant-load disagreements → emit finding AND set `requires_licensed_review=true`.
