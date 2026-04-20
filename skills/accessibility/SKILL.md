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

### Example 3 — AC-PATH-001: path-of-travel trigger for addition/alteration (BV comment #22)
Kitchen remodel cost $42 k; accessible path to kitchen blocked by 29-inch doorway.
**Rule:** `AC-PATH-001`.
> *The kitchen alteration (Sheet A3.1) triggers path-of-travel requirements under CBC §11B-202.4. The doorway on the accessible route to the kitchen provides a 29-inch clear width, which does not meet the 32-inch minimum required by CBC §11B-404.2.3.1. Provide an accessible path of travel to the altered area or document that disproportionate cost applies.*

### Example 4 — AC-TURN-001: turning space (BV comment #34)
Accessible bathroom turning circle is 57 inches in diameter due to door swing intrusion.
**Rule:** `AC-TURN-001`.
> *The accessible bathroom (Sheet A3.2) shows a 57-inch turning diameter. CBC §11B-304.3.1 requires a circular turning space of 60 inches minimum diameter, clear of door swings. Revise the layout — relocate the door swing or enlarge the room — to provide a compliant turning space.*

### Example 5 — AC-TP-DISP-001: toilet paper dispenser (BV comment #40)
Toilet paper dispenser shown 11 inches in front of WC centerline, outlet at 52 inches AFF.
**Rule:** `AC-TP-DISP-001`.
> *The toilet paper dispenser (Sheet A3.3) is located 11 inches in front of the water closet centerline and 52 inches above finish floor. CBC §11B-604.7 requires the dispenser to be 7–9 inches in front of the water closet centerline, with the outlet between 15 and 48 inches above finish floor. Revise the dispenser location to comply.*

## Decision tree
- Geometric findings → rule + measurement → `revise`.
- Signage missing → `provide`; signage incorrect → `revise`.
- Measurement confidence < 0.90 → auto-flag for reviewer attention.
- This reviewer never sets `requires_licensed_review`.
