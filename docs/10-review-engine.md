# § 10 — Review engine: rules, LLMs, findings

The review engine is where evidence becomes findings. Every discipline reviewer runs a two-pass pipeline over its scope. Pass one is deterministic rules; pass two is LLM reasoning for what rules can't decide. Both passes emit findings with identical schema, identical provenance, identical review treatment in the UI.

## Pass one — deterministic rules

A rule is a small piece of typed code that reads structured entities, calls tools to pull measurements and code text, and decides a compliance question. A rule is identified by its `rule_id` and `rule_version`. Every finding it emits carries both, so a rule can be improved, re-run on prior projects, and its historical findings either revalidated or flagged.

Rules are cheap. They're fast (most run in milliseconds). They're reproducible — given the same inputs, the same rule version always produces the same output. They're defensible — the finding traces through deterministic logic to a specific line of code.

### Target rule counts per discipline

| Discipline | Phase 1 | Phase 5 target |
|---|---|---|
| PlanIntegrityReviewer | 15 | 40 |
| ArchitecturalReviewer | — | 60 |
| AccessibilityReviewer | — | 80 |
| StructuralReviewer | — | 40 |
| MechanicalReviewer | — | 30 |
| ElectricalReviewer | — | 35 |
| PlumbingReviewer | — | 30 |
| EnergyReviewer | — | 25 |
| FireLifeSafetyReviewer | — | 25 |
| CalGreenReviewer | — | 30 |
| **Total** | **15** | **~370** |

Every new external review letter parsed through the learning loop adds candidates for new rules.

## Pass two — LLM reasoning

LLMs handle the residue. Three categories need reasoning a rule can't provide:

- **Narrative checks** — "does the code-analysis narrative on sheet G-0.1 correctly classify this as R-2.1 per HSC §13131.5 given the stated occupant count?"
- **Visual-quality findings** — overlapping text, illegible dimension strings, detail crops that don't match their referenced details. BV comment 24 on 2008 Dennis Ln is exactly this kind.
- **Ambiguous callout resolution** — "sheet A-1.2 references 'detail 8/A-1.5' but no detail 8 appears on A-1.5; what's the intended reference?"

LLM passes receive structured entities, retrieved code sections, measurement tool outputs, and the discipline skill. They produce a reasoning chain and a draft finding. The reasoning chain is logged in full. **Claude Sonnet handles most of this; Claude Opus runs on high-stakes or low-confidence findings in a second pass.**

## Finding schema (canonical)

```json
{
  "finding_id": "uuid",
  "project_id": "uuid", "submittal_id": "uuid", "review_round": 1,
  "discipline": "architectural | accessibility | ...",
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

## Severity model

Four levels following the BV dialect:

- **Revise** — the plans contradict the code and must be changed to comply.
- **Provide** — required information is missing and must be added.
- **Clarify** — ambiguity must be resolved.
- **Reference only** — a note for the designer's awareness, not a required change.

Severity is set by the rule or LLM that emits the finding. Reviewers can adjust in the UI. Final-letter severity distribution is tracked as a quality metric — a distribution heavily skewed toward `revise` may indicate overflagging; heavily toward `reference_only` may indicate underflagging.

## Confidence handling

Every finding carries a combined confidence score. A finding resting on a `0.95` measurement and a `1.0` retrieval has higher confidence than one resting on `0.75` + `1.0`. Below per-discipline thresholds (accessibility `≥ 0.90`, architectural `≥ 0.80` for coarse checks), the finding auto-tags for reviewer attention with a visible confidence indicator.

## `requires_licensed_review` flag

Certain findings are flagged regardless of AI confidence because they sit on the legal critical path:
- Occupant load calculations.
- Shear-wall adequacy.
- Fire-rated assembly adequacy.
- Egress capacity decisions when occupant load is non-trivial.

These still get drafted with full evidence and citations; the UI marks them as needing licensed sign-off before approval. The authoritative list of rules that set this flag lives in `packages/shared/src/critical_path.py`.
