# LLM outage playbook

If the Anthropic API is degraded or down.

## Detection

- Error rate on `llm_call_log` inserts with `error_code IS NOT NULL` > 10% over 5 min → alert.
- P99 latency on Sonnet calls > 30s → alert.
- Anthropic status page red.

## Degraded mode

1. **Queue incoming work.** Stop starting new review-tier LLM passes. Ingestion and measurement continue (they are mostly non-LLM).
2. **Reviewer-facing message.** Banner: "Review processing is temporarily delayed due to an upstream provider outage. Your projects are queued and will complete once service resumes."
3. **Fall back to rules-only findings.** The UI shows rule-emitted findings immediately; the LLM tail (narrative-consistency, ambiguous callouts) is deferred.
4. **No silent failures.** Every LLM call that fails is retried with exponential backoff up to 3 times, then written to a `deferred_llm_calls` table for automatic replay when service resumes.

## Resumption

- On status-green + 10 successful calls in a row, drain the `deferred_llm_calls` backlog in FIFO order, rate-limited to avoid another cliff.
- Reviewer UI clears the banner once the backlog is empty.
