# Fire & Life Safety skill

## Scope
CFC + HSC §13131.x + NFPA 13R/72. Deferred submittals, separation ratings, R-2.1 special requirements, fire-department access.

### Covers
- Deferred-submittal flagging for sprinklers (NFPA 13R) and alarms (NFPA 72).
- Separation ratings between occupancies per CBC Table 508.4.
- R-2.1 + HSC §13131.5 triggers (licensed 24-hr care facilities).
- Fire Department access requirements (per Santa Rosa FD memos in the jurisdictional pack).
- Fire-extinguisher locations.
- Smoke alarms and CO alarms per CRC R314/R315.

### Defers
- Sprinkler-design adequacy → licensed fire-protection engineer, `requires_licensed_review`.
- Alarm-system design adequacy → licensed designer, `requires_licensed_review`.
- Fire-rated assembly adequacy (as built) → `requires_licensed_review`.

## Frequent citations (Santa Rosa)
- **CBC §508** — Mixed occupancies.
- **CBC Table 508.4** — Required separation of occupancies.
- **CFC Ch 9** — Fire protection systems.
- **HSC §13131.5** — Residential care occupancy Type V one-hour.
- **NFPA 13R** — Residential sprinklers.
- **NFPA 72** — Fire alarm and signaling code.

## Gotchas
- **R-2.1 with > 6 occupants + residential care** triggers Type V one-hour construction per HSC §13131.5. This is the canonical "not obvious from CBC" finding.
- 1-hour door between R-2.1 and R-3 with self-closing hardware and labeling — frequently underspecified.
- NFPA 13R deferred submittal for sprinklers: comment note required on plans stating the deferred path.

## Worked example

### Example 1 — Missing 1-hour separation door specs
R-2.1 to R-3 separation door shown on plans; door schedule shows no rating, no self-closing hardware.
**Rule:** `FIRE-SEP-001`.
> *The door separating the R-2.1 and R-3 portions (Sheet A-1.2) is shown without a fire-resistance rating. CBC Table 508.4 requires a 1-hour rated assembly with rated, self-closing door. Update door schedule to specify 45-min rating, self-closing hardware, and labeling for R-3/R-2.1 separation door.*

## Decision tree
- Missing deferred-submittal note → `provide`.
- Separation rating missing or incorrect → `revise` AND `requires_licensed_review`.
- R-2.1 construction-type mismatch → `revise` AND `requires_licensed_review`.
