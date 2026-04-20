# Measurement skill (cross-cutting)

## Scope
Loaded by the measurement stack (Layer 4). Governs scale resolution, calibration protocol, confidence composition, PDF-quality degradation rules.

## Protocol

1. **Read declared scale** from the title block / viewport notation. Parse architectural notation (`1/4" = 1'-0"`, `3/16" = 1'-0"`, etc.) into a numeric ratio.
2. **Calibrate** against at least one known-dimension anchor on the drawing. Anchor = a dimension text + a dim-line geometry whose pixel length is measurable. Use the longest anchor with the highest-confidence OCR.
3. **Cross-check** declared vs calibrated. If delta > 2%, flag with reduced confidence and prefer calibrated.
4. **PDF-quality class** is read from `sheets.pdf_quality_class`:
   - `vector` — full confidence envelope.
   - `hybrid` — text vector, images raster. Reduced confidence on vision-derived geometry.
   - `raster` — -20% confidence floor. Disable egress-path doorway routing until reviewer provides calibration anchors.
   - `low_quality_scan` — most measurements disabled; reviewer must set anchors manually.

## Confidence composition
`final = product(sublayer_confidences)` capped at 0.99, floored at 0.30. Per-measurement-type minimums:
- Accessibility clear-widths: ≥ 0.90.
- Egress travel distance: ≥ 0.75.
- Room area: ≥ 0.80.
- Window NCO: ≥ 0.85.

## Override rules
Reviewer override is a single click in the UI. The override is persisted with timestamp and reviewer ID; the override value is treated as confidence = 1.0 from that point forward for this project; the original value is retained for comparison in the learning loop.

## Gotchas
- Fractional dimensions (e.g. `3'-7 1/2"`) OCR poorly; pair OCR with geometry-based inference and take the higher-confidence reading.
- Sheets with multiple scales (plan + inset detail) need per-viewport calibration, not per-sheet.
- Elevations and sections may use different scales than floor plans on the same sheet.
