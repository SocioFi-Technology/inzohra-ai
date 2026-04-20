# Prompt 01 — Phase 00: Foundations (week 1)

Prerequisite: `BOOTSTRAP: READY` from Prompt 00.

## Goal

Upload the 2008 Dennis Ln plan set, see all 19 sheets enumerated, title-block fields extracted with bbox, clickable from UI to PDF page.

## Build

1. **Postgres + pgvector schema.** Confirm migrations in `db/migrations/` cover: `projects`, `submittals`, `documents`, `sheets`, `entities`, `measurements`, `findings`, `external_review_comments`, `reviewer_actions`, `llm_call_log`, `retrieval_log`, `code_sections`, `amendments`, `cross_doc_claims`, `agency_policies`, `jurisdictional_packs`, `extractor_versions`, `rule_versions`. Add any missing. Every table carries `created_at` and relevant version stamps.
2. **S3 / MinIO buckets.**
   - `inzohra-raw` — uploaded documents, write-once.
   - `inzohra-raster` — page rasters at two resolutions (thumb @ 144 DPI, extract @ 300 DPI).
   - `inzohra-crops` — bbox crops cached per finding.
   - `inzohra-output` — rendered PDF/DOCX letters.
3. **Redis queues.** `ingestion`, `measurement`, `review`, `rendering`. Each a BullMQ (Node) or RQ (Python) queue with dead-letter handling.
4. **PDF ingestion pipeline.** In `services/ingestion/app/pipelines/plan_set.py`:
   - Hash the uploaded file (SHA-256).
   - Dedupe by hash.
   - Open with PyMuPDF; for each page, produce thumb raster and extract raster; persist to `inzohra-raster` with keys `{document_id}/{page}/thumb.png` and `{document_id}/{page}/extract.png`.
   - Write `documents` and `sheets` rows. `sheets.declared_scale` left null; `sheets.sheet_identifier` left null; both filled in Phase 01.
5. **TitleBlockAgent** in `services/ingestion/app/extractors/title_block.py`:
   - Input: one page's extract-raster + its native text layer.
   - Output: `TitleBlockExtraction` (Pydantic) with fields: `project_name`, `project_address`, `apn`, `permit_number`, `sheet_identifier_raw`, `sheet_title`, `designer_of_record`, `stamp_present: bool`, `date_issued`, `scale_declared`, `north_arrow_bbox`. Every field carries `{bbox, confidence}`.
   - Dual-track: run PyMuPDF text extraction over the title-block region first; pair with a Claude Sonnet vision call over the raster crop. On disagreement, emit the field at low confidence and log both.
   - `version = "1.0.0"`. Persist to `entities` with `type = "title_block"`.
6. **Next.js shell** with sheet viewer.
   - Route: `/projects/[id]/sheets/[sheetId]`.
   - Left rail lists sheets by discipline.
   - Center pane renders the PDF page via PDF.js.
   - Title-block extracted fields render as a collapsible panel on the right, each with a "show source" toggle that highlights the bbox on the sheet.
7. **Fixture ingestion smoke.** A script `uv run scripts/ingest_fixture.py` should:
   - Upload `fixtures/2008-dennis-ln/plan-set.pdf`.
   - Create the project if not exists (matched by address + permit).
   - Run the plan-set pipeline.
   - Print the list of 19 extracted sheet identifiers and, for each, the title-block extraction with bboxes.

## Acceptance criteria

- [ ] Fixture ingestion completes in under 3 minutes on a laptop.
- [ ] All 19 sheets appear in Postgres `sheets` table.
- [ ] At least 17/19 title blocks have `project_address = "2008 Dennis Ln"` (the fixture includes one where `1966 Dennis Ln` appears — this is the known bug BV comment #X catches; flag the mismatch in the metadata but do not fix it).
- [ ] UI at `/projects/[id]/sheets/[sheetId]` renders the PDF and the extracted title-block fields with working bbox highlights.
- [ ] `pnpm test:fixture --phase 00` passes.

When complete, commit on a branch `phase/00-foundations`, open a PR, and report `PHASE 00: SHIPPED`. Do not touch Phase 01 until the PR merges.
