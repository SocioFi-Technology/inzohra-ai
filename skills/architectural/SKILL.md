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

### Example 3 — AR-EGRESS-WIN-001: bedroom egress window NCO too small (BV comment #2)
Bedroom window tag W-3 has measured NCO 4.8 sqft; sill height 46 in.
**Rule:** `AR-EGRESS-WIN-001`.
> *The egress window at Bedroom 3 (tag W-3, Sheet A2.1) has a net clear opening of 4.8 sq ft and a sill height of 46 inches above finish floor. CRC §R310.2.1 requires a minimum net clear opening of 5.7 sq ft; CRC §R310.2.4 limits the sill height to 44 inches. Revise the window schedule and rough opening to comply with both requirements.*

### Example 4 — AR-TRAVEL-001: exit access travel distance (BV comment #15)
Measured egress path from room at rear of floor to exit door: 268 ft.
**Rule:** `AR-TRAVEL-001`.
> *The exit access travel distance from the rear bedroom on the second floor (Sheet A2.2) to the exit door measures approximately 268 feet. CBC §1017.2.2 limits exit access travel distance in Group R-3 occupancies to 250 feet. Revise the floor plan layout or provide an additional exit to comply.*

### Example 5 — AR-EXIT-SEP-001: exit separation (BV comment #14)
Two exits on second floor are 18 ft apart; building diagonal 72 ft; required minimum 36 ft.
**Rule:** `AR-EXIT-SEP-001`.
> *The two required exits on the upper floor (Sheet A2.2) are approximately 18 feet apart (edge to edge). CBC §1014.3 requires exits to be separated by at least one-half the maximum overall diagonal of the floor (36 feet for this floor). Revise the exit locations to achieve the required separation.*

## Decision tree
- Rule-emittable checks (clear-width, NCO, travel distance, exit separation) → deterministic rule with measurement backing → `revise`.
- Narrative-consistency checks → LLM tail → `clarify`.
- Occupant-load disagreements → emit finding AND set `requires_licensed_review=true`.
