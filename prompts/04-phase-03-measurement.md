# Prompt 04 — Phase 03: Measurement stack v1 (weeks 6–8)

The hardest phase. Deserves the longest time. Prerequisite: Phase 02 shipped.

## Goal

Door clear widths reported on the fixture, window NCO computed for every new bedroom, egress travel distances on the path-of-travel plan, confidence intervals on every measurement.

## Build

1. **ScaleResolver** — reads the declared scale from title block or viewport labels. Outputs a ratio (pixels per inch at given DPI).
2. **ScaleCalibrator** — verifies declared scale against known-dimension anchors on the drawing. Picks the strongest anchor (longest dim line with clear OCR'd text) and cross-checks. Confidence drops when anchors disagree.
3. **DimensionTextAgent** — OCR tuned for architectural notation (feet-inches, fractions, decimal feet). Outputs `(value_ft, value_in, raw_text, bbox, confidence)`.
4. **DimensionGeometryAgent** — OpenCV for dim lines, extension lines, leader lines, tick marks. Pairs each dim-text bbox with its dim-line geometry.
5. **FloorPlanGeometryAgent** — vision model (Claude Sonnet) + geometric primitives. Extracts walls (segments with thickness + classification), rooms (polygons), doors (symbol + swing), windows (symbol), stairs/ramps. Tags each with its schedule reference where one exists.
6. **DerivedMetricsEngine** — areas from polygons, door clear widths, window NCO, egress distance (straight-line for now — doorway routing comes in Phase 09), exit separation, accessible route widths, turning spaces, stair rise/run, ramp slopes.
7. **Tool surface** — implement every `measure_*` tool per `docs/09-reasoning-tools.md`. Each returns `value, unit, confidence, trace, bbox`.
8. **UI measurement-override workflow.** Every measurement in the UI is clickable. Click opens the derivation trace: every sub-layer's contribution, each source bbox, intermediate values. Reviewer can override with a manual value; override is persisted to `measurements.override_history` and emits a `reviewer_action`.
9. **Confidence composition.** `final = product(sublayer_confidences)`, capped at 0.99, floored at 0.30. Per-measurement-type minimums enforced at emission time.

## Acceptance criteria

- [ ] Every new bedroom window in the fixture has an NCO value + confidence.
- [ ] Every door has a clear-width value + confidence.
- [ ] Egress travel distance computed from each bedroom to an exit.
- [ ] PDF-quality classifier tags the fixture as `vector` (it's a vector PDF). Confidence for vector sources ≥ 0.90 on 80% of measurements.
- [ ] Override workflow tested end-to-end: a reviewer can click a measurement, see its trace, override, and see the override persist and the confidence update.
- [ ] `pnpm test:fixture --phase 03` passes.

Commit on `phase/03-measurement`, PR, report `PHASE 03: SHIPPED`.
