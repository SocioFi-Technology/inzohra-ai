# Prompt 11 — Finalize and ship

Prerequisite: Phase 09 shipped.

## Goal

Production deploy, runbook, on-call rotation, post-launch roadmap.

## Build

1. **Production deploy topology** — finalize per `docs/15-operations.md`:
   - Next.js app on a managed platform (Vercel, Railway, or AWS ECS Fargate).
   - Python workers on ECS Fargate or Cloud Run, queue-driven.
   - Node rendering workers on the same platform as workers.
   - Postgres + pgvector on RDS/Cloud SQL with read replicas.
   - Redis on ElastiCache/Memorystore.
   - S3 with SSE-KMS + lifecycle to Glacier after 90 days.
   - Traefik or Cloud Load Balancer as ingress.
   - Internal mTLS via cert-manager.
2. **Secrets & config** — AWS Secrets Manager or Vault. Twelve-factor env plumbing.
3. **Observability bundle** — OpenTelemetry collectors; Grafana + Prometheus or Datadog; alert rules per `docs/15-operations.md`.
4. **Runbooks** in `ops/runbooks/`:
   - `incident-response.md` — SEV ladder, paging, rollback.
   - `llm-outage.md` — Anthropic outage playbook; degraded mode.
   - `fixture-regression.md` — what to do when fixture regression blocks a merge.
   - `pack-promotion.md` — how to promote a jurisdictional pack from staging to prod.
   - `restore-from-backup.md` — WAL-based PITR drill.
5. **On-call rotation** — PagerDuty schedule, escalation, severity definitions.
6. **Legal review** — terms of service, data-processing agreement template, E&O insurance binder, privacy policy. Not engineering-owned end-to-end, but engineering must confirm the disclaimer text renders on every output.
7. **Disclaimer rendering** — every PDF, every DOCX, every JSON bundle carries the disclaimer from `docs/14-security-and-liability.md`:
   > *Inzohra-ai is a reviewer's assistant, not a substitute for licensed professional judgment. Any finding on the legal critical path is flagged for licensed sign-off and is not auto-approved.*
8. **Onboarding checklist** for the first reviewer-firm customer (Bureau Veritas Santa Rosa): SSO setup, user provisioning, project history migration (if any), support channel.
9. **Post-launch roadmap** in `docs/roadmap.md`:
   - Phase 10+: additional jurisdictions (one per month).
   - Phase 11+: additional disciplines (landscape, civil, fire-alarm specifics).
   - Phase 12+: integration with Accela, EnerGov, Tyler EnerGov.
   - Phase 13+: commercial and nonresidential occupancies beyond R.
   - Phase 14+: mobile companion for on-site review.

## Acceptance criteria

- [ ] Production environment green across all services.
- [ ] Synthetic monitoring (hits `/healthz` every 60s from three regions) green.
- [ ] All runbooks written and reviewed.
- [ ] PagerDuty rotation live.
- [ ] Every output carries the disclaimer.
- [ ] First customer onboarded in staging; confirm end-to-end flow on a real project.
- [ ] `pnpm test:fixture --phase all` passes across the full fixture library.

Tag `v1.0.0`. Report `INZOHRA-AI v1.0.0: SHIPPED`.

---

## Post-v1.0 operating rhythm

- Weekly fixture regression review: what passed, what slipped, what rules need tuning.
- Monthly pack release cadence: one new jurisdiction per month.
- Quarterly learning-loop retro: triage queue throughput, skill updates, prompt hot-swaps.
- Annual code-cycle readiness: when California adopts a new Title 24 (2025 cycle next), the pipeline re-runs for affected sections; affected active projects are flagged for re-review.
