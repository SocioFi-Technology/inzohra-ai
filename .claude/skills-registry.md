# Skills registry

Every skill in this project is a `SKILL.md` file under `skills/<name>/`. Skills are loaded into an agent's context **only when the agent that needs them runs** — never all at once. Keep them small and diffable.

## Discipline skills (one per BV reviewer)

| Skill | Loaded by | Governs |
|---|---|---|
| `skills/plan-integrity/SKILL.md` | `PlanIntegrityReviewer` | CBC §107 family, sheet coherence, schedule/plan alignment, title-block consistency |
| `skills/architectural/SKILL.md` | `ArchitecturalReviewer` | CBC Ch 3, 4, 5, 7, 10; egress, mixed-occupancy separation, opening protection |
| `skills/accessibility/SKILL.md` | `AccessibilityReviewer` | CBC Ch 11B; path of travel, turning spaces, reach ranges, signage, kitchen, bath |
| `skills/structural/SKILL.md` | `StructuralReviewer` | CBC Ch 16, 22, 23; shear walls, holdowns, fastening, framing, headers |
| `skills/mechanical/SKILL.md` | `MechanicalReviewer` | CMC; CEnC §150; HVAC, bath exhaust, kitchen hood, attic ventilation |
| `skills/electrical/SKILL.md` | `ElectricalReviewer` | CEC; panels, GFCI/AFCI, egress lighting, §210.70, bedroom receptacles |
| `skills/plumbing/SKILL.md` | `PlumbingReviewer` | CPC; fixture counts, water heater, accessible shower, trap arms |
| `skills/energy/SKILL.md` | `EnergyReviewer` | Title 24 Part 6; envelope, HERS, plan-to-T24 consistency |
| `skills/fire-life-safety/SKILL.md` | `FireLifeSafetyReviewer` | CFC, HSC §13131.x, NFPA 13R/72; deferred submittals, separation ratings |
| `skills/calgreen/SKILL.md` | `CalGreenReviewer` | CalGreen Part 11; recycling, water efficiency, EV readiness |

## Cross-cutting skills

| Skill | Loaded by | Purpose |
|---|---|---|
| `skills/measurement/SKILL.md` | Measurement stack | Scale resolution, calibration protocol, PDF-quality degradation rules |
| `skills/code-rag/SKILL.md` | Code-RAG retrieval layer | Retrieval ranking, amendment precedence, citation canonicalization |
| `skills/extraction/SKILL.md` | Extraction agents | Dual-track extraction (text + vision), bbox provenance rules, confidence scoring |
| `skills/jurisdiction-santa-rosa/SKILL.md` | Any reviewer in Santa Rosa | Santa Rosa amendments, agency policies, BV comment dialect, few-shot examples |

## Skill anatomy

Every `SKILL.md` follows this template:

```markdown
# <Name> skill

## Scope
- What this reviewer covers.
- What it defers to (other reviewers / licensed professional).

## Frequent citations (this jurisdiction)
- <Code §> — one-line summary, expected fixture hits.

## Gotchas
- Non-obvious interpretations, common errors, rule-of-thumb numbers.

## Worked examples
### Example 1 — <short title>
<Symptoms in the extracted data>
<Rule logic / reasoning>
<Draft comment text in the jurisdictional dialect>
<Citation(s)>

## Decision tree: emit vs defer
<If ... then ... else ...>
```

## How agents use skills

```python
from packages.shared.skills import load_skill

skill = load_skill("architectural", jurisdiction="santa_rosa")
# skill.scope, skill.citations, skill.gotchas, skill.examples, skill.decision_tree

# Pass skill.as_system_prompt() into the LLM system prompt for this reviewer.
```

Skills are **read-only at runtime**; they are edited in Git, reviewed in PRs, and versioned with the rule set that relies on them. A skill bump is a rule-set bump.
