# § 12 — Frontend: reviewer UI and designer portal

Two frontends, one codebase. They share design language, auth, component library, and data layer; they diverge in information architecture because their users do different jobs.

## Reviewer workspace

A three-pane workspace optimized for the one thing a reviewer does all day: triage findings, approve or edit drafts, send a letter.

### Left pane — Project navigator

- Top segment: documents by type (plan set, Title 24, fire review, narrative, letters from prior rounds).
- Bottom segment: plan set expanded into sheets grouped by discipline letter (G/A/S/M/E/P/T/F).
- Each sheet: thumbnail, sheet identifier, title, badge with open findings count.

### Center pane — Sheet viewer

The PDF sheet, pan-and-zoomable, with two overlays:
- **Extracted-entity overlay** — rooms, walls, doors, windows, dimensions as faint highlights that light up on hover.
- **Findings overlay** — bbox crops for every finding on this sheet, tagged with discipline color and finding number.

Clicking any finding badge scrolls the right pane to that finding; clicking any entity shows its extracted payload.

A **measurement tool** in the top toolbar lets a reviewer tap any two points to get a live measurement using calibrated scale. Results appear inline with confidence, savable as a manual override.

### Right pane — Findings panel

List of findings for the active sheet (or all findings when "All sheets" is selected). Each finding tile:

- Discipline badge + finding number.
- Severity chip (Revise / Provide / Clarify / Reference).
- Sheet reference chip (clickable to jump the viewer).
- Draft comment text, editable inline on click.
- Code citation chips — click to open retrieved section in a drawer with frozen text, amendment chain, source link.
- Bbox crop with red-annotation markup, editable by the reviewer.
- Confidence indicator and `requires_licensed_review` flag if applicable.
- Evidence chain expander — click to see every measurement, every entity, every retrieved section that supports the finding.
- Actions: Approve, Edit, Merge, Split, Reject, Add manual comment.

Batch actions at the top: "Approve all Architectural," "Reject all below 0.7 confidence," "Export draft letter."

### Bottom pane — Letter preview

Live-rendering preview of the draft letter, updating as findings are approved or edited. Round selector in top-right lets the reviewer flip between round views.

## Designer portal

Different workspace for QC-agent users. Same project data; different workflow.

### Upload flow

Designers upload plans and (separately) their question checklist. Checklist can be PDF, DOCX, pasted list, or selected from a library of jurisdictional checklists. The system parses, confirms what it found, launches the answer pipeline.

### Three answer views

1. **Question-by-question report** — each question with status (green/amber/red), evidence, suggested remediation on failure.
2. **Plan-set annotation overlay** — same sheet viewer, with question tags floating on relevant regions.
3. **Remediation queue** — focused to-do list for the designer.

## Shared design principles

- **Dense, engineering-grade display** — no wasted space, no decorative margins.
- **Keyboard-first navigation** — every action has a shortcut; power users never touch the mouse.
- **Bbox-first provenance** — every finding, measurement, and citation is anchored to a visible region. If a reviewer can't see where it came from, it's not in the UI.
- **Progressive disclosure** — finding shows summary first; evidence chain, retrieved text, raw entities are all one click away.
- **Predictable latency** — every action has a clear state (loading / ready / error). No spinners without progress. No stale data without staleness indicators.

## Tech choices

- **Next.js 14** with React Server Components for data-heavy views; client components for the interactive sheet viewer.
- **PDF.js** with a custom overlay layer for bboxes and annotations.
- **Tailwind** for styling with a small custom token set.
- **TanStack Query** for server state. **Zustand** for local UI state.
- **NextAuth** with OAuth SSO for reviewer-firm integrations.
- Real-time updates via WebSocket layer for collaborative review on a single project.
