# CLAUDE.md — Inzohra-ai master context

You are the engineering lead on **Inzohra-ai**, an automated reviewer and commenter agent for building-permit plan review. This file is the authoritative context you (Claude) operate under on every turn in this repository. Read it in full at the start of every new session; re-read it if you ever feel drift.

Target revision: `DOC-ARCH-002 · REV 0.1`
Primary fixture: `2008 Dennis Ln · Santa Rosa · CA · Permit B25-2734`
Code cycle: `2022 California Building Standards (Title 24, all parts)`

---

## 1. What you are building, in one paragraph

A multi-agent, retrieval-grounded system that ingests a permit submittal (plan sets, Title 24, fire review, narrative, question checklists) and produces a jurisdictional-grade comment letter. Every finding is tied to a sheet, a bounding region, a measured or extracted value, and a retrieved section of the governing code. The model paraphrases nothing from its parameters — it retrieves, cites, and defers to the human reviewer who owns the final letter. The system is a reviewer's assistant, never a decider on the legal critical path.

## 2. Non-negotiable invariants

These six invariants override every other instruction. If a task appears to require violating one, the task is wrong — not the invariant. Stop and flag.

1. **Provenance is sacred.** Every artefact (entity, measurement, finding, citation) carries `{document_id, page, bbox, extractor_version, rule_version, prompt_hash}`. Nothing is stored without it. Nothing is emitted without it.
2. **Immutability on commit.** Storage is append-only. Re-runs produce new rows, never overwrites. Old rows are retained for diffing.
3. **No code paraphrase from model weights.** Every code citation is a live retrieval from the code KB. The frozen retrieved text travels with the finding. The model never invents a citation.
4. **Deterministic rules before LLMs.** Every reviewer runs a two-pass pipeline: rules first, LLM only for the residue rules cannot decide. LLM temperature is always `0`. Output schemas are always structured.
5. **Jurisdiction + effective_date on every retrieval.** Codes are versioned at the section level. A project permitted on `2025-03-15` is forever reviewed against the text in effect on that date.
6. **`requires_licensed_review` on the legal critical path.** Occupant load, shear-wall adequacy, fire-rated assembly adequacy, and egress capacity at non-trivial occupant counts are always flagged for licensed sign-off, regardless of system confidence.

## 3. The nine-layer architecture

You are never writing "one big thing." You are writing nine layers, bottom to top, each with a single concern and a defined tool surface.

| Layer | Concern | Writes to | Calls LLMs? |
|---|---|---|---|
| 1 — Substrate | PG + pgvector, S3/MinIO, Redis, event log | storage | no |
| 2 — Intake | hash, dedupe, classify, project-match, round-detect | L1 | classifier only |
| 3 — Extraction | per-document / per-sheet specialist agents → structured JSON | L1 | yes (Sonnet, T=0) |
| 4 — Measurement | scale → calibration → geometry → derived metrics | L1 | yes (Sonnet vision) |
| 5 — Reconciliation | cross-document claims, conflicts | L1 | no |
| 6 — Reasoning tools | `measure_*`, `lookup_section`, entity queries | read-only | no |
| 7 — Review engine | 10 discipline workers, rules then LLM residue | findings | yes (Sonnet + Opus) |
| 8 — Reviewer UI | split-pane workspace, human approval, edit, log | reviewer actions | no |
| 9 — Output | comment-letter PDF/DOCX/JSON, round typography | storage | drafter (Sonnet) |

**Nothing above Layer 7 writes directly to storage.**
**Nothing below Layer 5 calls an LLM.**
These two rules keep the system defensible when a finding is challenged — every output traces down to the pixels it came from.

## 4. Agent topology — four tiers, ten reviewers

- **Intake tier** — `IntakeCommander` → `DocumentClassifier`, `ProjectMatcher`, `SubmittalRoundDetector`.
- **Extraction tier** — `ExtractionCommander` → `TitleBlockAgent`, `SheetIdentifierParser`, `SheetIndexAgent`, `FloorPlanGeometryAgent`, `ScheduleAgent`, `CodeNoteAgent`, `Title24FormAgent`, `ReviewLetterAgent`, `NarrativeAgent`, `QuestionChecklistAgent`, `RevisionCloudAgent`, `DetailCalloutAgent`, `ElectricalSymbolAgent`, `PlumbingSymbolAgent`, `StructuralCalloutAgent`.
- **Review tier** — `ReviewCommander` → `PlanIntegrityReviewer`, `ArchitecturalReviewer`, `AccessibilityReviewer`, `StructuralReviewer`, `MechanicalReviewer`, `ElectricalReviewer`, `PlumbingReviewer`, `EnergyReviewer`, `FireLifeSafetyReviewer`, `CalGreenReviewer`. Each mirrors a Bureau Veritas discipline one-to-one.
- **Output tier** — `OutputCommander` → `CommentDrafterAgent`, `LetterAssemblerAgent`, `ComparisonAgent`, `RoundRenderer`.

Every reviewer has the same tool surface and runs the same two-pass pipeline.

## 5. The tool surface (what agents call)

Three tool families. Every tool call returns provenance along with its result.

**Measurement**
```
get_sheet_scale(sheet_id) → {declared, calibrated, confidence}
measure_distance(sheet_id, point_a, point_b) → inches
get_room_dimensions(sheet_id, room_id) → {width, length, area, height}
get_door_specs(sheet_id, door_tag) → {width, height, type, rating, swing}
get_window_specs(sheet_id, window_tag) → {width, height, sill, NCO}
measure_egress_path(sheet_id, start, end) → feet
measure_between(sheet_id, entity_a, entity_b) → inches
get_accessible_route(sheet_id, from, to) → {width_min, slope, x_slope}
verify_dimension(sheet_id, bbox) → {text_val, geom_val, match}
```

**Code-RAG**
```
lookup_section(code, section, jurisdiction, effective_date)
search_code(query, code_filter, jurisdiction, effective_date)
get_table(table_id, jurisdiction, effective_date)
resolve_citation(citation_string) → canonical_id
get_amendments(state_section_id, jurisdiction_id)
get_referenced_standards(section_id)
check_effective_date(section_id, project_date)
```

**Entity-query (read-only)**
```
get_entity(entity_id); get_sheet(sheet_id)
list_rooms / list_doors / list_windows / list_fixtures
get_schedule(sheet_id, schedule_type); find_by_tag(project_id, tag)
cross_doc_claim(project_id, claim_type) → {value, sources, conflicts}
```

Full signatures and contracts: `docs/09-reasoning-tools.md` and `schemas/`.

## 6. Skills, not fine-tuning

Every discipline reviewer loads a **skill** (`skills/<discipline>/SKILL.md`) into context at review time. A skill contains:

- Scope (what the reviewer covers, what it defers to others).
- Catalogue of the most frequent code citations in that discipline for this jurisdiction.
- Common interpretations and known gotchas (e.g. R-2.1 with >6 occupants triggers HSC §13131.5 Type V one-hour — not obvious from CBC alone).
- Worked examples in the jurisdictional dialect.
- Decision tree: when to emit a finding vs defer to licensed review.

**You never fine-tune the model on code text.** Retrieval-first preserves pointer fidelity; fine-tuning freezes a snapshot.

## 7. The finding schema (memorize this)

```json
{
  "finding_id": "uuid",
  "project_id": "uuid", "submittal_id": "uuid", "review_round": 1,
  "discipline": "architectural | accessibility | structural | mechanical | electrical | plumbing | energy | fire_life_safety | calgreen | plan_integrity",
  "rule_id": "string", "rule_version": "string",
  "llm_reasoner_id": "string|null", "prompt_hash": "string|null",
  "severity": "revise | provide | clarify | reference_only",
  "requires_licensed_review": false,
  "sheet_reference": { "sheet_id": "string", "detail": "string|null" },
  "evidence": [
    { "entity_id": "uuid", "bbox": [x1,y1,x2,y2], "raster_crop_uri": "s3://…" },
    { "measurement_id": "uuid", "value": 4.2, "unit": "sqft", "confidence": 0.88, "trace": [] }
  ],
  "citations": [
    { "code": "CRC", "section": "R310.2.1", "jurisdiction": "santa_rosa",
      "effective_date": "2023-01-01", "frozen_text": "…", "retrieval_chain": [] }
  ],
  "draft_comment_text": "…",
  "confidence": 0.91,
  "created_at": "…", "extractor_versions_used": []
}
```

Severity follows the BV dialect: **Revise** (plans contradict code), **Provide** (missing info), **Clarify** (ambiguity), **Reference only** (awareness note).

## 8. House rules for code you write

- **Python**: 3.11, `uv` for envs, `ruff` + `mypy --strict` clean. `pydantic` v2 for every data contract. Never write a function that takes or returns an untyped dict.
- **TypeScript**: strict. Zod schemas for every API boundary. No `any`. Server components by default; client only where interactive.
- **SQL**: one migration per PR; migrations are idempotent where possible; every table carries `created_at`, `extractor_version` (or analog), and relevant version stamps. Use `pgvector` for embeddings.
- **LLM calls**: temperature 0. Structured output enforced via `response_format` / tool-use schema. Every call logs `{prompt_hash, model, tokens, latency, cost, retrieved_context_ids}`. Never pass raw user documents into a prompt without the structured-extraction step in front.
- **Tests**: every rule has a fixture-driven test. Every extractor has a golden-JSON test. Every measurement has a derivation-trace test that asserts the bbox chain down to source.
- **Never** invent a code section or paraphrase code text. If retrieval returns nothing, return a flagged low-confidence finding or none — not a hallucinated one.
- **Never** collapse provenance fields to save tokens.

## 9. Severity of your own output

When you write code, propose a plan, or answer a design question:

- Prefer the **retrieval-first, deterministic-first** path. If you find yourself designing an LLM step that a rule could do, replace it with a rule.
- Cite the section of this repo (file + anchor) that supports any design decision you make. If nothing supports it, flag the gap and propose an addition to `docs/` first.
- When writing a new rule, include its `rule_id`, its inputs, the tool calls it makes, its threshold logic, its severity, and the fixture test that covers it.
- When writing a new agent, include its single concern, its tool surface, its input/output schemas, the skill it loads, and which tier it belongs to.

## 10. How you work through this repo

You progress through the phases defined in `prompts/`. Each phase has a single entry prompt that supersedes prior instructions until it is shipped. A phase is shipped when its acceptance criteria, spelled out at the bottom of that prompt, evaluate green against the fixture. You do not begin phase N+1 before shipping phase N. You never alter `docs/17-invariants-and-risks.md` without a written design note in `docs/`.

If anything is unclear, re-read this file, the relevant `docs/` section, and the relevant `skills/` SKILL.md. If still unclear, ask — do not guess. Guessing breaks provenance.

---

> Inzohra-ai is a reviewer's assistant, not a substitute for licensed professional judgment. The system is defensible because every output traces down the stack to the pixels it came from. Keep it that way.
