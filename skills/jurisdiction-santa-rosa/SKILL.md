# Santa Rosa jurisdictional skill

## Scope
Loaded by any reviewer processing a project with `jurisdiction = "santa_rosa"`. Provides the amendments, policies, dialect, and checklists specific to Santa Rosa.

## Amendments summary

The Santa Rosa pack amends the 2022 California codes per the Santa Rosa Municipal Code Title 18. Notable amendments (full pack in `packs/santa-rosa/amendments/`):

- **Fire Zone 3** applies to large portions of the city (post-Tubbs Fire WUI expansion); triggers Chapter 7A requirements on new construction.
- **Defensible space** per Santa Rosa FD requirements on plan callouts.
- **Soft-story retrofit** requirements in certain zones.

## Agency policies

- **Santa Rosa Fire Department memos** (public) on ADU sprinkler requirements, WUI compliance, and access requirements. Each memo linked to the sections it modifies.
- **Santa Rosa Planning** policies on lot coverage, setbacks (building-department-relevant subset).

## Comment dialect

BV writes in a specific voice on Santa Rosa projects:
- Present tense, passive-avoiding where possible.
- Opens with the sheet reference.
- Cites the code section inline, not at the end.
- Uses "Revise" / "Provide" / "Clarify" / "Reference only" as severity keywords.
- Includes a bbox crop with red annotation for visual findings.

### Example style (from 2008 Dennis Ln letter)
> *Sheet A-1.2: The egress window at Bedroom 2 has a net clear opening of 4.2 sqft. CRC §R310.2.1 requires a minimum net clear opening of 5.7 sqft. Revise the window specification to comply.*

Full few-shot library of 30+ examples: `packs/santa-rosa/drafter-examples.md`.

## Letter template

- Font family: **Calibri**.
- Letterhead: BV logo + "Santa Rosa · Building Division" + reviewer contact block.
- Margins: 1.0" top/bottom, 0.875" left/right.
- Page numbers: bottom right.
- Response slot: two-line text box after each comment.

## Submittal checklists

Public Santa Rosa SFR submittal checklist parsed into structured queries in `packs/santa-rosa/checklists/sfr.json`. Additional checklists per occupancy type (R-2.1, R-3, mixed) in the same directory.

## Review round conventions

Italic → round 1; **bold** → round 2; <u>underlined</u> → round 3. Matches the BV convention documented on the 2008 Dennis Ln plan-check letter.

## Fee and timing

- Plan check turnaround: 15 business days, round 1; 10 business days, round 2+.
- Resubmittal fee: per the fee schedule at `packs/santa-rosa/fees.json`.

These fields flow into the letter's general-instructions block and the designer-portal timeline widget.
