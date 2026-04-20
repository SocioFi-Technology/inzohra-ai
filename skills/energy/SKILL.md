# Energy skill

## Scope
Title 24 Part 6 (CEnC). Envelope consistency, HERS declarations, plan-to-T24 consistency, mixed-occupancy T24 path selection.

### Covers
- Envelope U-factor and R-value plan-to-T24 consistency.
- HERS measure declarations — presence and plan-note alignment.
- Climate-zone correctness.
- Mixed-occupancy T24 path selection.
- Prescriptive vs performance path declarations.

### Defers
- Energy modeling adequacy → licensed professional (CEA, Title 24 preparer).
- HERS verification in the field → HERS rater, out of scope.

## Frequent citations
- **CEnC §100.0** — Scope.
- **CEnC §100.0(f)** — Mixed-occupancy individual compliance.
- **CEnC §150.1** — Residential prescriptive requirements.
- **CEnC §150.0** — Mandatory measures.
- **CEnC §150.2** — Additions and alterations.

## Gotchas
- Mixed-occupancy (R-2.1 + R-3): each occupancy must comply individually per §100.0(f). Common miss — filed as SFR only.
- R-value mismatch between plans (sometimes R-0 on existing) and Title 24 (R-19 for new) → `revise` with both sources attached.
- HERS verified measures must be called out on plans with the specific measure identifier.

## Worked example

### Example 1 — Filed under wrong compliance path
Fire review confirms R-2.1 (licensed 24-hr care) occupancy; T24 filed as single-family residential.
**Rule:** `ENERGY-PATH-001`.
> *The Title 24 report (CF1R p.1) is filed as single-family residential per CEnC residential standards only, but the fire review and narrative confirm R-2.1 occupancy. CEnC §100.0(f) requires each occupancy to individually comply. Provide R-2.1 compliance under multifamily/nonresidential standards.*

## Decision tree
- Plan-to-T24 numeric mismatch (R-value, U-factor, SHGC) → `revise` with both sources.
- Wrong compliance path → `revise` with narrative + T24 cited.
- HERS measure not declared on plans → `provide`.
