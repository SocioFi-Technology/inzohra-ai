# Jurisdictional pack promotion

Moving a pack from development → staging → production.

## Pre-flight (dev)

1. Pack validates against `schemas/jurisdictional-pack.schema.json`.
2. All amendments link to existing `code_sections.canonical_id`.
3. All agency policies have source URLs (public record).
4. Drafter examples are ≥ 20, spanning disciplines.
5. Letter template renders cleanly on a sample finding bundle.

## Staging

1. Load the pack into staging.
2. Run `pnpm test:fixture --jurisdiction <name>` — passes.
3. Process at least one real project from that jurisdiction end-to-end.
4. A subject-matter expert reviews the output and signs off in writing.

## Production

1. `pack_id` + version bumped.
2. Migration script promotes the pack row to `is_default=true`.
3. Old version marked `superseded_by`.
4. Active projects on the old pack are **not** re-reviewed automatically; they get a banner inviting re-review.
5. Post-promotion: monitor metrics dashboard for drops in precision or recall over 72 hours.

## Rollback

`superseded_by` reverted, `is_default` flipped back. Active projects unaffected.
