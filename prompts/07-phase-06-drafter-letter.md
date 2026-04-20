# Prompt 07 — Phase 06: Drafter & letter assembler (week 13)

Prerequisite: Phase 05 shipped.

## Goal

Reviewer approves in UI, PDF rolls out, letter indistinguishable from BV-authored at a glance, ready to send.

## Build

1. **CommentDrafterAgent** (`services/review/app/drafter/`).
   - Input: an approved finding + its evidence + its citations + the jurisdictional skill's few-shot examples.
   - Output: a polished comment in the BV dialect with sheet reference, citation formatting, and response slot.
   - Temperature 0. Claude Sonnet.
   - Few-shot library loaded from `skills/jurisdiction-santa-rosa/drafter-examples.md`. Each example pairs a canonical finding with the BV-authored comment on a real project.
2. **Severity picker.** Each drafted comment re-checks its severity against the rule-emitted severity and the finding's reasoning chain. Reviewer can override in UI.
3. **LetterAssemblerAgent** (`services/rendering/src/letter.ts`).
   - Group findings by discipline in BV's canonical order: Architectural, Accessibility, Energy, Electrical, Mechanical, Plumbing, Structural, Fire, CalGreen.
   - Renumber letter-wide (1-based, incrementing across disciplines).
   - Insert letterhead, project block, general instructions, signature block from the Santa Rosa pack.
   - Place bbox crops inline for findings that carry them (BV comments 8 and 9 on 2008 Dennis Ln are the canonical pattern).
4. **PDF template** (`services/rendering/src/templates/bv-santa-rosa.ts`).
   - Calibri typography, BV header/footer, page numbering, correct margins.
   - Use `pdfkit` + `fontkit` with the Calibri font family bundled.
5. **DOCX template** parallel to the PDF (using `docx` on npm).
6. **RoundRenderer** — apply italic/bold/underline typography based on the round in which each comment was first raised. First round: all italic. Second round: round-1-unresolved bold, new italic. Third round: round-1-unresolved underlined, round-2-unresolved bold, new italic.
7. **RevisionCloudAgent** — on a round-2 submittal, detect revision clouds (red ellipsoidal polylines) and associate them with round-1 comments whose `sheet_reference` falls inside the cloud. Emits a `round_alignment` record.
8. **JSON bundle export** — every finding, every citation, every piece of evidence in a machine-readable bundle for permit-tracking-system integration.

## Acceptance criteria

- [ ] Running `pnpm letter:render --project <id>` produces a PDF, a DOCX, and a JSON bundle in `inzohra-output`.
- [ ] Side-by-side visual comparison of the generated PDF vs the BV fixture letter: indistinguishable at a glance (typography, structure, numbering, crops with red annotation).
- [ ] Round-2 fixture (synthetic resubmittal) correctly applies bold typography to unresolved round-1 comments.
- [ ] JSON bundle validates against `schemas/letter-bundle.schema.json`.
- [ ] `pnpm test:fixture --phase 06` passes.

Commit on `phase/06-drafter-letter`, PR, report `PHASE 06: SHIPPED`.
