# Inzohra-ai — Scaffolding & Development Package

**DOC-ARCH-002 · REV 0.1 · Code-grounded, multi-agent, retrieval-first plan review.**

This is the full development scaffolding for `inzohra-ai`, an automated reviewer and commenter agent for building-permit plan review. It ingests a permit submittal — architectural/structural drawings, Title 24 reports, fire-review letters, narratives, question checklists — and produces a jurisdictional-grade comment letter in the reviewing authority's style. Every finding is tied to a sheet, a bounding region, a measured or extracted value, and a retrieved section of the governing code.

> **It is not a code-memorization model. It is a code-grounded reasoning system.** The model paraphrases nothing from its parameters; it retrieves, cites, and defers to the human reviewer who owns the final letter.

---

## How to use this package

This scaffolding is designed to be developed **end-to-end by Claude Code**. The `prompts/` folder contains a sequenced set of prompts (Phase 00 → Phase 09 → Finalize) that drive Claude Code through the full build.

### 1. Unzip, cd, and initialize Claude Code

```bash
unzip inzohra-ai-scaffolding.zip
cd inzohra-ai
claude   # start Claude Code in this directory
```

Claude Code will automatically read `CLAUDE.md` (the master system prompt) and the files in `.claude/` (project rules, invariants, skills registry).

### 2. Run the bootstrap prompt

Paste `prompts/00-bootstrap.md` into Claude Code. It will:
- Verify the toolchain (Node 20, Python 3.11, Docker, pnpm, uv).
- Boot the `docker-compose` dev stack (Postgres 16 + pgvector, MinIO, Redis).
- Apply the baseline database migrations in `db/migrations/`.
- Install package workspaces and smoke-test every service.

### 3. Walk the phases

Each phase prompt in `prompts/` is a complete, self-contained instruction to Claude Code. They are sequential — do not skip. Every phase ends with a demoable deliverable keyed to the 2008 Dennis Ln · Santa Rosa · B25-2734 fixture.

| # | Prompt file | Weeks | Ships |
|---|---|---|---|
| 00 | `00-bootstrap.md` | 0 | Dev environment green |
| 01 | `01-phase-00-foundations.md` | 1 | Fixture ingested, title blocks extracted |
| 02 | `02-phase-01-sheet-identity.md` | 2–3 | BV comments 1, 4, 8, 9, 18, 24 auto-generated |
| 03 | `03-phase-02-schedules.md` | 4–5 | Cross-doc claims, R-value mismatch flagged |
| 04 | `04-phase-03-measurement.md` | 6–8 | Egress NCO, turning spaces, travel distance |
| 05 | `05-phase-04-arch-access.md` | 9–10 | BV comments 2, 10–17, 22, 25–38, 40, 42 |
| 06 | `06-phase-05-mep-structural-energy.md` | 11–12 | All 58 BV comments covered |
| 07 | `07-phase-06-drafter-letter.md` | 13 | Signed, sendable PDF letter |
| 08 | `08-phase-07-learning-loop.md` | 14 | Per-rule precision/recall dashboard |
| 09 | `09-phase-08-second-jurisdiction.md` | 15–16 | City-2 pack live |
| 10 | `10-phase-09-measurement-v2-qc-agent.md` | 17–18 | Designer portal live |
| 11 | `11-finalize-and-ship.md` | — | Production deploy + post-launch roadmap |

### 4. Skills

`skills/` holds the **ten discipline skills** that drive the review tier, plus cross-cutting skills for measurement, code-RAG, extraction, and the Santa Rosa jurisdictional pack. Each follows the canonical `SKILL.md` pattern:

- A scope statement defining what the reviewer covers and what it defers.
- A catalogue of the most frequent code citations for this jurisdiction.
- Common interpretations and known gotchas.
- Worked examples of well-phrased comments in the jurisdictional dialect.
- A decision tree for when to emit a finding vs defer to licensed review.

Skills are loaded into an agent's context **only when it runs**. They are diffable across code cycles.

### 5. Invariants

The six architectural invariants in `docs/invariants.md` are non-negotiable. If a phase's work appears to require violating one, the design is wrong — not the invariant.

---

## Repository layout

```
inzohra-ai/
├─ CLAUDE.md                  # Master system prompt for Claude Code
├─ .claude/                   # Project-scoped Claude rules, invariants, skills registry
├─ README.md                  # This file
├─ FEATURES.md                # Canonical feature list (the artifact deliverable)
│
├─ docs/                      # Production documentation — nine layers, data model, ops
│  ├─ 01-mission-and-scope.md
│  ├─ 02-architecture-nine-layers.md
│  ├─ 03-document-processing.md
│  ├─ 04-data-model-and-provenance.md
│  ├─ 05-measurement.md
│  ├─ 06-knowledge-base.md
│  ├─ 07-agents-and-skills.md
│  ├─ 08-question-checklist-agent.md
│  ├─ 09-reasoning-tools.md
│  ├─ 10-review-engine.md
│  ├─ 11-output-letter.md
│  ├─ 12-frontend.md
│  ├─ 13-learning-loop.md
│  ├─ 14-security-and-liability.md
│  ├─ 15-operations.md
│  ├─ 16-development-plan.md
│  ├─ 17-invariants-and-risks.md
│  └─ 18-glossary.md
│
├─ prompts/                   # Claude Code driver prompts, phase-by-phase
│
├─ skills/                    # Discipline + cross-cutting skills (SKILL.md each)
│
├─ schemas/                   # JSON Schemas for Finding, Entity, Measurement, Claim, …
│
├─ db/migrations/             # Postgres 16 + pgvector migrations
│
├─ apps/web/                  # Next.js 14 — reviewer workspace + designer portal
├─ services/ingestion/        # Python (FastAPI + workers): intake, extraction
├─ services/measurement/      # Python: scale, geometry, derived metrics
├─ services/review/           # Python: commander + 10 discipline reviewers
├─ services/rendering/        # Node: PDF/DOCX letter rendering
├─ packages/shared/           # Shared types, schemas, client bindings
│
├─ ops/                       # docker-compose, Helm, otel config, runbooks
├─ fixtures/                  # 2008 Dennis Ln fixture + expected BV letter
│
├─ pyproject.toml             # uv workspace, Python 3.11
├─ pnpm-workspace.yaml        # pnpm workspace
├─ docker-compose.yml         # dev stack: pg, redis, minio, traefik
└─ .env.example
```

---

## The fixture

Every phase is anchored to **2008 Dennis Ln · Santa Rosa · CA · Permit B25-2734** (2022 California Building Standards). The expected Bureau Veritas comment letter has 58 comments. The system is done when Inzohra-ai's output on this fixture is indistinguishable, at a glance, from a BV-authored letter.

Fixture files live in `fixtures/2008-dennis-ln/`. They are referenced by path throughout the phase prompts — do not move them.

---

## Tech stack (locked)

- **Postgres 16** + `pgvector` for relational data and embeddings.
- **S3 / MinIO** for raw files, rasterized crops, rendered outputs.
- **Redis** for job queues and caching.
- **Next.js 14** (App Router, RSC) for the reviewer/designer UI.
- **Python 3.11** (FastAPI, Pydantic v2, `uv`) for ingestion, extraction, measurement, review workers.
- **Node 20** (tsx, pdfkit + docx) for the rendering service.
- **Claude Sonnet** for most extraction and review LLM work; **Claude Opus** as the high-stakes / low-confidence escalation tier.
- **OpenTelemetry** for tracing; **Prometheus + Grafana** for metrics.
- **PDF.js** with a custom overlay layer for the sheet viewer.
- **Tailwind + Radix + TanStack Query + Zustand** on the frontend.

See `docs/15-operations.md` for the full deployment topology.

---

## Scope reminders

Inzohra-ai is **not**:
- a structural engineering tool (no shear-wall design, seismic analysis, load calc);
- an accessibility consultant (no CASp field determinations);
- a substitute for licensed professional judgment.

Anything on the legal critical path is flagged `requires_licensed_review` and cannot be auto-approved without an explicit reviewer sign-off. **Inzohra-ai never signs anything.**

Initial scope is the **2022 California code cycle, residential and mixed-occupancy, Santa Rosa first**. Every new city is a data release (a jurisdictional pack), not a software release.

---

## License & disclaimers

This scaffolding is proprietary to the Inzohra-ai project. Every output produced by the system carries the disclaimer in `docs/14-security-and-liability.md`. Read it before deploying.
