# Structural skill

## Scope
CBC Chapters 16, 22, 23. Documentation-level review of shear walls, holdowns, fastening, framing, and headers. **This reviewer does not verify structural adequacy — that is the licensed structural engineer's responsibility.** It reads what the engineer drew and flags cases where drawings disagree with schedules, schedules disagree with calculations, or callouts reference details that don't exist.

### Covers
- Shear-wall callouts complete and schedule-referenced.
- Holdowns present on schedule and anchored in foundation plan.
- Fastener schedule keys to callouts on the framing plans.
- Framing-member schedule rows for every called-out member.
- Header sizes noted where required by spans.
- Continuous load-path documentation.

### Defers
- Shear-wall adequacy → `requires_licensed_review`.
- Holdown capacity selection → `requires_licensed_review`.
- Framing-member sizing adequacy → `requires_licensed_review` (documentation inconsistencies flagged as `revise`).
- Seismic-analysis adequacy → out of scope.
- Foundation design → `requires_licensed_review`.

## Frequent citations (Santa Rosa)
- **CBC §1601–1613** — Structural design general.
- **CBC §2304** — General construction requirements for wood.
- **CBC §2305** — Lateral force-resisting systems, wood.
- **CBC §2308** — Conventional light-frame construction.
- **CBC Table 2304.10.2** — Fastening schedule.

## Gotchas
- Shear-wall type labels (e.g. SW-1, SW-2) called out on the framing plan must appear in the shear-wall schedule with their sheathing, nailing, and holdown type.
- Missing holdowns at the ends of shear walls is a common documentation omission; flag as `provide`.
- Fastener schedule must key to callouts used on the framing plan; orphaned callouts or schedule rows → `clarify`.

## Worked examples

### Example 1 — Shear-wall callout missing from schedule
Framing plan labels SW-3; shear-wall schedule lists only SW-1 and SW-2.
**Rule:** `STR-SHEAR-001`.
> *The framing plan (Sheet S-1.2) includes callout "SW-3" at the north exterior wall, but the shear-wall schedule on Sheet S-0.1 does not include an SW-3 entry. Provide the SW-3 specification in the schedule.*

### Example 2 — Holdown missing at shear wall end
Shear wall SW-1 callout at interior wall, no holdown symbol at either end.
**Rule:** `STR-HOLDOWN-005`.
> *The SW-1 shear wall on Sheet S-1.2 does not show holdowns at its end posts. Provide holdown callouts keyed to the holdown schedule.*

## Decision tree
- Callout without a matching schedule row → `provide` (not a compliance finding, but required documentation).
- Schedule row without a callout on any plan → `clarify`.
- Document-level conflict on sizing (schedule says 2x10, callout says 2x12) → `revise` AND `requires_licensed_review`.
- Anything that would require evaluating the structural calculations → emit as informational only with `requires_licensed_review=true`.
