# Prompt 02 — Phase 01: Sheet identity & Plan Integrity (weeks 2–3)

Prerequisite: Phase 00 shipped and merged.

## Goal

System emits BV comments 1, 4, 8, 9, 18, 24 automatically on the fixture; catches the `1966 Dennis Ln` title-block error and the `A-1.1`/`E-1.0` sheet-identifier mismatch; every finding cites a real retrieved section. This is the first demoable milestone.

## Build

1. **SheetIdentifierParser** (`services/ingestion/app/extractors/sheet_identifier.py`).
   - Input: `TitleBlockExtraction` + page raster.
   - Output: `SheetIdentifier` with `discipline_letter` (G/A/S/M/E/P/T/F), `sheet_number`, `sheet_type` (`site_plan` / `floor_plan` / `elevation` / `section` / `details` / `schedule` / `code_notes` / `cover`), `raw_id`, `canonical_id`, confidences.
   - Populate the discipline taxonomy in `packages/shared/src/taxonomy/disciplines.py`.
2. **SheetIndexAgent** (`services/ingestion/app/extractors/sheet_index.py`).
   - Parse the cover sheet or index sheet for the declared sheet list.
   - Output: `SheetIndex` = list of `(declared_id, declared_title)`.
   - Run a reconciler against actual parsed sheet IDs: missing (in index, not in set), orphan (in set, not in index), mismatched-id (appears in both but IDs differ), mismatched-title.
3. **Code-RAG v0** (`services/review/app/codekb/`).
   - Load CBC §107 family and CBC Ch 11B into `code_sections`. Chunk by subsection; embed each chunk (OpenAI `text-embedding-3-large` or a local embedder — locked behind a provider-agnostic interface).
   - Implement `lookup_section`, `search_code`, `resolve_citation`, `get_amendments` (returning empty for phase 01 — amendments arrive with the Santa Rosa pack in Phase 08).
   - Add a Santa Rosa jurisdiction row with empty amendment set for now. Every retrieval takes `(jurisdiction, effective_date)` and honors it even when amendments are empty.
4. **PlanIntegrityReviewer** (`services/review/app/reviewers/plan_integrity.py`) with 15 rules.
   - `PI-TITLE-001` — title block mismatched across sheets (the 1966 Dennis Ln case).
   - `PI-INDEX-001` — sheet present in set but missing from index.
   - `PI-INDEX-002` — sheet in index but missing from set.
   - `PI-INDEX-003` — sheet ID mismatch between index and title block (the A-1.1/E-1.0 case).
   - `PI-INDEX-004` — sheet title mismatch between index and title block.
   - `PI-STAMP-001` — sheet missing designer-of-record stamp where required.
   - `PI-SCALE-001` — floor plan missing declared scale.
   - `PI-NORTH-001` — site plan missing north arrow.
   - `PI-SHEET-NUMBERING` — sheets non-sequential within a discipline.
   - `PI-CODECYCLE-001` — declared code cycle on title block doesn't match project-wide declaration.
   - `PI-ADDR-001` — address mismatch between title block and submittal metadata.
   - `PI-PERMIT-001` — permit number mismatch.
   - `PI-DATE-001` — title-block date older than submittal date by >90 days.
   - `PI-TEXT-OVERLAP-001` — overlapping text strings on a sheet (LLM residue rule).
   - `PI-REV-CLOUD-001` — revision clouds present but revision table missing.
   - Each rule: typed Python, fixture-driven test (positive + negative), reads entities via tools, cites retrieved code, emits through `emit_finding`.
5. **Reviewer UI** — discipline tabs (G/A/S/M/E/P/T/F); findings panel with:
   - Severity chip, sheet-ref chip, confidence indicator.
   - Bbox crop with red-annotation markup.
   - Citation chip that opens a right-side drawer with frozen retrieved text, amendment chain (empty for now), and source link.
   - Approve / Edit / Reject actions; edits persisted as `reviewer_actions`.

## Acceptance criteria

- [ ] Running the full pipeline on 2008 Dennis Ln emits, at minimum, findings that correspond to BV comments 1, 4, 8, 9, 18, 24.
- [ ] Every finding has a `citations[].frozen_text` populated and a `citations[].retrieval_chain` logged.
- [ ] Reviewer UI renders findings grouped by discipline, each with a working bbox crop and a working citation drawer.
- [ ] All 15 PlanIntegrity rules have positive + negative fixture tests.
- [ ] `pnpm test:fixture --phase 01` passes.

When complete, commit on `phase/01-sheet-identity`, open PR, report `PHASE 01: SHIPPED`.
