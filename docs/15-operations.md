# § 15 — Operations: deployment, scaling, observability

Inzohra-ai runs as a set of stateless services backed by stateful storage. Horizontal scaling on every processing tier; vertical scaling on the storage tier as data volumes grow.

## Deployment topology

- **API service** — Next.js app handling the reviewer workspace and designer portal.
- **Ingestion workers** — Python services behind Redis queues processing uploads and running extraction pipelines.
- **Measurement workers** — Python services running the six measurement sub-layers.
- **Review workers** — Python services running rule evaluations and LLM reasoning for review-tier agents.
- **Rendering workers** — Node services producing PDFs and DOCX exports.
- **Scheduled jobs** — metric aggregation, citation audits, retention cleanup.
- **Postgres primary** with read replicas for analytics queries.
- **pgvector** on the primary for embedding retrieval.
- **S3** (MinIO in dev) for object storage.
- **Redis** for queues and session cache.

All workers are stateless and queue-driven.

## Scaling strategy

- **Processing capacity** scales horizontally. More workers = more throughput. Ingestion queue handles bursts (a firm uploads fifty projects on Monday morning); review queue runs continuously as ingestion completes.
- **LLM rate limits** become the binding constraint at scale, managed by a token-bucket scheduler per provider.
- **Storage** scales with data. Hot projects on Postgres primary; warm projects in a separate schema with slower SLAs; cold projects archive to Parquet on S3 with a thin metadata index on Postgres.
- **Code KB** lives on its own schema, cached aggressively because read-heavy and rarely updated.

## Environments

- **Local** — `docker-compose up`; Postgres, Redis, MinIO, Traefik. Uses `fixtures/` for smoke testing.
- **Staging** — full cloud stack, isolated tenant. Every PR that merges to `main` deploys to staging.
- **Production** — customer-facing. Deploys from `main` after staging soak + fixture regression green.

## Observability

- **Tracing** — OpenTelemetry end-to-end. Every request traced.
- **LLM logs** — prompt hash, model, tokens, latency, cost on every call.
- **Rule logs** — inputs, outputs, latency on every rule evaluation.
- **Retrieval logs** — query, matched section IDs, score on every code-RAG call.
- **Metrics** — queue depth, worker utilization, end-to-end project turnaround, rule-level precision/recall.
- **Alerts** — hallucination signals, precision drops, LLM cost anomalies, queue backlogs.

## Cost envelope (steady state, 50-sheet residential)

| Step | Cost |
|---|---|
| Ingestion + extraction (Haiku classify, Sonnet extract) | $2–4 |
| Measurement stack (Sonnet vision) | $0.50–1 |
| Review engine (Sonnet primary, Opus high-stakes) | $2–5 |
| Comment drafting (Sonnet) | $0.50–1 |
| **API total** | **$5–11** |
| Infra amortized | $1–3 |
| **COGS per project** | **$7–14** |

Pricing supports this with comfortable margin: $50–150/project for designer-portal use; low-tens-of-thousands/year for reviewer-firm annual contracts.

## Backups

- Postgres WAL-shipped to S3, PITR window of 30 days.
- S3 objects: versioning on, lifecycle policy to Glacier after 90 days.
- Quarterly restore drill from backup to a scratch environment.
