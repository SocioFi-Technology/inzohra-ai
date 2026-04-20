# § 16 — Development plan: phases, milestones, ownership

Eighteen weeks to Bureau-Veritas-parity on a Santa Rosa residential permit. Every phase ships a running product. Phases are sequential; the fixture (2008 Dennis Ln) is common throughout, so regression is visible at every milestone.

## Phase 00 — Foundations · week 1

**Build:** Postgres + pgvector schema, S3/MinIO buckets, Redis queues, PDF ingestion with page split and raster, `TitleBlockAgent` as reference extractor with bbox provenance, minimal Next.js shell with sheet viewer.

**Ship:** upload the 2008 Dennis Ln set, see all 19 sheets enumerated, title-block fields extracted with bbox, clickable from UI to PDF page.

## Phase 01 — Sheet identity and Plan Integrity · weeks 2–3

**Build:** `SheetIdentifierParser` with discipline taxonomy, `SheetIndexAgent` with consistency reconciler, 15 PlanIntegrity rules, code-RAG v0 covering CBC §107 and Chapter 11B, `lookup_section` and `search_code` tools, UI with discipline tabs and finding panel with bbox crops.

**Ship:** system emits BV comments 1, 4, 8, 9, 18, 24 automatically on the fixture; catches the 1966-Dennis-Ln title-block error and the A-1.1/E-1.0 sheet-identifier mismatch; every finding cites a real retrieved section. **First demoable milestone.**

## Phase 02 — Schedules and structured extraction · weeks 4–5

**Build:** `ScheduleAgent` specialized for doors/windows/fasteners/holdowns, `CodeNoteAgent`, `Title24FormAgent` for CF1R/RMS-1/MF1R, `ReviewLetterAgent` for BV-style letter parsing, `CrossDocClaimBuilder` for occupancy/area/climate-zone reconciliation, expand code-RAG to CBC Ch 5, 10 + CEnC §150 + CPC Ch 4.

**Ship:** reconciled project profile on a mixed submittal, BV letter parsed into 58 structured comments, R-value mismatch between plans and Title 24 flagged automatically.

## Phase 03 — Measurement stack v1 · weeks 6–8

The hardest phase; deserves the longest time. **Build:** `ScaleResolver`, `ScaleCalibrator`, `DimensionTextAgent` tuned for architectural notation, `DimensionGeometryAgent` with OpenCV, `FloorPlanGeometryAgent` combining vision and CV, `DerivedMetricsEngine` producing areas / NCO / egress distances / turning spaces, full `measure_*` tool family, UI measurement-override workflow with derivation trace.

**Ship:** door clear widths reported on the fixture, window NCO computed for every new bedroom, egress travel distances on the path-of-travel plan, confidence intervals on every measurement.

## Phase 04 — Architectural and Accessibility reviewers · weeks 9–10

**Build:** `ArchitecturalReviewer` with 60 rules (egress, occupant load, mixed-occupancy separation, opening protection); `AccessibilityReviewer` with 80 rules (11B-202, path of travel, kitchen, bath, reach, signage); LLM reviewer tail for narrative checks; expand code-RAG to full CBC Ch 10, Ch 11B, CRC R310–R317.

**Ship:** auto-generates BV comments 2, 10–17, 22, 25–38, 40, 42 on the fixture; first real precision/recall numbers vs BV letter; measurements back every size/distance finding.

## Phase 05 — MEP, Structural, Energy · weeks 11–12

**Build:** `MechanicalReviewer`, `ElectricalReviewer`, `PlumbingReviewer`, `StructuralReviewer`, `EnergyReviewer`, `FireLifeSafetyReviewer`, `CalGreenReviewer` scaffolds. All with rule sets and code-RAG coverage.

**Ship:** full BV-parity draft on the fixture, all 58 comments covered (matched or partial), miss and false-positive queues populated for triage.

## Phase 06 — Drafter and letter assembler · week 13

**Build:** `CommentDrafter` with jurisdictional-dialect few-shot, severity picker, `LetterAssembler` with PDF template, round-typography renderer, signature block and response slots, `RevisionCloudAgent` for resubmittal diffing.

**Ship:** reviewer approves in UI, PDF rolls out, letter indistinguishable from BV-authored at a glance, ready to send.

## Phase 07 — Learning loop · week 14

**Build:** `ComparisonAgent` for AI-to-BV alignment, miss and false-positive triage UI, per-rule precision/recall dashboard, reviewer edit-distance tracking, prompt and RAG hot-swap mechanism.

**Ship:** metrics visible on every rule, triage queue for adding new rules, regression tests blocking bad deploys.

## Phase 08 — Second jurisdiction · weeks 15–16

**Build:** jurisdiction-pack specification and tooling, Santa Rosa pack (complete first pack at ~100 hours), second-city pack (target 60 hours), jurisdiction resolver with precedence chain, per-jurisdiction evaluation scoping.

**Ship:** a project from city #2 processes end-to-end with correct amendments applied; pack-authoring documentation for future cities.

## Phase 09 — Measurement v2 and Question-Checklist agent · weeks 17–18

**Build:** PDF-quality classifier (vector/hybrid/raster/scan), egress-path with doorway routing, elevation-to-section height inference, structural framing span extraction, fixture library grown to 30 projects, full `QuestionChecklistAgent` with three answer views and remediation queue.

**Ship:** measurement override rate below 10% on fixtures, confidence bands tightened, scanned-PDF projects reviewable, Question-Checklist agent live for designer-portal users.

## Post-launch

Phase 10+: additional jurisdictions (one per month), additional disciplines (landscape, civil, fire-alarm specifics), integration with permit-tracking systems (Accela, EnerGov, Tyler EnerGov), commercial and nonresidential occupancies beyond R, a mobile companion for on-site review. The architecture supports all without structural change — additional packs, rules, skills.
