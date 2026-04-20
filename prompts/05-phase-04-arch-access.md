# Prompt 05 — Phase 04: Architectural & Accessibility reviewers (weeks 9–10)

Prerequisite: Phase 03 shipped.

## Goal

Auto-generates BV comments 2, 10–17, 22, 25–38, 40, 42 on the fixture; first real precision/recall numbers vs the BV letter; measurements back every size/distance finding.

## Build

1. **ArchitecturalReviewer** — 60 rules covering:
   - Egress (CBC Ch 10): number of exits, exit separation, travel distance, egress width, common path of travel, dead-end corridors, aisle widths.
   - Occupant load (CBC Ch 10, Table 1004.5): load factor × area per room; cumulative load per exit.
   - Mixed-occupancy separation (CBC Ch 5 / §508): separated vs non-separated, required rated separations.
   - Opening protection (CBC Ch 7): fire-rated assemblies, opening protectives, penetration firestopping.
   - Code analysis consistency with narrative.
   - Stair/ramp geometry (CBC Ch 10).
2. **AccessibilityReviewer** — 80 rules covering:
   - 11B-202 (path of travel): continuous barrier-free route from arrival to area of use.
   - Turning spaces (11B-304): 60" diameter or T-turn.
   - Reach ranges (11B-308).
   - Kitchen accessibility (11B-804): work surface, sink, appliances, clearances.
   - Bath accessibility (11B-603 through 11B-608): clear floor space, grab bars, shower, water closet.
   - Signage (11B-703).
   - Thresholds, door clear widths (11B-404.2.3), door hardware (11B-404.2.7).
3. **LLM reviewer tail** — narrative-check layer on each reviewer. Inputs: relevant structured entities, retrieved code sections, measurement outputs, the discipline skill. Output: reasoning chain + draft finding. Temperature 0, structured output, prompt hash logged. Claude Sonnet primary; Opus escalation when reviewer confidence < 0.70.
4. **Skill loading** — `ArchitecturalReviewer` loads `skills/architectural/SKILL.md` at startup. `AccessibilityReviewer` loads `skills/accessibility/SKILL.md`. Skills are read-only at runtime and surface as the system prompt for the LLM tail.
5. **Code-RAG expansion** — full CBC Ch 10, Ch 11B; CRC R310–R317.
6. **Precision/recall instrumentation.** After every fixture run, `ComparisonAgent` aligns AI findings to the parsed BV letter. Per-rule + per-discipline P/R/F1 lands in a simple metrics table queryable at `/metrics`.

## Acceptance criteria

- [ ] Fixture emits findings matching BV comments 2, 10–17, 22, 25–38, 40, 42 (where these are within Architectural or Accessibility scope).
- [ ] Every size/distance finding has a measurement attached with its confidence and trace.
- [ ] Precision ≥ 0.85 on PlanIntegrity + Architectural + Accessibility combined at this phase's snapshot.
- [ ] Recall ≥ 0.60 on the same scope.
- [ ] Skills load at runtime and surface in the LLM system prompt for their respective reviewers.
- [ ] `pnpm test:fixture --phase 04` passes.

Commit on `phase/04-arch-access`, PR, report `PHASE 04: SHIPPED`.
