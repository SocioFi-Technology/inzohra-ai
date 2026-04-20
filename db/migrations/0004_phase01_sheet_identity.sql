-- Phase 01: Sheet identity, sheet index, findings extensions.
-- Append-only. Idempotent.

-- ============================================================================
-- Sheet index (declared sheet list parsed from cover sheet)
-- ============================================================================
CREATE TABLE IF NOT EXISTS sheet_index_entries (
  entry_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID NOT NULL REFERENCES projects(project_id),
  document_id UUID NOT NULL REFERENCES documents(document_id),
  source_sheet_id TEXT NOT NULL REFERENCES sheets(sheet_id),
  declared_id TEXT NOT NULL,
  declared_title TEXT,
  bbox REAL[] NOT NULL,
  extractor_version TEXT NOT NULL,
  confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sheet_index_project
  ON sheet_index_entries(project_id);
CREATE INDEX IF NOT EXISTS idx_sheet_index_declared
  ON sheet_index_entries(project_id, declared_id);

-- ============================================================================
-- Extra columns on sheets for Phase 01
-- Every column is nullable to keep legacy rows valid.
-- ============================================================================
ALTER TABLE sheets
  ADD COLUMN IF NOT EXISTS canonical_title TEXT,
  ADD COLUMN IF NOT EXISTS sheet_identifier_confidence REAL;

-- ============================================================================
-- Findings-adjacent: mark the submittal the finding was generated from.
-- `submittal_id` already exists; add an index on (project, round) for list views.
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_findings_project_round
  ON findings(project_id, review_round, discipline);

-- ============================================================================
-- Reference: Santa Rosa jurisdictional pack + effective cycle stub.
-- Populated by kb:seed. Idempotent on conflict.
-- ============================================================================
INSERT INTO jurisdictional_packs (pack_id, jurisdiction, version, effective_date, manifest)
VALUES (
  'santa_rosa_2022',
  'santa_rosa',
  '2022-ca-cycle',
  '2023-01-01',
  '{"notes": "Santa Rosa amendments pack — empty for Phase 01; populated in Phase 08."}'::jsonb
)
ON CONFLICT (pack_id) DO NOTHING;
