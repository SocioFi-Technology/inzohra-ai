# Electrical skill

## Scope
California Electrical Code. Panel locations, GFCI/AFCI coverage, egress lighting, §210.70 lighting outlets, bedroom receptacle count, service size, grounding, tamper-resistant receptacles.

### Covers
- Panel locations per CEC §240.24.
- GFCI required locations (bath, kitchen, garage, outdoor, unfinished basements, crawlspaces).
- AFCI required circuits (dwelling-unit bedroom receptacles, etc.).
- Egress lighting per CBC §1008.
- §210.70 — lighting outlets in every habitable room and at egress points.
- Required receptacles per §210.52.
- Tamper-resistant receptacles in dwelling units (§406.12).

### Defers
- Load calculations for service sizing → `requires_licensed_review`.
- Grounding-electrode system adequacy → `requires_licensed_review`.

## Frequent citations
- **CEC §210.52** — Dwelling unit receptacle outlets.
- **CEC §210.70** — Lighting outlets required.
- **CEC §210.8** — GFCI protection.
- **CEC §210.12** — AFCI protection.
- **CEC §240.24** — Location of overcurrent devices.
- **CEC §406.12** — Tamper-resistant receptacles.

## Gotchas
- AFCI is required for all 120V 15/20A circuits supplying outlets in dwelling-unit bedrooms AND additional rooms per §210.12 (updates per code cycle — check effective_date).
- Bathroom receptacles require both GFCI and a dedicated 20A circuit (§210.11).
- §210.70(A)(1) — at least one wall-switch-controlled lighting outlet in every habitable room and bathroom.

## Decision tree
- Missing required receptacle / lighting outlet → `provide`.
- Wrong protection (missing GFCI/AFCI) → `revise`.
- Panel location violating §240.24 → `revise`.
- Service size questioned → `requires_licensed_review`.
