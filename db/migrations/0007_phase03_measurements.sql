-- Phase 03: Measurement stack — add provenance fields to measurements.
-- All DDL idempotent.

-- Add bbox (for UI click targeting), entity_id (link to source entity), tag (door/window tag)
ALTER TABLE measurements
  ADD COLUMN IF NOT EXISTS bbox       REAL[],
  ADD COLUMN IF NOT EXISTS entity_id  UUID REFERENCES entities(entity_id),
  ADD COLUMN IF NOT EXISTS tag        TEXT;

CREATE INDEX IF NOT EXISTS idx_measurements_entity_id
  ON measurements(entity_id);
CREATE INDEX IF NOT EXISTS idx_measurements_tag
  ON measurements(project_id, tag);

-- Update pdf_quality_class check constraint to allow existing values (already correct in baseline)
-- No schema change needed — baseline already has this column on sheets.

-- Add structured index for sheet_type lookups (used by measurement pipeline)
CREATE INDEX IF NOT EXISTS idx_sheets_type
  ON sheets(project_id, sheet_type);
