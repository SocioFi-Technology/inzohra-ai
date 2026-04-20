# Extraction skill (cross-cutting)

## Scope
Loaded by extraction agents. Governs dual-track extraction (text + vision), bbox provenance rules, confidence scoring, disagreement handling.

## Dual-track protocol
Every extractor pairs:
1. **Native text** extraction via PyMuPDF. Fast, exact on vector PDFs; degrades on raster.
2. **Vision** extraction via Claude Sonnet over the rasterized region. Handles raster and vector equally; slower and more expensive.

Both tracks run on the same bbox region. Results are compared:
- **Agreement** — emit at high confidence.
- **Disagreement** — emit at low confidence with both values; flag for reviewer attention.
- **One track empty** — emit the populated track at reduced confidence.

## Bbox provenance
- Every extracted field carries `{bbox, page, extractor_version, confidence, source_track}`.
- Never emit a field without a bbox unless it is a pure derivation of other fields (each of which has its own bbox).
- Bbox coordinates are PDF points (72 DPI base), not pixels.

## Confidence scoring
- Schema-matched values with both tracks agreeing: 0.95 baseline.
- Schema-matched but only one track present: 0.70 baseline.
- Disagreement: 0.40 baseline.
- Per-field penalties: low-contrast region, tight bbox, suspected font mismatch.

## Retries and versioning
- Re-runs are idempotent and encouraged. A new `extractor_version` processes the same document independently; old entities retained.
- Version bumps on schema change or prompt change.

## Gotchas
- Stamped/sealed plans often have the stamp overlapping title-block text; vision track is more robust here.
- Hand-written notes in the margins are almost always vision-track only and should be marked as such.
- Rotated pages (landscape within a portrait set) need explicit orientation handling; otherwise bboxes come out transformed.
