-- Migration 0013: Phase 08 — Second-jurisdiction pack support.
-- Adds submittal_checklists, drafter_examples, and adds jurisdiction scoping
-- to both the rule_metrics_live VIEW and the rule_metrics MATERIALIZED VIEW.
-- All DDL is idempotent where possible; the materialized view is dropped and
-- recreated because ALTER MATERIALIZED VIEW cannot add columns.

-- ============================================================================
-- 1. submittal_checklists
--    Per-jurisdiction, per-occupancy-class checklist of items that every
--    submittal must include.  NULL occupancy_class means the checklist
--    applies to all occupancy classes within the jurisdiction pack.
-- ============================================================================

CREATE TABLE IF NOT EXISTS submittal_checklists (
    checklist_id    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    pack_id         TEXT        NOT NULL REFERENCES jurisdictional_packs(pack_id),
    occupancy_class TEXT,                        -- 'R-3', 'R-2', 'A-2', NULL = all
    checklist_items JSONB       NOT NULL,        -- [{item_id, description, code_ref, required}]
    version         TEXT        NOT NULL,
    effective_date  DATE        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index: fast lookup by pack + occupancy class
CREATE INDEX IF NOT EXISTS idx_submittal_checklists_pack
    ON submittal_checklists (pack_id, occupancy_class);

-- ============================================================================
-- 2. drafter_examples
--    BV-dialect approved comment examples used by CommentDrafterAgent as
--    few-shot material.  Keyed by pack + discipline + severity so the drafter
--    can retrieve only the examples that match the current review context.
-- ============================================================================

CREATE TABLE IF NOT EXISTS drafter_examples (
    example_id       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    pack_id          TEXT        NOT NULL REFERENCES jurisdictional_packs(pack_id),
    discipline       TEXT        NOT NULL,
    severity         TEXT        NOT NULL CHECK (severity IN ('revise','provide','clarify','reference_only')),
    draft_input      TEXT        NOT NULL,  -- raw draft text that went into approval
    polished_output  TEXT        NOT NULL,  -- approved BV-dialect output text
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index: fast lookup by pack + discipline + severity
CREATE INDEX IF NOT EXISTS idx_drafter_examples_pack_disc_sev
    ON drafter_examples (pack_id, discipline, severity);

-- ============================================================================
-- 3. rule_metrics_live VIEW — add jurisdiction column.
--    DROP and CREATE OR REPLACE because adding a column to a view requires
--    recreating it; CREATE OR REPLACE is valid here (just modifies the def).
--    findings → projects gives us jurisdiction without any extra join cost.
-- ============================================================================

-- NOTE: jurisdiction is appended as the LAST column so CREATE OR REPLACE VIEW
-- does not need to change the position of any existing column.
CREATE OR REPLACE VIEW rule_metrics_live AS
SELECT
    f.rule_id,
    f.discipline,
    COUNT(DISTINCT f.finding_id)                                                 AS total_findings,
    COUNT(DISTINCT ar.finding_id) FILTER (WHERE ar.bucket = 'matched')           AS matched,
    COUNT(DISTINCT ar.finding_id) FILTER (WHERE ar.bucket = 'false_positive')    AS false_positives,
    COUNT(DISTINCT ar.comment_id) FILTER (WHERE ar.bucket = 'missed')            AS missed,
    ROUND(
        CASE WHEN COUNT(DISTINCT f.finding_id) > 0
             THEN COUNT(DISTINCT ar.finding_id) FILTER (WHERE ar.bucket = 'matched')::numeric
                  / COUNT(DISTINCT f.finding_id)
             ELSE NULL
        END, 3
    )                                                                            AS precision,
    AVG(f.confidence)                                                            AS avg_confidence,
    MAX(f.created_at)                                                            AS last_evaluated_at,
    p.jurisdiction                                                               -- appended last (Phase 08)
FROM findings f
JOIN projects p ON p.project_id = f.project_id
LEFT JOIN alignment_records ar ON ar.finding_id = f.finding_id
GROUP BY f.rule_id, f.discipline, p.jurisdiction;

-- ============================================================================
-- 4. rule_metrics MATERIALIZED VIEW — add jurisdiction column.
--    ALTER MATERIALIZED VIEW cannot add columns, so we drop and recreate.
--    WITH NO DATA: caller must run REFRESH MATERIALIZED VIEW rule_metrics
--    after migration to populate data.
--    The unique index is recreated afterwards to maintain idempotency.
-- ============================================================================

-- Drop the old index first (depends on the view)
DROP INDEX IF EXISTS rule_metrics_rule_id_idx;

-- Safety: drop as plain TABLE in case migration 0012 did not run yet
DROP TABLE IF EXISTS rule_metrics;

-- Drop and recreate the materialized view with jurisdiction
DROP MATERIALIZED VIEW IF EXISTS rule_metrics;

CREATE MATERIALIZED VIEW rule_metrics AS
SELECT
    f.rule_id,
    f.discipline,
    p.jurisdiction,                                                              -- NEW
    COUNT(DISTINCT f.finding_id)                                                 AS total_findings,
    COUNT(DISTINCT ar.finding_id) FILTER (WHERE ar.bucket = 'matched')           AS matched,
    COUNT(DISTINCT ar.finding_id) FILTER (WHERE ar.bucket = 'false_positive')    AS false_positives,
    COUNT(DISTINCT erc.external_comment_id) FILTER (WHERE ar.bucket = 'missed')  AS missed,
    CASE WHEN COUNT(DISTINCT f.finding_id) > 0
         THEN COUNT(DISTINCT ar.finding_id) FILTER (WHERE ar.bucket = 'matched')::float
              / COUNT(DISTINCT f.finding_id)
         ELSE NULL
    END                                                                          AS precision,
    CASE WHEN (
                SELECT COUNT(*) FROM external_review_comments erc2
                 WHERE erc2.project_id = f.project_id
              ) > 0
         THEN COUNT(DISTINCT ar.finding_id) FILTER (WHERE ar.bucket = 'matched')::float
              / NULLIF(
                    (SELECT COUNT(*) FROM external_review_comments erc3
                      WHERE erc3.project_id = f.project_id),
                    0
                )
         ELSE NULL
    END                                                                          AS recall,
    MAX(f.created_at)                                                            AS last_evaluated_at
FROM findings f
JOIN projects p ON p.project_id = f.project_id                                  -- NEW
LEFT JOIN alignment_records ar ON ar.finding_id = f.finding_id
LEFT JOIN external_review_comments erc ON erc.external_comment_id = ar.comment_id
GROUP BY f.rule_id, f.discipline, p.jurisdiction, f.project_id                  -- NEW
WITH NO DATA;

-- Recreate the unique index on the new column set
CREATE UNIQUE INDEX rule_metrics_rule_id_idx
    ON rule_metrics (rule_id, discipline, jurisdiction);
