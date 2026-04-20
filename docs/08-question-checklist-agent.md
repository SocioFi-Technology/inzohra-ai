# § 08 — The Question-Checklist agent

The capability the client specifically asked us to build. It reshapes who the tool serves: until now we've described Inzohra-ai as a reviewer's assistant. The Question-Checklist agent makes it also a **designer's pre-submittal verifier**.

## The current practice being automated

Design firms submitting permit applications commonly work through a checklist before they submit. Questions drawn from jurisdictional submittal lists, internal QA processes, and prior-comment patterns. Typical question:

> *"Does every new bedroom have an egress window with at least 5.7 sqft net clear opening, 24" minimum height, 20" minimum width, and a sill height not exceeding 44"?"*

Until now this is a manual walkthrough. The agent automates it.

## Inputs

- The plan set (same as reviewer workflow).
- Any supporting documents (Title 24, narratives, fire review).
- A **question checklist** — PDF, DOCX, pasted list, or selected from a library of jurisdictional checklists.

## Pipeline

1. `QuestionChecklistAgent` parses the checklist into structured queries. Each query carries:
   - **Target entity class** (e.g. bedroom windows).
   - **Filter predicates** (e.g. new construction, specific rooms).
   - **Measurement(s)** to evaluate.
   - **Governing code section** or an explicit threshold if the user provided one.
2. For each question the agent dispatches to measurement and code-RAG tools exactly as a reviewer would.
3. Each question receives an answer status: **green** (pass), **amber** (partial / confidence low), **red** (fail), or **unknown** (required input missing).
4. Findings produced by "red" answers flow into the standard `findings` table with `review_round=0` and the designer as the audience.

## Three answer views (designer portal)

- **Question-by-question report** — each question with status, evidence chips, suggested remediation on failure.
- **Plan-set annotation overlay** — same sheet viewer as the reviewer workspace, with question tags floating on relevant regions.
- **Remediation queue** — focused to-do list ranked by severity, with copy-paste-ready summary for the designer's internal QA log.

## Language difference

Reviewer workspace:  *"The plans fail to show X."*
Designer portal:     *"We recommend adding X before submittal."*

Same findings infrastructure, different rendering template, different framing. Specifically:

- Severity labels for designers: `attention`, `recommend`, `optional` (vs `revise / provide / clarify / reference_only`).
- Citation chips link to the retrieved section but also to the jurisdiction's submittal checklist if that's where the requirement surfaces in practice.
- `requires_licensed_review` is still set, but surfaces as a notice that a licensed reviewer will need to sign off at submittal — not a blocker.

## Library of checklists

Maintained per-jurisdiction in `skills/jurisdiction-<n>/checklists/`. Each entry is a curated list of parsed queries with:
- The canonical question text (for display).
- The structured query (for the agent).
- A citation back to the jurisdiction's source document (for the footer on the designer's report).

Design firms can upload their own checklists which are parsed and stored per-firm.
