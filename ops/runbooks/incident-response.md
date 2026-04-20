# Incident response

## Severity ladder

- **SEV-1** — production down or data loss. Page on-call immediately.
- **SEV-2** — production degraded (queue backlog >10 min, elevated error rate, one region unavailable). Slack + ticket; on-call assesses within 30 min.
- **SEV-3** — minor impact (single customer, cosmetic issues). Ticket; addressed in the next business day.

## On-call

PagerDuty rotation, weekly handoff. Primary + secondary. Escalation to engineering lead after 15 min no-ack.

## Response

1. **Acknowledge** the page in PagerDuty.
2. **Declare** the incident in `#inz-incidents` Slack with severity.
3. **Assess** impact: who is affected? what's broken? what's the blast radius?
4. **Mitigate** before rooting. Roll back, scale up, take the feature flag down.
5. **Root cause** after mitigation. Write the post-mortem.
6. **Communicate** status every 30 min to the incident channel until resolved.

## Post-mortem

Within 5 business days of any SEV-1 or SEV-2. Published in `ops/post-mortems/`. Blameless; focused on systemic causes and remediation.
