# § 11 — Output and comment-letter generation

The product's primary deliverable is the comment letter. Everything upstream exists to make one thing: a PDF (and its DOCX equivalent) a licensed reviewer can approve and send, in the style and structure the receiving jurisdiction expects.

## Letter anatomy (Santa Rosa / BV style)

In order:

1. **Letterhead** — firm logo, city name, review date, application number, review round, reviewer contact info.
2. **Project block** — description, address, permit number, occupancy class, construction type, sprinklered, stories, floor area, fire hazard severity zone, flood zone.
3. **General instructions** — jurisdictional boilerplate about code cycle, response requirements, resubmittal conventions (cloud and delta).
4. **Response slot for the designer** — name and phone of person preparing responses.
5. **Submittal instructions** — where to send the resubmittal.
6. **Reviewer signature block.**
7. **Numbered comments** — grouped by discipline (Architectural, Accessibility, Energy, Electrical, Mechanical, Plumbing, Structural), each with:
   - Sheet reference
   - Comment text
   - Code citation
   - Response slot
   - Embedded bbox crop where applicable
8. **Review-round typography** — italic for first-round, **bold** for second-round (unresolved from first), <u>underlined</u> for third-round (still unresolved). On first review, all comments are italic.
9. **End-of-comments marker.**

## Rendering pipeline

`LetterAssemblerAgent` takes approved findings and renders them into the jurisdiction's template:

1. **Group** findings by discipline in BV's canonical order.
2. **Renumber** within the combined document — findings come discipline-numbered; assembler assigns final letter-wide numbering.
3. **For each finding:** render comment text in the jurisdictional dialect, insert sheet reference, format code citation, place bbox crops inline (BV comments 8 and 9 on 2008 Dennis Ln are the canonical pattern — crops with red annotation).
4. **Apply round-specific typography** — italic/bold/underlined based on the round in which each comment was first raised.
5. **Insert** letterhead, project block, general instructions, and signature block from the jurisdictional pack.
6. **Render to PDF** with correct font (Calibri for BV, Arial for other firms per pack), page margins, header/footer template.
7. **Parallel DOCX** export so the reviewer can tweak in Word if needed.
8. **JSON bundle** carrying every finding, citation, and piece of evidence for permit-tracking-system integration.

## Round management

When a resubmittal arrives, the round manager does cross-round bookkeeping:
- Previous-round comment's underlying condition now resolved → close.
- Partially resolved → re-raise with round-two status.
- Unaddressed → re-raise with round-two status.
- New findings on the resubmittal → new round-two comments.

Typography on the second-round letter:
- Round-one unresolved → **bold**.
- New round-two → *italic*.

Round three: round-one-unresolved → <u>underlined</u>, round-two-unresolved → **bold**, new round-three → *italic*. This matches the BV convention on the 2008 Dennis Ln plan-check letter.

## Designer-facing output (Question-Checklist agent)

When the user is a design firm using the QC agent, output differs:

- **Checklist report PDF** — each question answered, evidence linked.
- **Plan-set annotation overlay** — exportable as a marked-up PDF.
- **Remediation queue** — short document listing items needing attention before submittal, ranked by severity.

Both pipelines (reviewer letter, designer report) share the same underlying findings and citations. What differs is rendering template and framing language: *"the plans fail to show X"* vs *"we recommend adding X before submittal."*

## Export formats

Every output is available in three formats:
- **PDF** — for sending and printing.
- **DOCX** — for editing.
- **JSON** — for integration with permit-tracking systems (Accela, EnerGov, Tyler EnerGov).
