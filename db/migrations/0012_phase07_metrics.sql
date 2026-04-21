-- Migration 0012: Phase 07 — Prompt versioning, shadow runs, and metrics views.
-- All statements are idempotent (CREATE TABLE IF NOT EXISTS, CREATE OR REPLACE VIEW).

-- Prompt versioning for shadow-deploy
CREATE TABLE IF NOT EXISTS prompt_versions (
    version_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_key      TEXT NOT NULL,        -- e.g. 'drafter_system', 'arch_reviewer_system'
    version_tag     TEXT NOT NULL,        -- e.g. 'v1', 'v2-concise'
    prompt_text     TEXT NOT NULL,
    is_default      BOOLEAN NOT NULL DEFAULT false,
    shadow          BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(prompt_key, version_tag)
);

-- Shadow run: both old+new prompt ran; outputs stored for comparison
CREATE TABLE IF NOT EXISTS shadow_runs (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL,
    finding_id      UUID REFERENCES findings(finding_id),
    prompt_key      TEXT NOT NULL,
    control_version TEXT NOT NULL,
    shadow_version  TEXT NOT NULL,
    control_output  TEXT,
    shadow_output   TEXT,
    winner          TEXT CHECK (winner IN ('control','shadow','tie',NULL)),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- rule_metrics existed as a plain TABLE in earlier schema versions; drop it so
-- we can replace it with a materialized view. Handle both cases idempotently:
-- a plain table (fresh DB) or an already-created materialized view (re-run).
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_matviews WHERE matviewname = 'rule_metrics') THEN
    DROP MATERIALIZED VIEW rule_metrics;
  ELSIF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'rule_metrics' AND schemaname = 'public') THEN
    DROP TABLE rule_metrics;
  END IF;
END $$;

-- Per-rule precision/recall metrics (refreshed nightly via REFRESH MATERIALIZED VIEW)
CREATE MATERIALIZED VIEW IF NOT EXISTS rule_metrics AS
SELECT
    f.rule_id,
    f.discipline,
    COUNT(DISTINCT f.finding_id)                                   AS total_findings,
    COUNT(DISTINCT ar.finding_id) FILTER (WHERE ar.bucket = 'matched')    AS matched,
    COUNT(DISTINCT ar.finding_id) FILTER (WHERE ar.bucket = 'false_positive') AS false_positives,
    COUNT(DISTINCT erc.external_comment_id) FILTER (WHERE ar.bucket = 'missed') AS missed,
    CASE WHEN COUNT(DISTINCT f.finding_id) > 0
         THEN COUNT(DISTINCT ar.finding_id) FILTER (WHERE ar.bucket = 'matched')::float
              / COUNT(DISTINCT f.finding_id)
         ELSE NULL END                                             AS precision,
    CASE WHEN (SELECT COUNT(*) FROM external_review_comments erc2
               WHERE erc2.project_id = f.project_id) > 0
         THEN COUNT(DISTINCT ar.finding_id) FILTER (WHERE ar.bucket = 'matched')::float
              / NULLIF((SELECT COUNT(*) FROM external_review_comments erc3
                        WHERE erc3.project_id = f.project_id), 0)
         ELSE NULL END                                             AS recall,
    MAX(f.created_at)                                              AS last_evaluated_at
FROM findings f
LEFT JOIN alignment_records ar ON ar.finding_id = f.finding_id
LEFT JOIN external_review_comments erc ON erc.external_comment_id = ar.comment_id
GROUP BY f.rule_id, f.discipline, f.project_id
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS rule_metrics_rule_id_idx ON rule_metrics(rule_id, discipline);

-- Simpler per-rule metrics view (non-materialized) for immediate use before data exists
CREATE OR REPLACE VIEW rule_metrics_live AS
SELECT
    f.rule_id,
    f.discipline,
    COUNT(DISTINCT f.finding_id)                                                          AS total_findings,
    COUNT(DISTINCT ar.finding_id) FILTER (WHERE ar.bucket = 'matched')                   AS matched,
    COUNT(DISTINCT ar.finding_id) FILTER (WHERE ar.bucket = 'false_positive')            AS false_positives,
    COUNT(DISTINCT ar.comment_id) FILTER (WHERE ar.bucket = 'missed')                    AS missed,
    ROUND(
      CASE WHEN COUNT(DISTINCT f.finding_id) > 0
           THEN COUNT(DISTINCT ar.finding_id) FILTER (WHERE ar.bucket = 'matched')::numeric
                / COUNT(DISTINCT f.finding_id)
           ELSE NULL END, 3
    )                                                                                     AS precision,
    AVG(f.confidence)                                                                     AS avg_confidence,
    MAX(f.created_at)                                                                     AS last_evaluated_at
FROM findings f
LEFT JOIN alignment_records ar ON ar.finding_id = f.finding_id
GROUP BY f.rule_id, f.discipline;
