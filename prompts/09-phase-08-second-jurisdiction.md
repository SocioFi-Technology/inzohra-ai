# Prompt 09 — Phase 08: Second jurisdiction (weeks 15–16)

Prerequisite: Phase 07 shipped.

## Goal

A project from city #2 processes end-to-end with correct amendments applied; pack-authoring documentation for future cities.

## Build

1. **Jurisdictional-pack specification** — finalize the schema in `schemas/jurisdictional-pack.schema.json`. A pack contains:
   - Amendments (per state section, with effective_date windows).
   - Agency policies (memos, interpretations, linked to sections they modify).
   - Submittal checklists.
   - Reviewer dialect: few-shot comment-phrasing examples.
   - Comment-letter template overrides (font, margins, letterhead image, signature block).
   - Fee and timing conventions.
2. **Pack-authoring tooling** (`apps/web/src/app/admin/packs/`):
   - Upload a pack manifest (YAML or directory tarball).
   - Validate against the schema.
   - Compare against the state base + any existing pack; surface diffs.
   - Dry-run amendment resolution on a sample project.
3. **Santa Rosa pack** — complete to ~100 hours of work:
   - All Santa Rosa amendments to the 2022 California codes.
   - Fire Department memos (public) ingested as agency policies.
   - 30+ few-shot BV comment examples covering all disciplines.
   - Submittal checklists.
   - Letter template.
4. **Second-city pack** — pick one of Oakland, San Francisco, or Sonoma County (recommend Oakland for diversity vs Santa Rosa). Target 60 hours.
5. **Jurisdiction resolver** (`services/review/app/codekb/resolver.py`):
   - Input: `(code, section, jurisdiction, effective_date)`.
   - Walk precedence chain: base state section → jurisdiction amendments → agency policies.
   - Return resolved applicable text, unamended text, and the full precedence chain.
6. **Per-jurisdiction evaluation scoping** — the learning loop now reports metrics per-jurisdiction. A rule that works in Santa Rosa but fails in Oakland should be visible as such.
7. **Pack-authoring documentation** (`docs/authoring/new-jurisdiction.md`):
   - Step-by-step: sourcing the municipal code; identifying amendments; cataloguing agency memos; collecting sample review letters; validating the pack; promoting from staging to prod.
   - Target: a subject-matter expert can author a new pack in under 30 hours by city 5.

## Acceptance criteria

- [ ] Santa Rosa pack in production; all 58 BV fixture comments still matched.
- [ ] Second-city pack loaded; a project from that city processes end-to-end with at least one amendment-specific finding.
- [ ] Jurisdiction resolver honors precedence chain; verified by tests.
- [ ] Metrics dashboard scopes per-jurisdiction.
- [ ] `docs/authoring/new-jurisdiction.md` reviewed by at least one senior engineer and one subject-matter expert.
- [ ] `pnpm test:fixture --phase 08` passes (now includes a second-city fixture).

Commit on `phase/08-second-jurisdiction`, PR, report `PHASE 08: SHIPPED`.
