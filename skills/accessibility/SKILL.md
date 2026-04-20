# Accessibility skill

## Scope
CBC Chapter 11B mechanically against measured geometry. Path of travel, turning spaces, reach ranges, signage, accessible kitchens and bathrooms.

### Covers
§11B-202 path-of-travel continuity; §11B-304 turning space; §11B-308 reach ranges; §11B-404 doors (clear width, hardware); §11B-603–608 toilet/bathing rooms; §11B-804 kitchens; §11B-703 signage.

### Defers
Substantive CASp field determinations. Structural anchoring of grab bars → StructuralReviewer (`requires_licensed_review`).

## Frequent citations (Santa Rosa)
- **CBC §11B-202** — Existing buildings and facilities.
- **CBC §11B-302** — Floor or ground surfaces.
- **CBC §11B-304** — Turning space.
- **CBC §11B-308** — Reach ranges.
- **CBC §11B-404.2.3** — Clear width of doorways.
- **CBC §11B-404.2.7** — Door hardware.
- **CBC §11B-603** — Toilet and bathing rooms.
- **CBC §11B-604** — Water closets.
- **CBC §11B-608** — Shower compartments.
- **CBC §11B-804** — Kitchens.

## Gotchas
- Clear width at doors is measured between the face of the door (when open 90°) and the stop on the opposite jamb — not the rough opening.
- 60" turning circle must be free of door swings; common error places the turning space where a door swings into it.
- Reach ranges: 48" max high, 15" min low; relaxed for side-reach with approach constraints.
- R-occupancy dwelling unit vs public accommodation: 11B applies differently; most SFR plans need only §11B-809 Type A provisions.

## Worked examples

### Example 1 — Insufficient clear floor space at toilet
Bathroom measures 16" from WC centerline to side wall.
**Rule:** `ACC-BATH-030`.
> *The accessible bathroom (Sheet A-1.2) provides 16" side clearance from the water closet centerline to the side wall. CBC §11B-604.2 requires a minimum of 18". Revise the layout to comply.*

### Example 2 — Turning space overlaps door swing
60" turning circle partially obstructed by inward-swinging door.
**Rule:** `ACC-TURNING-005`.
> *The required 60" turning space in the accessible bathroom (Sheet A-1.2) is partially obstructed by the inward-swinging door. CBC §11B-304.3 requires turning space to be clear of door swings. Revise the door swing or the turning space location.*

## Decision tree
- Geometric findings → rule + measurement → `revise`.
- Signage missing → `provide`; signage incorrect → `revise`.
- Measurement confidence < 0.90 → auto-flag for reviewer attention.
- This reviewer never sets `requires_licensed_review`.
