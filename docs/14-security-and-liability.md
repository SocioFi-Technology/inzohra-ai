# § 14 — Security, privacy, and licensed-professional liability

## Security

- **Transport** — TLS 1.3 everywhere. HSTS. No plaintext ports open on any service.
- **At rest** — Postgres volumes encrypted (LUKS in dev, cloud-provider KMS in prod). S3 buckets with SSE-KMS. Redis with ACL and TLS.
- **Auth** — NextAuth for the web tier; SSO (OIDC/SAML) for reviewer-firm integrations; service-to-service via short-lived JWTs signed by an internal issuer.
- **Secrets** — AWS Secrets Manager / Vault. Nothing committed. `.env` files gitignored.
- **Network** — services communicate over a private VPC. Public surface is the web app and a narrow API gateway only.
- **Audit log** — every reviewer action, every admin action, every access to a project that isn't the reviewer's own.
- **Rate limits** — token bucket per-user on the API; per-provider on LLM calls.

## Privacy

- **PII inventory** — project addresses, occupant names on plans, reviewer contact info. Enumerated in `docs/privacy/pii-inventory.md`.
- **Retention** — raw submittal documents retained per jurisdictional requirement (Santa Rosa: 7 years post-permit-close). Derived artefacts retained for the same period for provenance.
- **Deletion** — a customer-initiated project deletion is soft; after retention window and a legal review, hard delete cascades through S3, Postgres, and object-store derivatives.
- **Tenant isolation** — every project is scoped to a `tenant_id`. No cross-tenant query paths. Row-level security in Postgres as a belt-and-braces defense.

## Copyright on code text

- The knowledge base contains excerpts of California codes (Title 24, CRC, CBC, etc.). California Building Standards Commission text is publicly available; we attribute and cite.
- Agency policies and interpretations: most Santa Rosa Fire Department memos are public and ingested directly.
- Legal model: Inzohra-ai is a tool that supports licensed reviewers; any code text displayed is displayed in the context of a professional review they are authorized to perform. We are not a code publisher; we are a reviewer workflow product.

## Licensed-professional liability

- Every output carries a disclaimer: *Inzohra-ai is a reviewer's assistant, not a substitute for licensed professional judgment.*
- Any finding on the legal critical path is marked `requires_licensed_review` and cannot be auto-approved without explicit reviewer sign-off.
- The final letter is signed by the licensed reviewer under their own license. **Inzohra-ai does not sign anything.**
- Contractual terms with reviewer-firm customers explicitly allocate responsibility: the firm's licensed reviewer is responsible for letter content; Inzohra-ai is responsible for system operation as specified.
- E&O insurance is carried by both parties at scale-appropriate coverage.

## Incident response

- Runbook in `ops/runbooks/incident-response.md`.
- On-call rotation via PagerDuty (or equivalent).
- Severity ladder: SEV-1 (production down or data-loss) → page on-call; SEV-2 (degraded) → Slack + ticket; SEV-3 (minor) → ticket.
- Post-mortem within 5 business days for any SEV-1 or SEV-2, published internally.
