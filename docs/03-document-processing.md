# § 03 — Document processing pipelines

Seven canonical document types. Each has its own pipeline; all share the shape: **classify → split → extract → validate → store**.

## Canonical document types

- **`PLAN_SET`** — Architectural, structural, MEP drawing packages. Multi-sheet PDFs with title blocks, sheet indexes, drawings, schedules, code notes, details. Every sheet is an independent unit with its own sheet identifier and extractors.
- **`TITLE24_REPORT`** — CEC compliance reports (CF1R, RMS-1, MF1R, load calcs). Stable form templates; highly tabular. Dedicated form parsers per CEC document class.
- **`PLAN_CHECK_LETTER`** — Correspondence from the AHJ or their plan-review contractor (Bureau Veritas, Willdan, 4Leaf). Structured comments with response slots and review-round typography.
- **`NARRATIVE`** — Code-analysis narratives, design basis memos, fire-protection narratives. Prose; extracted into structured claims.
- **`QUESTION_CHECKLIST`** — Designer-side pre-submittal verification list. See §08.
- **`DEFERRED_SUBMITTAL`** — Sprinklers, elevators, solar, anything filed after the main permit.
- **`SUPPORTING_DOC`** — Catch-all for manufacturer cut sheets, product approvals, etc.

## Per-type pipelines

### PLAN_SET

1. Split into pages; detect sheet boundaries; raster each page at two resolutions (low-res for UI thumbs, high-res for extraction).
2. Run `TitleBlockAgent` on each page for project metadata.
3. Run `SheetIdentifierParser` to assign discipline and sheet type.
4. Dispatch per-sheet specialists: floor plans → `FloorPlanGeometryAgent`, schedules → `ScheduleAgent`, code notes → `CodeNoteAgent`, details → `DetailCalloutAgent`, elevations → `ElevationAgent`.
5. Run `SheetIndexAgent` across the set to reconcile the table of contents.
6. Trigger measurement stack for every floor plan, elevation, and section with a scale.

### TITLE24_REPORT

1. Detect CEC form class (CF1R-PRF-01-E, RMS-1, MF1R, etc.).
2. Apply form-specific parsers: header block → project metadata; envelope table → surfaces with area, U-factor, R-value; HVAC table → system specs; DHW table; building summary; compliance declaration.
3. Emit reconciled `cross_doc_claim` candidates for R-values, climate zone, conditioned area, sprinklered status.

### PLAN_CHECK_LETTER

1. Parse header (project, address, permit, reviewer, date, round).
2. Parse numbered comments grouped by discipline, each with comment text, code citation(s), embedded image snippet (if present), and response slot.
3. Extract review-round typography (italic/bold/underlined → round 1/2/3).
4. Emit every parsed comment as an `external_review_comment` record (round tracking + learning loop).

### NARRATIVE

1. Paragraph-level segmentation with heading detection.
2. Claim extraction: occupancy classification statements, construction-type declarations, sprinkler design basis, fire-zone determinations, code-cycle declarations.
3. Cross-reference each claim to the matching plan-set assertion; feed into reconciliation layer.

### QUESTION_CHECKLIST

Covered in `docs/08-question-checklist-agent.md`. Each question is parsed into a structured query (target entity, target measurement or code-rule test) and answered against extracted measurements + retrieved code.

## Extraction invariants

- Every extracted field carries `{document_id, page, bbox, extractor_version, confidence}`.
- Every extractor runs at `temperature=0` with a fixed JSON schema enforced via structured output.
- Vision extractors are always paired with the text layer for the same region; disagreements become low-confidence flags, not silent reconciliations.
- Re-runs are cheap and encouraged. A new extractor version processes the same document independently; old entities are retained for diffing, not deleted.
