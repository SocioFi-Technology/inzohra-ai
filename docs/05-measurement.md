# § 05 — The measurement sub-system

The hardest layer. Six sub-layers turn pixels into code-checkable quantities.

## Sub-layer 1 — Scale resolution

Read the declared scale from the title block and/or viewport labels. Scales in architectural plans are typically `1/4" = 1'-0"`, `3/16" = 1'-0"`, `1/8" = 1'-0"`. Elevations and sections often use different scales than floor plans on the same sheet.

## Sub-layer 2 — Reference calibration

Verify declared scale against known-dimension anchors on the drawing (e.g., a dimension string reading `24'-0"` between two points whose pixel distance we can measure). Calibration produces a confidence score; low confidence triggers a reviewer alert.

## Sub-layer 3 — Dimension-text OCR

Architectural notation tuned OCR:
- Feet-inches formats: `24'-6"`, `24'-6 1/2"`, `24' 6"`, `24ft-6in`.
- Decimal feet: `24.5'`.
- Fractions: `1/2"`, `5/8"`, `3'-7 3/4"`.

Produces `(value_ft, value_in, raw_text, bbox, confidence)`.

## Sub-layer 4 — Dimension-geometry detection

Classical CV (OpenCV) for:
- Dimension lines (long thin lines with arrowheads/ticks at both ends).
- Extension lines (perpendicular guide lines).
- Leader lines (connecting callout to feature).
- Matching dim lines to their OCR'd values by proximity and orientation.

## Sub-layer 5 — Floor-plan entity extraction

Vision model (Claude Sonnet) + geometric primitives to extract:
- **Walls** — line segments with thickness, classified as exterior / interior / demising / shear.
- **Rooms** — polygons formed by wall segments, labeled by room-name callouts.
- **Doors** — door symbol + tag, swing arc, hinge side.
- **Windows** — window symbol + tag, dimensions from schedule reference.
- **Stairs / ramps** — polylines with rise/run or slope.

Each entity is tagged with its schedule reference (e.g., door `#3`, window `W-4`) and its bounding geometry.

## Sub-layer 6 — Derived metrics

Given calibrated scale + extracted geometry, compute:
- **Room areas** — from room polygons.
- **Door clear widths** — from door-opening extraction (accounting for swing direction).
- **Window net clear openings (NCO)** — height × width after sash-depth adjustment.
- **Egress travel distance** — longest path from any occupiable point to an exit, routed through doorways.
- **Exit separation** — greatest distance between any two exits divided by overall diagonal.
- **Accessible route widths** — at their narrowest point.
- **Bathroom turning space diameters**, **stair rise/run**, **ramp slopes** — per CBC 11B geometry.

Each derived metric is stored as its own entity with a full derivation trace.

## The measurement tool surface

```
get_sheet_scale(sheet_id) → {declared, calibrated, confidence}
measure_distance(sheet_id, point_a, point_b) → inches
get_room_dimensions(sheet_id, room_id) → {width, length, area, height}
get_door_specs(sheet_id, door_tag) → {width, height, type, rating, swing}
get_window_specs(sheet_id, window_tag) → {width, height, sill, NCO}
measure_egress_path(sheet_id, start, end) → feet
measure_between(sheet_id, entity_a, entity_b) → inches
get_accessible_route(sheet_id, from, to) → {width_min, slope, x_slope}
verify_dimension(sheet_id, bbox) → {text_val, geom_val, match}
```

## Confidence, override, and degraded modes

Confidence flows up the stack. If calibration is `0.97`, geometry is `0.85`, and metric composition adds `0.02` uncertainty, final confidence is the product (capped/floored). Each finding displays its measurement confidence alongside. Per-rule thresholds:

- Accessibility rules: `≥ 0.90`.
- Coarse egress distance: `≥ 0.75`.

Below threshold → auto-flagged for reviewer attention.

**PDF-quality classifier** (vector / hybrid / raster / low-quality-scan) runs at ingest. Raster sources carry a systematic confidence penalty. Some measurement types (egress path routing) are disabled on raster/scan until the reviewer provides calibration anchors manually.

Every measurement in the UI is clickable → opens the derivation trace → every sub-layer's contribution, the source bbox, intermediate values. Reviewer override is a single click; overrides are logged and become training signal.
