# services/rendering

Node 20 service. Renders comment letters (PDF + DOCX + JSON bundle) from approved findings.

## Layout

```
src/
  smoke.ts            # health-check entry
  cli.ts              # letter render CLI
  letter.ts           # LetterAssembler
  templates/
    bv-santa-rosa.ts  # BV · Santa Rosa template
```

Implementation proceeds in Phase 06. See `prompts/07-phase-06-drafter-letter.md`.
