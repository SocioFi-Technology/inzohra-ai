# Fixture regression

When `pnpm test:fixture` fails in CI and blocks a merge.

## Read the fail

CI output shows which previously-matched BV comments are no longer matched and which new findings are false positives.

## Decide

- **Expected** — you intentionally changed a rule or prompt; the fixture expectations need updating. Open a sibling PR updating `fixtures/2008-dennis-ln/expected-ai-output.json` with a one-line justification per changed expectation.
- **Unexpected** — you broke something. Fix it.

## Never

Do not bypass the gate. Do not merge with a skipped fixture test. The fixture is the floor.

## Adding new fixtures

`fixtures/<address>/` with:
- `plan-set.pdf`
- `title24-report.pdf`
- `narrative.pdf` (if present)
- `fire-review.pdf` (if present)
- `expected-bv-letter.pdf`
- `expected-bv-letter.parsed.json` — parsed comments with sheet refs and citations
- `expected-ai-output.json` — the AI findings we expect to emit

Add the fixture id to `fixtures.yaml` and to the CI phase matrix.
