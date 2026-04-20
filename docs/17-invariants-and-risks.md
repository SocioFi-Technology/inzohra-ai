# § 17 — Invariants, risks, open questions

## Architectural invariants (NON-NEGOTIABLE)

Six rules that must not break. If any phase's work appears to require violating one, **the design is wrong, not the rule.**

1. **Provenance is sacred.** Every artefact carries `{document_id, page, bbox, extractor_version, rule_version, prompt_hash}`. No exceptions.
2. **Immutability on commit.** Append-only storage; re-runs produce new rows, never overwrites.
3. **No code paraphrase from model weights.** Every citation is a live retrieval. The frozen retrieved text travels with the finding.
4. **Deterministic rules before LLMs.** Every reviewer runs rules first, LLM only for the residue. Temperature is always `0`. Schemas are always structured.
5. **Jurisdiction + effective_date on every retrieval.** Codes are versioned at the section level. A project permitted on 2025-03-15 is reviewed against text in effect on that date, forever.
6. **`requires_licensed_review` on the legal critical path.** Occupant load, shear-wall adequacy, fire-rated assembly adequacy, egress capacity decisions at non-trivial occupant loads are always flagged for licensed sign-off, regardless of AI confidence.

## Top risks

- **Measurement accuracy on raster/scanned PDFs.** Mitigated by PDF-quality classifier, systematic confidence penalty on raster sources, and reviewer-calibration anchors for low-quality inputs.
- **Code-RAG precision under amendment layering.** Mitigated by canonical-ID resolution, explicit precedence chain, and retrieval-chain logging for every citation.
- **LLM hallucination of code text.** Structurally prevented: model never paraphrases; citations are frozen retrievals; reviewer sees both the frozen text and the live KB link.
- **Jurisdictional drift.** Pack versioning; closed projects not retroactively re-reviewed; active projects flagged on pack update.
- **Reviewer fatigue from false positives.** Per-rule precision tracking; thresholds tuned in the learning loop; confidence-based auto-surface order.
- **Legal liability for a bad finding.** Addressed by `requires_licensed_review`, the signed-by-licensed-reviewer model, contractual allocation of responsibility, and E&O insurance.

## Open questions

- Pack-authoring tooling: what's the right UX for a subject-matter expert adding amendments without needing engineering?
- Inter-rater reliability: when two BV reviewers would write different comments for the same issue, which do we target?
- Cross-round continuity across staff changes: when a different reviewer handles round 2, what context gets surfaced from round 1?
- Error-and-omissions insurance structure as AI-share of decisions grows.

## Things we explicitly will NOT do

- We will not fine-tune the model on code text.
- We will not let Inzohra-ai sign a letter.
- We will not auto-approve a `requires_licensed_review` finding.
- We will not let a finding emit without a retrieval chain.
- We will not mutate a committed artefact.

## Phase 07 regression gate

A GitHub Actions workflow (`.github/workflows/ci.yml`) runs `pnpm test:fixture --phase 07` on every push to `main` and every pull request. The workflow:

1. Starts a fresh PostgreSQL 15 instance.
2. Applies all migrations in `db/migrations/` order.
3. Runs `fixture-regression.ts --phase 07` which checks:
   - All Phase 07 DB tables and views exist.
   - Key Phase 07 source files are present.
4. Blocks merge if any check fails.

A deliberately introduced regression (e.g. dropping the `alignment_records` table) will cause the check `[b]` to fail with exit code 1, blocking the PR.

To verify CI blocks a regression locally:
```bash
# Simulate a regression
psql $DATABASE_URL -c "DROP TABLE IF EXISTS alignment_records CASCADE;"
pnpm test:fixture --phase 07   # Should exit 1
```

Shadow-deploy promotions (changing `prompt_versions.is_default`) also trip a fixture regression because the regression test snapshots P/R metrics and asserts they do not drop below previous thresholds (tracked in `apps/web/scripts/fixture-regression.ts`).
