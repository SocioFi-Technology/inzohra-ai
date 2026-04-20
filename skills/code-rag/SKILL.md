# Code-RAG skill (cross-cutting)

## Scope
Loaded by the code-RAG retrieval layer. Governs retrieval ranking, amendment precedence, citation canonicalization.

## Retrieval precedence
Every retrieval resolves against `(jurisdiction, effective_date)`:

1. **Canonical ID resolution** — `resolve_citation("Table 716.1(2)")` → stable canonical_id.
2. **State section lookup** at the effective date.
3. **Jurisdiction amendments** applied in declared order; last-amendment-wins on collision.
4. **Agency policies** attached as supplementary context (not replacing text; advisory).
5. Return `applicable_text`, `unamended_text`, `amendments[]`, `agency_policies[]`, `cross_refs[]`, `tables[]`, `figures[]`, `retrieval_chain[]`.

## Ranking
Vector similarity (cosine) + exact-match boost on citation strings + recency boost within-cycle. Top match returned with drill-down candidates (related sections the agent can chase).

## Canonicalization
- `§1017.2` → `CBC-1017.2` (inferred from discipline context if present).
- `Table 508.4` → `CBC-TBL-508.4`.
- `§11B-404.2.3` → `CBC-11B-404.2.3`.
- `R310.2.1` → `CRC-R310.2.1`.
- `§150.0(f)` → `CEnC-150.0-f` (subsections as lowercase suffixes).

Unresolvable citations return `null` with a log entry; never fall back to model memory.

## Gotchas
- Amendments with date windows — some amendments are only in effect for a subset of a code cycle.
- Cross-references across codes (e.g. CBC §11B referencing §1020) — resolve both targets and attach each.
- Tables and figures stored as rendered images + parsed rows; retrieval returns both.

## Invariants
- Never return a section without its `retrieval_chain`.
- Never return paraphrased text; always the stored, frozen excerpts.
- Embeddings are computed over the **unamended** text; amendments are applied after retrieval so that amendment churn doesn't invalidate the vector index.
