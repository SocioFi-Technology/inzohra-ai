# § 07 — Agent topology and skills

A multi-agent system organized as **commanders dispatching to specialized workers**. Shape mirrors the Bureau Veritas comment letter structure — one reviewer worker per BV discipline — so every AI-produced finding aligns one-to-one with a human reviewer's mental model.

## Four tiers

### Intake tier
`IntakeCommander` owns arrival and routing of every file.

Workers:
- `DocumentClassifier` — classifies into the seven canonical types.
- `ProjectMatcher` — address/APN/permit number with fuzzy fallback.
- `SubmittalRoundDetector` — identifies round and parent submittal.

No LLM reasoning beyond classification; everything else is deterministic.

### Extraction tier
`ExtractionCommander` orchestrates per-document and per-sheet extraction.

Workers:
- `TitleBlockAgent`
- `SheetIdentifierParser`
- `SheetIndexAgent`
- `FloorPlanGeometryAgent`
- `SitePlanAgent`
- `ScheduleAgent` (specialized per schedule type: doors, windows, fasteners, holdowns)
- `CodeNoteAgent`
- `ElectricalSymbolAgent`
- `PlumbingSymbolAgent`
- `StructuralCalloutAgent`
- `Title24FormAgent`
- `ReviewLetterAgent`
- `NarrativeAgent`
- `QuestionChecklistAgent` (see §08)
- `RevisionCloudAgent`
- `DetailCalloutAgent`

Each is a narrow specialist with a fixed output schema and bbox provenance.

### Review tier
`ReviewCommander` owns substantive compliance review. Ten workers mirror BV disciplines exactly:

| Reviewer | Scope | Primary codes |
|---|---|---|
| `PlanIntegrityReviewer` | Sheet coherence, schedule/plan alignment, overlapping text, title-block consistency | CBC §107 family |
| `ArchitecturalReviewer` | Egress, mixed-occupancy separation, opening protection, code analysis | CBC Ch 3, 4, 5, 7, 10 |
| `AccessibilityReviewer` | Path of travel, turning spaces, reach ranges, signage, accessible kitchens/baths | CBC Ch 11B |
| `StructuralReviewer` | Shear walls, holdowns, fastening, framing, header sizes | CBC Ch 16, 22, 23 |
| `MechanicalReviewer` | Dedicated HVAC per occupancy, bath exhaust, kitchen hood, attic ventilation | CMC, CEnC §150 |
| `ElectricalReviewer` | Panel locations, GFCI/AFCI, egress lighting, §210.70, bedroom receptacles | CEC |
| `PlumbingReviewer` | Fixture counts, water heater, accessible shower, trap arms | CPC |
| `EnergyReviewer` | Envelope, HERS, plan-to-T24 consistency, mixed-occupancy T24 | CEnC (Title 24 Part 6) |
| `FireLifeSafetyReviewer` | Deferred submittals, separation ratings, R-2.1 special requirements | CFC, HSC §13131.x, NFPA 13R/72 |
| `CalGreenReviewer` | Recycling, water efficiency, EV readiness | CalGreen (Title 24 Part 11) |

Every reviewer has the same tool surface: code-RAG tools, measurement tools, entity-query tools, finding-emission tools. Every reviewer runs a two-pass pipeline — deterministic rules first, LLM residue second.

### Output tier
`OutputCommander` handles delivery.

Workers:
- `CommentDrafterAgent` — phrases findings in jurisdictional dialect.
- `LetterAssemblerAgent` — renders the final PDF in the reviewer firm's template.
- `ComparisonAgent` — aligns AI findings to external review letters for the learning loop.
- `RoundRenderer` — applies italic/bold/underline typography keyed to review round.

## Skills vs fine-tuning

Each reviewer discipline gets a curated **skill** file with:

- Scope statement: what the reviewer covers, what it defers.
- Catalogue of most frequent code citations for this jurisdiction.
- Common interpretations and known gotchas (e.g. R-2.1 + >6 occupants → HSC §13131.5 Type V one-hour).
- Worked examples in the jurisdictional dialect.
- Decision tree: emit vs defer to licensed review.

Skills live in version control, diffable across code cycles, and load into context **only for the relevant reviewer**. Total context stays small and auditable — you can trace any finding back to the specific skill that guided it.

## Agent invariants

- No reviewer paraphrases a code section from memory. Every citation is a live retrieval.
- Every agent runs at `temperature=0` with a fixed output schema enforced via structured output.
- Every LLM call logs `{prompt_hash, model, tokens, retrieved_context_ids}`.
- Deterministic rules run before LLM reasoning in every reviewer. LLMs are for the residue.
- Every finding carries the complete evidence chain — entities, measurements, retrieved sections, skill guidance — so the reasoning is always reviewable.
