# Prompt 00 — Bootstrap

Paste this prompt into Claude Code the first time you open the repo. It brings the development environment up from scratch.

---

You are starting work on **Inzohra-ai**. Before any feature work, get the development environment to a known-good state.

## Context to read first (in this order)

1. `CLAUDE.md` — the master system prompt. Read every section.
2. `.claude/house-rules.md` — operational rules.
3. `.claude/skills-registry.md` — inventory of skills.
4. `docs/17-invariants-and-risks.md` — the six non-negotiable invariants.
5. `docs/16-development-plan.md` — the phase sequence you will be walking.

## Task: bring the dev stack green

1. **Verify the toolchain.** Check that Node 20, Python 3.11, Docker, pnpm, and `uv` are present. Install `uv` if missing (`curl -LsSf https://astral.sh/uv/install.sh | sh`). Install pnpm if missing (`npm i -g pnpm`).
2. **Install workspace dependencies.**
   - `pnpm install` at the repo root to wire the TS workspace.
   - `uv sync` at the repo root to wire the Python workspace.
3. **Boot the dev stack.**
   - `docker compose up -d postgres redis minio` from `ops/`.
   - Wait for health checks: `docker compose ps` should show `healthy` on all three.
4. **Apply migrations.**
   - `pnpm db:migrate` (this runs the shell script in `db/scripts/migrate.sh`).
   - Verify tables exist: `pnpm db:shell` then `\dt` should list `projects`, `submittals`, `documents`, `sheets`, `entities`, `measurements`, `findings`, `llm_call_log`, `retrieval_log`, `code_sections`, `amendments`, etc.
5. **Seed the code KB with a minimal slice.** Run `pnpm kb:seed -- --jurisdiction santa_rosa --slice cbc-107`. This loads just enough to make `lookup_section` return a real row for Phase 01's Plan Integrity rules.
6. **Smoke-test every service.**
   - `pnpm dev` should boot the Next.js app at `http://localhost:3000`. Confirm the landing page renders.
   - `uv run services/ingestion/app/smoke.py` should print `INGESTION SMOKE: OK`.
   - `uv run services/review/app/smoke.py` should print `REVIEW SMOKE: OK`.
   - `uv run services/measurement/app/smoke.py` should print `MEASUREMENT SMOKE: OK`.
   - `pnpm --filter @inzohra/rendering smoke` should print `RENDERING SMOKE: OK`.
7. **Fixture sanity check.** Verify `fixtures/2008-dennis-ln/` contains the plan-set PDF, the Title 24 report, the narrative, the fire review, and the expected BV letter. If any are missing, stop and report.
8. **Run the empty fixture regression.** `pnpm test:fixture --phase 00` should report all Phase 00 acceptance criteria as unchecked (no failures, no passes — just a clean baseline).

## Acceptance criteria for Phase 00 bootstrap

- [ ] All four smoke tests print OK.
- [ ] All containers in `docker compose ps` report `healthy`.
- [ ] Migrations applied cleanly; `\dt` shows the full baseline schema.
- [ ] `pnpm dev` serves the Next.js shell at `:3000`.
- [ ] `fixtures/2008-dennis-ln/` present and complete.
- [ ] `pnpm test:fixture --phase 00` exits 0.

When all six are green, report `BOOTSTRAP: READY` and stop. Do not begin Phase 00 feature work in this prompt — that starts with `prompts/01-phase-00-foundations.md`.

If anything fails, do not hand-wave. Report exactly what failed, with the command run and its output. Re-read `CLAUDE.md` if you find yourself tempted to take a shortcut.
