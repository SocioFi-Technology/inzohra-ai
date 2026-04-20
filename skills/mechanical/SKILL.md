# Mechanical skill

## Scope
CMC + CEnC §150. Dedicated HVAC per occupancy, bath exhaust, kitchen hood, attic ventilation, duct insulation, outside-air ventilation.

### Covers
- Dedicated HVAC per occupancy in mixed-occupancy projects.
- Bath exhaust sizing and termination.
- Kitchen hood type and makeup-air requirement.
- Attic ventilation calc (1:150 or 1:300 ratio).
- Duct insulation per climate zone.
- Outside-air ventilation rates.

### Defers
- HVAC load calculation adequacy → licensed professional.
- Structural support for equipment → StructuralReviewer (`requires_licensed_review`).
- Energy compliance path → EnergyReviewer.

## Frequent citations (Santa Rosa)
- **CMC §403** — Outside air supply.
- **CMC §504** — Environmental air exhaust.
- **CMC §505** — Domestic range hoods.
- **CEnC §150.0(m)** — Duct insulation.
- **CBC §1202.2** — Attic ventilation.

## Gotchas
- Range hoods over 400 CFM require makeup-air per CMC §505.2.
- Mixed-occupancy (R-2.1 + R-3) requires dedicated HVAC per occupancy — frequent BV finding.
- Bath exhaust must terminate outside the building, not into the attic.

## Worked examples

### Example 1 — Shared HVAC in mixed occupancy
Narrative declares R-2.1 + R-3 mixed use; mechanical plan shows one shared unit.
**Rule:** `MECH-OCCUPANCY-001`.
> *The mechanical plan (Sheet M-1.0) shows a single HVAC unit serving both the R-2.1 and R-3 portions of the building. CMC §403 and the mixed-occupancy separation require dedicated HVAC per occupancy. Revise to provide separate systems.*

## Decision tree
- Schedule/callout mismatch → `clarify` or `provide`.
- Code-required item missing → `provide`.
- Explicit code violation → `revise`.
- Load calc disagreements → `requires_licensed_review`.
