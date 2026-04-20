# House rules

These are the operational rules Claude Code follows when working in this repo. They are in addition to the invariants in `docs/17-invariants-and-risks.md` and the master context in `CLAUDE.md`.

## On every session start

1. Read `CLAUDE.md` in full.
2. Read `docs/17-invariants-and-risks.md` (one page; read it anyway).
3. Read `.claude/skills-registry.md` to know which skills exist.
4. Open the last-shipped phase's prompt and check off its acceptance criteria against the repo state before starting any new phase.

## On every non-trivial commit

- Run `pnpm lint && pnpm typecheck` for TS code and `ruff check . && mypy --strict` for Python.
- Run the fixture-regression test: `pnpm test:fixture` (wraps a docker-compose up + a full pipeline run on `fixtures/2008-dennis-ln/`).
- If the fixture output regresses on any BV comment that previously passed, block the commit and investigate.

## On every rule you add

Each rule is a typed function in `services/review/app/rules/<discipline>/<rule_id>.py`. It must:

1. Have a unique `rule_id` (e.g. `ARCH-EGRESS-010`) and a semantic version (`1.0.0`).
2. Declare its input entity types and the tool calls it makes.
3. Document its governing code section(s) by canonical citation.
4. Emit findings through the shared `emit_finding` helper which enforces the schema.
5. Ship with a fixture test in `services/review/tests/rules/test_<rule_id>.py` with at least one positive and one negative example.

## On every extractor you add

Each extractor is a Python class in `services/ingestion/app/extractors/<name>.py` with:

1. A `Pydantic` output schema in `packages/shared/schemas/extraction/<name>.py`.
2. A `version` class attribute (`"1.0.0"`); bump on every schema or prompt change.
3. A dual-track path: native-text (PyMuPDF) and vision (rasterized crop via Claude Sonnet).
4. Bbox provenance on every emitted field. Never emit a field without a bbox unless it is a derived summary of fields that each carry their own bbox.
5. A golden-JSON test under `services/ingestion/tests/extractors/goldens/`.

## On every LLM call

Wrap in the `llm_call` helper from `packages/shared/src/llm.py`. The helper:

- Enforces `temperature=0` and structured output.
- Logs `{prompt_hash, model, tokens_in, tokens_out, latency_ms, cost_usd, retrieved_context_ids}` to the `llm_call_log` table.
- Caches by prompt hash when inputs are pure (extraction, drafting).
- Routes to Opus when a Sonnet call comes back with confidence < `OPUS_ESCALATION_THRESHOLD` (default 0.70, per-reviewer override).

## On every retrieval

Every `lookup_section` / `search_code` call resolves against `(jurisdiction, effective_date)`. The returned result's `frozen_text` is what gets attached to the finding. Never let retrieval return a result without a `retrieval_chain` that lists the state section + amendment records used.

## On the critical path

Findings marked `requires_licensed_review=true` cannot be auto-approved, cannot bulk-approve, and render with a distinct "legal sign-off required" treatment in the UI. The list of rules that set this flag is in `packages/shared/src/critical_path.py` — it is a source of truth. Do not set `requires_licensed_review` outside that file.

## When you're stuck

- Re-read the invariants (`docs/17-invariants-and-risks.md`).
- Read the relevant `docs/` section.
- Read the relevant `skills/<discipline>/SKILL.md`.
- Grep for an existing analogous rule / extractor / agent; mimic its shape.
- Ask. Do not guess. Guessing breaks provenance.
