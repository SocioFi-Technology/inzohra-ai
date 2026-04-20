-- Phase 02: schedules, structured extraction, cross-doc claims.
-- All DDL is idempotent (IF NOT EXISTS / IF NOT COLUMN).

-- ============================================================================
-- external_review_comments — add discipline_group for BV-letter grouping
-- ============================================================================
ALTER TABLE external_review_comments
  ADD COLUMN IF NOT EXISTS discipline_group TEXT,      -- BV section header (e.g. "ARCHITECTURE")
  ADD COLUMN IF NOT EXISTS response_text    TEXT,      -- designer response (round 2+)
  ADD COLUMN IF NOT EXISTS is_resolved      BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_ext_comments_project_round
  ON external_review_comments(project_id, review_round);

CREATE INDEX IF NOT EXISTS idx_ext_comments_number
  ON external_review_comments(project_id, comment_number);

-- ============================================================================
-- cross_doc_claims — already exists in baseline; add claim_version + index
-- ============================================================================
ALTER TABLE cross_doc_claims
  ADD COLUMN IF NOT EXISTS claim_version TEXT NOT NULL DEFAULT '1.0.0',
  ADD COLUMN IF NOT EXISTS builder_version TEXT;

CREATE INDEX IF NOT EXISTS idx_cross_doc_claims_type
  ON cross_doc_claims(project_id, claim_type);

-- ============================================================================
-- schedule_rows — typed storage for individual schedule rows.
-- One row per schedule entry (door, window, holdown, fastener, wall …).
-- The parent entity is an entity of type 'door_schedule' / 'window_schedule' etc.
-- ============================================================================
CREATE TABLE IF NOT EXISTS schedule_rows (
  row_id          UUID  PRIMARY KEY DEFAULT uuid_generate_v4(),
  entity_id       UUID  NOT NULL REFERENCES entities(entity_id),
  project_id      UUID  NOT NULL REFERENCES projects(project_id),
  schedule_type   TEXT  NOT NULL,          -- 'door_schedule','window_schedule', …
  row_index       INT   NOT NULL,           -- 0-based order within the schedule
  tag             TEXT,                     -- MARK / TAG value (e.g. "1", "W-3")
  payload         JSONB NOT NULL,           -- all column values as {col: val}
  bbox            REAL[] NOT NULL,
  confidence      REAL  NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  extractor_version TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_schedule_rows_entity   ON schedule_rows(entity_id);
CREATE INDEX IF NOT EXISTS idx_schedule_rows_project  ON schedule_rows(project_id, schedule_type);
CREATE INDEX IF NOT EXISTS idx_schedule_rows_tag      ON schedule_rows(project_id, schedule_type, tag);

-- ============================================================================
-- Indexes to speed up Cross-doc claim queries
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_entities_type_project
  ON entities(project_id, type);
