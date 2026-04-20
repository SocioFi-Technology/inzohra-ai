# Prompt 10 — Phase 09: Measurement v2 & Question-Checklist agent (weeks 17–18)

Prerequisite: Phase 08 shipped.

## Goal

Measurement override rate below 10% on fixtures; confidence bands tightened; scanned-PDF projects reviewable; Question-Checklist agent live for designer-portal users.

## Build (Measurement v2)

1. **PDF-quality classifier** — classifies each page as `vector | hybrid | raster | low_quality_scan`. Confidence penalty applied per class; certain measurements (egress-path routing) disabled on `low_quality_scan` until reviewer provides calibration anchors.
2. **Egress-path doorway routing** — graph-based path from any occupiable point through doorways to an exit. Longest such path is the travel distance.
3. **Elevation-to-section height inference** — for height-dependent checks (headers, ceiling heights), extract from elevations and sections where floor plans don't carry the value.
4. **Structural framing span extraction** — read framing plans and infer spans between bearing points; feed to StructuralReviewer for header-sizing consistency checks.
5. **Fixture library growth** — from 1 to 30 residential projects. Mix of vector, hybrid, raster, and scanned inputs. Use to regression-test the measurement stack.
6. **Confidence recalibration** — using the expanded fixture library, recalibrate per-measurement-type confidence weights via isotonic regression on reviewer-override outcomes.

## Build (Question-Checklist agent)

1. **QuestionChecklistAgent** (`services/ingestion/app/extractors/question_checklist.py`):
   - Parse a checklist document (PDF / DOCX / pasted text / library selection) into structured queries.
   - Each query: target entity class, filter predicates, measurement(s), governing code section or explicit threshold.
   - Present parsed queries back to the designer for confirmation before answering.
2. **Answer pipeline** — for each query, dispatch to measurement and code-RAG tools exactly as a reviewer would. Assign status: `green` / `amber` / `red` / `unknown`.
3. **Designer-portal UI** (`apps/web/src/app/designer/`):
   - Upload flow for plans + checklist.
   - Three answer views: question-by-question report, plan-set annotation overlay, remediation queue.
   - Severity labels for designers: `attention`, `recommend`, `optional`.
4. **Designer-report rendering** — PDF with checklist answers, evidence, citations back to the jurisdiction's submittal checklist and code. Separate rendering template from the reviewer letter.
5. **Jurisdictional checklist library** — curated in `skills/jurisdiction-<n>/checklists/`. Santa Rosa's public submittal checklist parsed and stored. Designer firms can also upload their own internal checklists.

## Acceptance criteria

- [ ] PDF-quality classifier accuracy ≥ 95% on the 30-project fixture library.
- [ ] Measurement override rate ≤ 10% across the 30-project library.
- [ ] Scanned-PDF project (at least one in the library) processes end-to-end with calibration-anchor workflow.
- [ ] QuestionChecklistAgent parses a provided checklist into structured queries and answers all green/amber/red/unknown.
- [ ] Designer portal fully navigable with the three answer views.
- [ ] `pnpm test:fixture --phase 09` passes (now asserts over the 30-project library).

Commit on `phase/09-measurement-v2-qc-agent`, PR, report `PHASE 09: SHIPPED`.
