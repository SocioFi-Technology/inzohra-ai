# § 01 — Mission and scope

Inzohra-ai is an automated reviewer and commenter agent for building-permit plan review. It ingests a submittal — architectural and structural drawings, Title 24 energy reports, fire-review letters, code-analysis narratives, question checklists, and any supporting documents — and produces a jurisdictional-grade comment letter in the style of the reviewing authority.

**Every finding is tied to:**
- a specific sheet,
- a specific bounding region on that sheet,
- a specific measured or extracted value, and
- a specific section of the governing code retrieved live from a structured knowledge base.

It is **not** a code-memorization model. It is a code-grounded reasoning system. The model paraphrases nothing from its parameters; it retrieves, cites, and defers to the human reviewer who owns the final letter.

## Primary users

- **Plan-check firms and jurisdictional reviewers** — the reviewer workspace (three-pane triage UI) is the default surface.
- **Design firms submitting permit applications** — the designer portal and the Question-Checklist agent (§08) are the pre-submittal verification surface.

## Scope boundaries

Inzohra-ai is **not**:

- **a structural engineering tool.** It does not perform shear-wall design, seismic analysis, or load calculation. It reads what the structural engineer drew and flags cases where drawings disagree with schedules, schedules disagree with calculations, or callouts reference details that don't exist. It assumes the stamped engineer's calculations are correct and verifies only the documentation.
- **an accessibility consultant.** It applies CBC Chapter 11B rules mechanically against measured and extracted geometry; it does not make the substantive determinations that a CASp inspector would make in the field.
- **a substitute for licensed professional judgment.** Anything on the legal critical path — occupant load, shear-wall adequacy, fire-rated assembly adequacy — is flagged `requires_licensed_review` regardless of system confidence.

## Initial scope

- 2022 California code cycle.
- Residential and mixed-occupancy projects.
- Santa Rosa first. Every new city ships as a data release (a jurisdictional pack), not a software release.

## Primary fixture

`2008 Dennis Ln · Santa Rosa · CA · Permit B25-2734`. The expected Bureau Veritas comment letter has 58 comments. Inzohra-ai is "done" for this fixture when its output is indistinguishable from a BV-authored letter at a glance.
