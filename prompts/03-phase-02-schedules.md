# Prompt 03 — Phase 02: Schedules & structured extraction (weeks 4–5)

Prerequisite: Phase 01 shipped and merged.

## Goal

Reconciled project profile on a mixed submittal; BV letter parsed into 58 structured comments; R-value mismatch between plans and Title 24 flagged automatically.

## Build

1. **ScheduleAgent** (`services/ingestion/app/extractors/schedule.py`).
   - Specializations: `door_schedule`, `window_schedule`, `fastener_schedule`, `holdown_schedule`, `wall_schedule`.
   - Input: a sheet typed as `schedule` + its raster.
   - Output: a canonical schedule with typed rows, each row with its bbox and source page.
   - Table-detection via a hybrid approach: PyMuPDF for native tables; Claude Sonnet vision fallback for scanned or image-based schedules.
2. **CodeNoteAgent** — parse code-note blocks (typically on sheet G-0.x or A-0.x). Emit structured `code_note` entities with the code reference and the designer's statement.
3. **Title24FormAgent** — per form class (CF1R-PRF-01-E, RMS-1, MF1R).
   - Header block → project metadata.
   - Envelope table → surfaces with `(area, U-factor, R-value)`.
   - HVAC table → system specs.
   - DHW table → water heating specs.
   - Building summary, compliance declaration.
4. **ReviewLetterAgent** — parse BV-style plan-check letters.
   - Header block.
   - Numbered comments grouped by discipline; each comment with text, citation, embedded image, response slot.
   - Review-round typography (italic / bold / underlined → round 1/2/3).
   - Persist every comment as `external_review_comments`.
5. **CrossDocClaimBuilder** — for each claim type (`occupancy_class`, `construction_type`, `conditioned_area`, `climate_zone`, `sprinklered`, `r_value_wall_2x6`, etc.):
   - Gather every asserting entity across documents.
   - Build a `cross_doc_claim` row with `{value, sources[], conflicts[]}`.
   - On conflict, emit a PlanIntegrity finding (rule `PI-CROSSDOC-001`) with severity `clarify`.
6. **Code-RAG expansion** — CBC Ch 5, 10; CEnC §150; CPC Ch 4.
7. **Fixture verification.**
   - On ingesting the BV letter fixture, `external_review_comments` table should contain 58 rows.
   - On reconciliation, the R-0 (plans) vs R-19 (Title 24) wall mismatch should emit a finding with both sources attached.

## Acceptance criteria

- [ ] Door, window, fastener, and holdown schedules parsed into canonical rows on the fixture.
- [ ] CF1R and RMS-1 in the fixture parsed into structured Title 24 entities.
- [ ] BV letter parsed into 58 external_review_comments.
- [ ] R-value mismatch flagged as a cross-doc-claim inconsistency.
- [ ] `pnpm test:fixture --phase 02` passes.

Commit on `phase/02-schedules`, PR, report `PHASE 02: SHIPPED`.
