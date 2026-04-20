# § 13 — Learning loop and evaluation harness

Inzohra-ai gets measurably better with every project it sees. The loop doesn't retrain the model — it tunes rules, improves retrievals, and augments skills.

## The loop

1. A project flows through the system, producing AI findings.
2. A reviewer approves, edits, merges, splits, or rejects each finding; every action is logged in `reviewer_actions`.
3. The final letter is sent. If this is a reviewer-firm user, the final letter replaces the AI draft as ground truth.
4. When the authority's official review letter arrives (or is already on hand, for reference projects), `ReviewLetterAgent` parses it into structured comments (`external_review_comments`).
5. `ComparisonAgent` aligns AI findings to authority's comments. Each alignment lands in one of four buckets:
   - **Matched** — AI and authority flagged the same issue.
   - **Missed** — authority flagged, AI didn't.
   - **False-positive** — AI flagged, authority didn't.
   - **Partial** — related but not same scope.
6. Per-rule and per-discipline **precision, recall, F1** land on the metrics dashboard.
7. **Misses** enter a triage queue. An engineer (or senior reviewer) decides: add a new deterministic rule, tune an LLM prompt, extend a skill, or expand the code KB.
8. **False positives** enter their own triage queue. Fix is usually tightening a rule threshold or adding an exception.
9. **Reviewer edits** on approved findings become few-shot examples for the comment drafter's jurisdictional dialect.
10. **Measurement overrides** train the measurement stack — persistent overrides on a specific measurement type for a specific PDF-quality class become a training signal for the next geometry extractor version.

## Metrics dashboard

Per-rule:
- Precision (approved findings / total emitted).
- Recall (matched findings / authority comments that rule should have caught).
- F1.
- Mean edit distance between AI draft and approved text.
- Mean time-to-approve.

Per-discipline:
- Aggregate precision/recall.
- Distribution of severity on approved findings.
- Count and ratio of `requires_licensed_review` flags.
- Turnaround time end-to-end.

Per-jurisdiction:
- All of the above, scoped.
- Pack version.
- Amendment coverage.

## Evaluation harness

Every commit runs:
1. Unit tests for rules (positive + negative fixtures).
2. Golden-JSON tests for extractors.
3. Derivation-trace tests for measurements.
4. The **fixture regression** — full pipeline on `fixtures/2008-dennis-ln/` compared against the expected BV letter. Any drop in matched count on previously-passing BV comments blocks the commit.

## Prompt and RAG hot-swap

LLM prompts and RAG retrievers are versioned. A new prompt or retriever can be shadow-deployed on top of the existing one: both run, outputs are compared, differences surface in a dashboard. When the new version wins on fixture metrics, it's promoted.

## Triage queues

- **Misses queue** — authority comments with no AI counterpart. Each entry has the parsed external comment and a suggested rule template.
- **False-positives queue** — AI findings the authority did not raise. Each entry has the AI finding with its evidence and a prompt to decide: threshold-tighten, exception-add, or rule-deprecate.
- **Edits queue** — approved findings where the reviewer made substantial text changes. Source of few-shot examples for the drafter.
- **Overrides queue** — measurement overrides, grouped by measurement type and PDF-quality class.
