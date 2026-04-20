# services/review

Python 3.11 service. See `docs/02-architecture-nine-layers.md` for its role in the stack.

## Layout

```
app/
  __init__.py
  smoke.py          # health-check entry, used by Prompt 00
  extractors/       # (built out in phases 00–02)
  pipelines/        # (built out in phases 00–02)
  codekb/           # (built out in phase 01)
  reviewers/        # (built out in phases 01, 04, 05)
  comparison/       # (built out in phase 07)
```

## Commands

- `uv run services/review/app/smoke.py` — smoke check.
- See `prompts/` for phase-sequenced build instructions.

## Invariants

Consult `CLAUDE.md` and `docs/17-invariants-and-risks.md` before committing any code here. The six non-negotiables apply.
