# Prompt 08 — Phase 07: Learning loop (week 14)

Prerequisite: Phase 06 shipped.

## Goal

Metrics visible on every rule; triage queue for adding new rules; regression tests blocking bad deploys.

## Build

1. **ComparisonAgent** (`services/review/app/comparison/`).
   - Input: the project's AI findings + parsed external_review_comments from the authority's letter.
   - Output: alignment records with buckets: `matched`, `missed`, `false_positive`, `partial`.
   - Alignment algorithm: candidate pairs via shared sheet_reference + similar citation + fuzzy text match; cost function minimized via Hungarian assignment.
2. **Per-rule metrics** — a materialized view `rule_metrics` with P/R/F1, sample size, last-evaluated-at per `rule_id`. Refreshed nightly.
3. **Per-discipline metrics** aggregated from rule metrics.
4. **Reviewer-edit-distance tracking** — Levenshtein between `draft_comment_text` and final approved text; aggregated per rule.
5. **Metrics UI** at `/metrics`:
   - Heatmap of rule precision/recall over time.
   - Per-discipline dashboard with trend lines.
   - Click-through from any rule to its fixture tests and its live findings on recent projects.
6. **Triage queues** (already scaffolded in Phase 05; fill out now):
   - `/triage/misses` — authority comments without an AI counterpart. Each entry: parsed comment, suggested rule template (derived from similar matched rules), action: "Add rule" → opens a scaffolded test file + rule stub.
   - `/triage/false-positives` — AI findings the authority didn't raise. Each entry: finding, evidence, action: "Tighten threshold", "Add exception", "Deprecate rule".
   - `/triage/edits` — approved findings with reviewer edit distance above threshold. Source of few-shot examples for the drafter.
   - `/triage/overrides` — measurement overrides grouped by type and PDF-quality class.
7. **Prompt / RAG hot-swap.**
   - Every LLM prompt and every retriever has a version.
   - Shadow-deploy: when a new prompt or retriever is flagged `shadow=true`, both old and new run on incoming work; outputs compared and stored; promote on win.
   - Promotion is a PR that updates the `default_version` column in `prompts` / `retrievers` and trips a fixture regression.
8. **Regression test gating.**
   - `pnpm test:fixture --phase 07` asserts that recall does not drop on any previously-matched BV comment.
   - CI blocks merge to `main` on regression.

## Acceptance criteria

- [ ] `/metrics` renders real precision/recall for every rule.
- [ ] Triage queues populated from the fixture run and at least one real-world project.
- [ ] Shadow-deploy demonstrated end-to-end on a trivial prompt change: old + new both run, comparison visible, promotion lands.
- [ ] CI fails a deliberately introduced regression and blocks merge.
- [ ] `pnpm test:fixture --phase 07` passes.

Commit on `phase/07-learning-loop`, PR, report `PHASE 07: SHIPPED`.
