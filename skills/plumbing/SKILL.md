# Plumbing skill

## Scope
California Plumbing Code. Fixture counts, water heater, accessible shower, trap arms, backflow, DWV sizing.

### Covers
- Fixture counts per occupant load (CPC Ch 4).
- Water heater location, venting, seismic strapping.
- Accessible shower compliance (also 11B-608).
- Trap arm lengths.
- Backflow prevention on hose bibs, irrigation, etc.
- DWV sizing consistency.

### Defers
- Water pressure calcs → licensed professional.
- DWV adequacy for unusual configurations → `requires_licensed_review`.

## Frequent citations
- **CPC §402** — Minimum fixture counts.
- **CPC §501** — Water heaters general.
- **CPC §504** — Water heater requirements (TPR valve, drain, seismic).
- **CPC §1007** — Trap arms.
- **CPC §603** — Backflow prevention.

## Gotchas
- Water heaters in garages must be on a platform 18" above floor OR listed for flammable-vapor-ignition-resistant (FVIR) — often missed.
- Seismic strapping required at top and bottom thirds.
- Tankless water heater venting has specific termination clearances frequently violated.

## Decision tree
- Missing required fixture → `provide`.
- Incorrect venting or seismic → `revise`.
- Backflow preventer missing at a required location → `provide`.
