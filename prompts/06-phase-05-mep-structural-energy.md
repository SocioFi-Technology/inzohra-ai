# Prompt 06 — Phase 05: MEP, Structural, Energy, Fire, CalGreen (weeks 11–12)

Prerequisite: Phase 04 shipped.

## Goal

Full BV-parity draft on the fixture; all 58 comments covered (matched or partial); miss and false-positive queues populated for triage.

## Build

Seven reviewers, each with its skill file and its rule set:

1. **MechanicalReviewer** — 30 rules, CMC + CEnC §150: dedicated HVAC per occupancy, bath exhaust, kitchen hood, attic ventilation, duct insulation, outside-air ventilation.
2. **ElectricalReviewer** — 35 rules, CEC: panel locations, GFCI/AFCI coverage, egress lighting, §210.70 lighting outlets, bedroom receptacle count, service size, grounding, tamper-resistant receptacles.
3. **PlumbingReviewer** — 30 rules, CPC: fixture counts vs occupancy, water heater location and venting, accessible shower geometry, trap arms, backflow prevention, DWV sizing.
4. **StructuralReviewer** — 40 rules, CBC Ch 16/22/23: shear-wall callouts complete, holdowns on schedule, fastener schedule consistent, framing members sized in schedule, header sizes noted, continuous load path documentation.
5. **EnergyReviewer** — 25 rules, Title 24 Part 6: envelope U-factor and R-value consistency with plans, HERS measure declarations, climate-zone correctness, mixed-occupancy T24 path selection.
6. **FireLifeSafetyReviewer** — 25 rules, CFC + HSC §13131.x + NFPA 13R/72: deferred submittals for sprinklers/alarms, R-2.1 Type V one-hour triggers, separation ratings, fire-department access, Fire Department memos attached as agency policies.
7. **CalGreenReviewer** — 30 rules, Title 24 Part 11: recycling provisions, water efficiency (Division 4.3), EV readiness, mandatory vs voluntary measures.

Each reviewer:
- Loads its `skills/<discipline>/SKILL.md`.
- Runs rules first, LLM tail second.
- Emits findings with full provenance.
- Has fixture tests for every rule (positive + negative).

## Cross-cutting work

- **`requires_licensed_review` list** — finalize the authoritative list in `packages/shared/src/critical_path.py`. Every rule that sets the flag must import from this module. Cover: occupant load calcs, shear-wall adequacy, fire-rated assembly adequacy, egress capacity at non-trivial loads.
- **Opus escalation path** — implement the escalation pipeline: Sonnet primary call; if confidence < 0.70 or if the finding is on the critical path, an Opus second pass re-examines with broader context.
- **Miss and false-positive queues** — UI views at `/triage/misses` and `/triage/false-positives`. Each entry has the external comment (for misses) or AI finding (for FPs), its evidence, and action buttons: "Add rule", "Tune threshold", "Add exception", "Promote to skill gotcha".

## Acceptance criteria

- [ ] All 58 BV comments on the fixture are covered: either matched (AI raised the same issue) or flagged in the miss queue with a triage entry.
- [ ] No more than 10 false positives on the fixture.
- [ ] Precision ≥ 0.85 overall, recall ≥ 0.80 overall at this phase's snapshot.
- [ ] Triage UI live and populated.
- [ ] Every reviewer loads its skill at runtime.
- [ ] `pnpm test:fixture --phase 05` passes.

Commit on `phase/05-mep-structural-energy`, PR, report `PHASE 05: SHIPPED`.
