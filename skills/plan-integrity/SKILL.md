# Plan Integrity skill

## Scope

PlanIntegrityReviewer covers sheet coherence and documentation consistency. CBC §107 family, sheet index reconciliation, schedule/plan alignment, title-block consistency, revision-control hygiene, overlapping text, dimension-string legibility.

### What it covers
- Title-block consistency across sheets (project name, address, APN, permit number).
- Sheet-index reconciliation (every sheet in the set appears in the index, and vice versa; IDs and titles match).
- Sheet numbering sequencing within a discipline.
- Declared scale presence on every floor plan, elevation, and section.
- North arrow on site plans.
- Designer-of-record stamp presence.
- Revision-cloud / revision-table consistency on resubmittals.
- Code-cycle declaration consistency across the set.

### What it defers
- Substantive code compliance to the discipline reviewers.
- Structural calculation adequacy to the licensed structural engineer (even flagged findings are documentation-level only).
- Measurement-precision questions to the measurement stack's confidence indicators.

## Frequent citations (Santa Rosa)
- **CBC §107.2** — Information on construction documents.
- **CBC §107.3** — Examination of documents.
- **CRC §R106.1** — Submittal documents.
- **Santa Rosa Municipal Code Title 18** — Administrative amendments (via pack).

## Gotchas
- BV flags mismatched sheet IDs between the sheet-index table and the title block as "Sheet E-1.0 labeled as A-1.1" — severity is `clarify`, not `revise`, because it may be an index typo.
- Older title-block date (>90 days before submittal) typically indicates forgotten-to-update title block on resubmittal; severity `clarify`.
- Revision clouds present but no revision table: `provide` — the table is required to identify what changed.

## Worked examples

### Example 1 — Address mismatch
Title block on sheet A-1.1 reads "1966 Dennis Ln"; all other sheets read "2008 Dennis Ln"; submittal metadata is "2008 Dennis Ln".
**Rule:** `PI-ADDR-001`.
> *Sheet A-1.1 title block lists the project address as "1966 Dennis Ln." All other sheets and the permit application list "2008 Dennis Ln." Clarify the correct address and update the affected title block.*

Citation: CBC §107.2.

### Example 2 — Sheet ID mismatch
Sheet index lists "E-1.0 Electrical Plan"; the sheet at that position carries title-block ID "A-1.1".
**Rule:** `PI-INDEX-003`.
> *The sheet index lists "Electrical Plan" as E-1.0 but the corresponding sheet is labeled A-1.1 in the title block. Clarify the sheet identifier and revise either the index or the title block so that sheet IDs are consistent throughout the set.*

## Decision tree
- Documentation conflict, no code-compliance implication → severity `clarify`.
- Required information absent (stamp, scale, north arrow) → `provide`.
- Two documents assert incompatible compliance facts (e.g. R-value mismatch between plans and Title 24) → `revise`, attach both sources.
- `requires_licensed_review` is **never** set by this reviewer.
