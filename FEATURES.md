# Inzohra-ai — Feature catalog

The complete feature set for the multi-agent, retrieval-grounded plan-review platform. Every feature traces to a doc section (`docs/NN-*.md`), a build prompt (`prompts/NN-*.md`), and one or more skill files (`skills/*/SKILL.md`).

---

## 1 · Intake and document processing

**What it does.** Receives plan sets, Title 24 reports, narratives, fire-review memos, prior-round plan-check letters, deferred submittals, and designer question-checklists. Normalizes every document into a structured, provenance-stamped form.

- Deduplication by SHA-256 content hash.
- Per-page thumbnail raster (144 DPI) + extraction raster (300 DPI) persisted to object storage.
- Page-level orientation and rotation handling.
- Document type classifier (plan set / Title 24 / narrative / fire review / plan check letter / deferred submittal / checklist) via Claude Haiku.
- Per-page PDF-quality classification: `vector` / `hybrid` / `raster` / `low_quality_scan` — drives measurement confidence envelopes downstream.
- Full-text extraction via PyMuPDF for vector PDFs; vision-based fallback via Claude Sonnet for raster and scanned inputs.
- Idempotent re-ingestion: rerunning a newer extractor version produces additional append-only entities, never overwriting prior output.

*Docs § 3 · Prompts 01 · Skill `extraction`.*

## 2 · Sixteen extraction agents

Structured-entity extractors, each with a Pydantic schema and a dual-track (text + vision) protocol.

1. **TitleBlockAgent** — project name, address, APN, permit number, designer of record, stamp, date, declared scale, north arrow.
2. **SheetIdentifierParser** — discipline letter, sheet number, canonical ID, sheet type.
3. **SheetIndexAgent** — the cover-sheet sheet-list with reconciliation against actual parsed sheets.
4. **CodeNoteAgent** — code-note blocks with citation references.
5. **ScheduleAgent** — doors, windows, fasteners, holdowns, walls, fixtures.
6. **FloorPlanGeometryAgent** — rooms, walls, doors, windows, stairs, ramps.
7. **DetailBubbleAgent** — detail callouts and their cross-references.
8. **DimensionTextAgent** — architectural dimension OCR tuned for feet-inches.
9. **DimensionGeometryAgent** — dim lines, extension lines, ticks via OpenCV.
10. **Title24FormAgent** — CF1R, RMS-1, MF1R headers, envelope tables, HVAC/DHW rows.
11. **ReviewLetterAgent** — parses BV-style plan-check letters into structured comments with typography → round mapping.
12. **CrossDocClaimBuilder** — aggregates claims (occupancy class, R-value, climate zone, etc.) across documents with conflict detection.
13. **RevisionCloudAgent** — detects revision clouds on resubmittals and links them to prior-round comments.
14. **QuestionChecklistAgent** — parses designer-side submittal checklists into structured queries.
15. **NarrativeAgent** — code-analysis narrative into occupancy / construction type / compliance path statements.
16. **FireMemoAgent** — Santa Rosa FD (or equivalent) memos.

*Docs § 3, 7 · Prompts 01, 03 · Skill `extraction`.*

## 3 · Measurement stack — six sublayers, tool API

- **L4-a ScaleResolver** — reads declared scale from title block / viewport.
- **L4-b ScaleCalibrator** — verifies against known-dimension anchors; computes calibrated ratio.
- **L4-c DimensionTextAgent** — numeric dimension OCR.
- **L4-d DimensionGeometryAgent** — geometric dim/ext lines.
- **L4-e FloorPlanGeometryAgent** — rooms, walls, doors, windows, stairs, ramps as typed polygons.
- **L4-f DerivedMetricsEngine** — areas, clear widths, NCO, egress travel (w/ doorway routing in v2), exit separation, route widths, turning spaces, stair rise/run, ramp slopes.

**Tool API (9 tools):** `measure_distance`, `measure_area`, `measure_door_clear_width`, `measure_window_nco`, `measure_egress_travel_distance`, `measure_exit_separation`, `measure_accessible_route`, `measure_turning_space`, `measure_stair_rise_run`. Each returns `(value, unit, confidence, trace, bbox)`; trace carries every sublayer's contribution.

**PDF-quality-aware confidence envelope.** Reviewer-override workflow persists override history with reviewer ID and rationale, feeding the learning loop.

*Docs § 5, 9 · Prompt 04 · Skill `measurement`.*

## 4 · Code knowledge base and retrieval (code-RAG)

**What it stores.** California state codes (CBC, CRC, CEC, CMC, CPC, CFC, CalGreen, CEnC, HSC selectively), chunked at the subsection level with embeddings; jurisdictional amendments in a separate `amendments` table with date windows; agency policies as supplementary context.

**Seven tools.** `lookup_section`, `search_code`, `resolve_citation`, `get_amendments`, `get_agency_policies`, `get_referenced_standards`, `get_cross_references`.

- Every retrieval parameterized by `(jurisdiction, effective_date)`.
- Precedence chain: base state text → amendments (in declared order) → agency policies (advisory).
- Retrieval chain logged in full to `retrieval_log`; attached to every finding that uses it.
- Embeddings computed on unamended text so amendment churn doesn't invalidate the vector index.
- Canonical ID resolution (e.g. `§1017.2` → `CBC-1017.2`).
- Frozen excerpts travel with every finding; the model never paraphrases code text from weights.

*Docs § 6, 9 · Prompt 02 · Skill `code-rag`.*

## 5 · Ten discipline reviewers (~370 rules total at Phase 5)

Each reviewer pairs (a) deterministic typed rules that fire first and (b) an LLM-reasoning tail over residue.

| Reviewer | Phase 1 rules | Phase 5 target | Focus |
|---|---|---|---|
| PlanIntegrity | 15 | 40 | Sheet coherence, documentation consistency |
| Architectural | — | 60 | Egress, occupant load, mixed occupancy, openings |
| Accessibility | — | 80 | CBC Chapter 11B mechanical checks |
| Structural | — | 40 | Documentation-level, licensed-review-flagged |
| Mechanical | — | 30 | CMC + CEnC §150 |
| Electrical | — | 35 | CEC: GFCI/AFCI, §210.70, service, grounding |
| Plumbing | — | 30 | CPC fixture counts, water heater, accessible |
| Energy | — | 25 | Title 24 Part 6 consistency |
| FireLifeSafety | — | 25 | CFC, HSC §13131.x, NFPA 13R/72 |
| CalGreen | — | 30 | Title 24 Part 11 |

Every finding carries full provenance: `rule_id + version`, evidence entities with bboxes, measurements with traces, citations with frozen text and retrieval chains, confidence score, and a `requires_licensed_review` flag when on the legal critical path.

*Docs § 7, 10 · Prompts 02, 05, 06 · 10 discipline skills.*

## 6 · Critical-path and licensed-review guardrails

- Authoritative list of `requires_licensed_review` rules maintained in `packages/shared/src/critical-path.ts` (and Python mirror).
- No such finding can be auto-approved. The UI marks them explicitly; a licensed reviewer must sign off.
- Disclaimer on every exported artefact: *Inzohra-ai is a reviewer's assistant, not a substitute for licensed professional judgment.*

*Docs § 14, 17.*

## 7 · Cross-document reconciliation

Every substantive claim (occupancy, construction type, conditioned area, climate zone, sprinklered, R-values, U-factors, stories, fire-hazard zone, flood zone, code cycle) is aggregated across sources into a `cross_doc_claim`. Conflicts surface as PlanIntegrity findings with all sources attached — **this is how the R-0-on-plans vs R-19-on-Title-24 mismatch surfaces automatically.**

*Docs § 4 · Prompt 03.*

## 8 · Letter generation (PDF + DOCX + JSON)

- `CommentDrafterAgent` produces jurisdiction-dialect comments with few-shot examples from the pack.
- `LetterAssemblerAgent` groups findings by discipline in BV's canonical order, renumbers letter-wide, inserts letterhead / project block / general instructions / signature block from the pack.
- **Round typography renderer:** italic round-1, bold round-2, underlined round-3, exactly matching the BV convention on 2008 Dennis Ln.
- Bbox crops embedded inline with red-annotation markup (BV comments 8, 9 style).
- Calibri typography, BV margins, consistent header/footer.
- Three formats: PDF (send), DOCX (edit), JSON bundle (permit-tracking-system integration).

*Docs § 11 · Prompt 07 · Skill `jurisdiction-santa-rosa`.*

## 9 · Reviewer workspace (3-pane + letter preview)

- **Left pane** — project navigator: documents by type; plan set expanded into sheets grouped by discipline, each with open-findings badge.
- **Center pane** — sheet viewer: PDF.js with two overlays (extracted entities, findings with bbox crops); measurement tool tap-to-measure with live scale.
- **Right pane** — findings panel: per-finding tiles with severity chip, sheet ref, editable draft text, citation drawer (frozen text + amendment chain + source link), bbox crop, confidence indicator, licensed-review flag, evidence-chain expander, and actions (approve / edit / merge / split / reject). Batch actions for discipline-scoped approval.
- **Bottom pane** — live letter preview with round selector.
- Keyboard-first navigation; dense engineering-grade display; progressive disclosure of evidence chains.

*Docs § 12 · Prompts 01, 02, 05.*

## 10 · Designer portal (Question-Checklist agent)

- Upload flow for plans + checklist (PDF / DOCX / pasted / library).
- Parsed-query confirmation step before answer pipeline kicks off.
- Three answer views: (1) question-by-question report, (2) plan-set annotation overlay, (3) remediation queue.
- Designer-severity labels: `attention` / `recommend` / `optional` (distinct from reviewer severity).
- Curated jurisdictional checklist library (Santa Rosa SFR checklist parsed and stored).
- Custom-checklist upload for design firms' internal QC processes.

*Docs § 8 · Prompt 10 · Skill `jurisdiction-santa-rosa`.*

## 11 · Learning loop and evaluation harness

- **ComparisonAgent** aligns AI findings to parsed external-review comments (matched / missed / false-positive / partial) via Hungarian assignment over sheet-ref + citation + fuzzy text match.
- **Per-rule metrics.** Precision, recall, F1, sample size, mean reviewer edit distance, mean time-to-approve. Refreshed nightly into `rule_metrics`.
- **Per-discipline and per-jurisdiction aggregates.** Trend lines, heatmaps.
- **Triage queues.** Misses (authority flagged, AI didn't), false-positives (AI flagged, authority didn't), edits (reviewer-edited approved findings), overrides (measurement overrides grouped by type and PDF-quality class). Action buttons to add rules, tune thresholds, add exceptions, deprecate rules.
- **Prompt and retriever hot-swap.** Shadow deployment: new version and old run in parallel; comparison surfaces; promotion after fixture-regression-green.
- **Regression gating.** `pnpm test:fixture` asserts no regression on previously-matched comments; CI blocks merge on any drop.

*Docs § 13 · Prompt 08.*

## 12 · Jurisdictional packs and multi-jurisdiction support

- **Pack specification** — amendments (with operation type and effective_date windows), agency policies, submittal checklists, drafter few-shot examples, letter templates, fee schedules.
- **Resolver** — walks state → amendments → agency policies precedence on every retrieval, honoring `effective_date`.
- **Santa Rosa pack** — complete at Phase 08 (~100 engineering hours).
- **Second-city pack** — target 60 hours, used to validate the pack-authoring tooling and documentation.
- **Pack-authoring tooling** — upload, validate, diff against existing, dry-run on a sample project.
- **Per-jurisdiction metrics** — a rule's P/R is tracked per-jurisdiction; regressions visible per pack.

*Docs § 6 · Prompt 09.*

## 13 · Provenance and data-model invariants

- Every artefact carries `{document_id, page, bbox, extractor_version, rule_version, prompt_hash}`.
- Append-only storage across entities, measurements, findings, external_review_comments, reviewer_actions, llm_call_log, retrieval_log.
- UUIDv7 IDs internally; short public-facing random strings via mapping table.
- Six invariants locked in `docs/17-invariants-and-risks.md` — no phase may violate them.

*Docs § 4, 17.*

## 14 · Security, privacy, liability

- TLS 1.3 everywhere; encryption at rest on Postgres volumes and S3 (SSE-KMS).
- Tenant isolation via `tenant_id` scoping + Postgres row-level security.
- NextAuth + OIDC/SAML SSO for reviewer-firm integrations.
- Service-to-service auth via short-lived internal JWTs.
- Secrets in AWS Secrets Manager / Vault; nothing committed.
- PII inventory and retention policy per jurisdiction.
- Copyright compliance: California Building Standards text is publicly available; we cite and attribute.
- Licensed-professional liability: `requires_licensed_review` flag is structurally enforced; the final letter is signed by the licensed reviewer under their own license; contractual allocation of responsibility; E&O insurance.
- Full audit log of reviewer and admin actions.

*Docs § 14.*

## 15 · Operations, observability, cost

- Horizontal scaling on all processing tiers; stateless workers with Redis queues.
- Postgres primary + read replicas; pgvector on primary; hot/warm/cold data tiers as volume grows.
- OpenTelemetry tracing; LLM-call logs with prompt hash / model / tokens / latency / cost; rule-evaluation logs; retrieval logs.
- Alerts: hallucination signals, precision drops, cost anomalies, queue backlogs, error-rate spikes.
- WAL-shipped Postgres backups with 30-day PITR; S3 versioning + Glacier after 90 days; quarterly restore drills.
- Cost envelope: $7–14 COGS per 50-sheet residential project at steady state. Pricing: $50–150/project designer; low-tens-of-thousands/year reviewer-firm contracts.

*Docs § 15.*

## 16 · Phase-gated development plan

Eighteen weeks from foundations to Bureau-Veritas-parity on Santa Rosa residential.

| Phase | Weeks | Deliverable |
|---|---|---|
| 00 | 1 | Foundations: schema, ingestion, title blocks, sheet viewer |
| 01 | 2–3 | Sheet identity + 15 PlanIntegrity rules → BV comments 1, 4, 8, 9, 18, 24 |
| 02 | 4–5 | Schedules, Title 24 forms, BV-letter parsing, cross-doc claims |
| 03 | 6–8 | Measurement stack v1 with overrides and confidence |
| 04 | 9–10 | Arch (60) + Access (80) reviewers → large BV-coverage leap |
| 05 | 11–12 | MEP + Structural + Energy + Fire + CalGreen → full BV parity |
| 06 | 13 | Drafter + letter assembler → indistinguishable-from-BV PDF |
| 07 | 14 | Learning loop: metrics, triage, hot-swap, regression gates |
| 08 | 15–16 | Second jurisdiction; pack-authoring tooling |
| 09 | 17–18 | Measurement v2 (doorway routing, PDF-quality classifier) + Question-Checklist agent |
| — | 19 | Finalize, production deploy, tag v1.0.0 |

Every phase ships a running product. The 2008 Dennis Ln fixture is common throughout so regression is visible at every milestone.

*Docs § 16 · Prompts 00–11.*

## 17 · Extensibility

- **Skills pattern, not fine-tuning.** New disciplines, jurisdictions, and checklist domains added as skill files + rule sets + pack entries. No model retraining.
- **Append-only** storage means old extractor / rule versions coexist with new ones; re-runs are cheap and reversible.
- **Open tool API.** Measurement, code-RAG, and entity-query tools are provider-agnostic; adding a new reasoning model requires only a new adapter.
- **Pack authoring.** Documented 30-hour path for adding a new jurisdiction by city 5.

*Docs § 7, 17 · Skill registry.*

---

## File map

```
inzohra-ai/
├── README.md                    · package overview
├── CLAUDE.md                    · master system prompt
├── FEATURES.md                  · this file
├── docker-compose.yml           · local dev stack
├── pyproject.toml · pnpm-workspace.yaml · package.json
├── .env.example
├── .claude/                     · project config + house rules + skills registry
├── docs/                        · 18 sections (§ 1–18)
├── prompts/                     · 12 phase prompts (00 bootstrap → 11 ship)
├── skills/                      · 14 skill files (10 disciplines + 4 cross-cutting)
├── schemas/                     · 6 JSON schemas (finding, entity, measurement, …)
├── db/
│   ├── migrations/              · 0001_baseline.sql, 0002_extractor_rule_versions.sql
│   └── scripts/migrate.sh
├── apps/web/                    · Next.js 14 app (reviewer + designer portals)
├── services/
│   ├── ingestion/               · Python · extractors, pipelines
│   ├── measurement/             · Python · 6-sublayer measurement stack
│   ├── review/                  · Python · 10 reviewers, code-KB, comparison
│   └── rendering/               · Node · letter assembler
├── packages/
│   ├── shared/                  · TS · zod schemas, critical-path list
│   └── shared-py/               · Python · critical-path, LLM wrapper
├── ops/runbooks/                · incident, LLM outage, fixture regression, pack promotion, restore
└── fixtures/2008-dennis-ln/     · canonical reference fixture (README only in repo)
```
