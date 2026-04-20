# § 02 — System architecture: nine layers

Inzohra-ai is layered. Nine layers, bottom to top, each with a single concern, a defined tool surface, and a contract with its neighbors.

> **Nothing above Layer 7 writes directly to storage. Nothing below Layer 5 calls an LLM.**
> This discipline keeps the system defensible when a finding is challenged — every output traces down the stack to the pixels it came from.

## Layer 1 — Substrate

- **Postgres 16** with `pgvector` for relational data and embeddings.
- **S3-compatible object storage** (MinIO in dev, S3 in prod) for raw files, rasterized crops, rendered outputs.
- **Redis** for job queues and caching.
- An **append-only event log** records every extraction, every rule run, every LLM call, with `extractor_version`, `rule_version`, and `prompt_hash` on every artefact.
- Nothing in the system is mutable after commit. Re-runs produce new rows.

## Layer 2 — Intake and routing

- File hashing, deduplication, classification.
- Project matching on address / APN / permit number with fuzzy fallback.
- Submittal round detection (new / resubmittal / deferred).
- Document classifier covers six canonical types + one catch-all.

## Layer 3 — Extraction

Specialist agents per document type and per sheet type. Every extractor emits structured JSON against a fixed schema at `temperature=0`, with bounding-box provenance on every field. Input is dual-track: native text (PyMuPDF) + rasterized crops for vision.

Agents: `TitleBlockAgent`, `SheetIdentifierParser`, `SheetIndexAgent`, `FloorPlanGeometryAgent`, `SitePlanAgent`, `ScheduleAgent`, `CodeNoteAgent`, `ElectricalSymbolAgent`, `PlumbingSymbolAgent`, `StructuralCalloutAgent`, `Title24FormAgent`, `ReviewLetterAgent`, `NarrativeAgent`, `QuestionChecklistAgent`, `RevisionCloudAgent`, `DetailCalloutAgent`.

## Layer 4 — Measurement stack

Six sub-layers turn pixels into inches and inches into rooms and rooms into egress distances.

1. **Scale resolution** — read declared scale from title block / viewport.
2. **Reference calibration** — verify scale against known-dimension anchors.
3. **Dimension-text OCR** — architectural-notation-tuned.
4. **Dimension-geometry detection** — OpenCV for dim lines, extension lines, tick marks.
5. **Floor-plan entity extraction** — walls, rooms, doors, windows via vision + geometric primitives.
6. **Derived-metrics engine** — areas, NCO, egress distance, exit separation, accessible route widths, turning spaces, stair/ramp metrics.

Every measurement carries a confidence interval and a derivation trace. A reviewer can override any measurement; the override is logged and becomes training signal.

## Layer 5 — Reconciliation

Cross-document claim-building. The same fact (occupancy class, construction type, total conditioned area, climate zone, sprinkler system, R-values) is asserted across multiple documents. The reconciliation layer aggregates these into a single `cross_doc_claim` with all evidence. When sources disagree — plans say R-0 walls, Title 24 says R-19 — the reconciler emits an inconsistency finding with every conflicting source attached.

## Layer 6 — Reasoning tools

The callable API reviewer agents use. Three tool families: **measurement**, **code-RAG**, **entity-query**. See `docs/09-reasoning-tools.md` for full signatures. Every tool call returns provenance alongside its result.

## Layer 7 — Review engine

`ReviewCommander` dispatches to ten discipline workers mirroring Bureau Veritas structure: Plan Integrity, Architectural, Accessibility, Structural, Mechanical, Electrical, Plumbing, Energy, Fire & Life Safety, CalGreen. Each worker runs a two-pass pipeline: deterministic rules first, LLM residue second. Every finding emits with discipline, sheet reference, bbox evidence, code citation (state + amendments + agency policies), severity, and confidence.

## Layer 8 — Human review UI

A three-pane workspace (left: project navigator; center: sheet viewer with overlays; right: findings panel; bottom: live letter preview). Every approve / edit / merge / split / reject is logged as training signal.

## Layer 9 — Output

Final artefacts: a comment letter PDF in the reviewer firm's template, a parallel DOCX, and a JSON bundle for downstream integration. Revision-cloud detection ties resubmittals back to prior comments. Round-specific typography (italic/bold/underlined) matches the BV convention.

## Cross-cutting concerns

Three concerns thread every layer:

- **Provenance** — `{document_id, page, bbox, extractor_version, rule_version, prompt_hash}` on every artefact.
- **Jurisdiction** — every rule, retrieval, and citation resolves against `(jurisdiction, effective_date)`.
- **Evaluation** — every rule and finding type is measured against a fixture library with precision / recall / MAE tracked per rule, per discipline, per jurisdiction.
