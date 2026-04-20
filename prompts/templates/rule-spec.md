# Rule spec template

Copy this template when adding a new rule. See `docs/10-review-engine.md` for conventions.

---

## Rule ID

`<DISC>-<GROUP>-<NNN>` (e.g. `ARCH-EGRESS-010`)

## Version

`1.0.0`

## Discipline

`architectural | accessibility | structural | mechanical | electrical | plumbing | energy | fire_life_safety | calgreen | plan_integrity`

## What it checks

Short prose.

## Inputs

List of entity types and measurement types consumed.

## Tools used

List of `measure_*`, `query_entity`, `lookup_section`, etc.

## Code citations

The sections this rule will cite (by canonical_id).

## Severity default

`revise | provide | clarify | reference_only`

## `requires_licensed_review`

`true` only if the rule ID is in `packages/shared/src/critical-path.ts`.

## Positive fixture

Which fixture triggers this rule and with what expected finding text.

## Negative fixture

A fixture where this rule should NOT fire.

## Implementation

Path to `services/review/app/reviewers/<discipline>/<rule_id>.py`.
