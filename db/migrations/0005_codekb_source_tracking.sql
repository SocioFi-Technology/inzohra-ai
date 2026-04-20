-- Phase 02: Code-KB source tracking.
-- Adds provenance columns to code_sections so every row can be traced
-- back to the exact PDF page(s) it was parsed from.
-- Also adds a code_book_loads audit table for idempotent re-processing.

-- ============================================================================
-- Source columns on code_sections
-- ============================================================================
ALTER TABLE code_sections
  ADD COLUMN IF NOT EXISTS source_pdf   TEXT,          -- relative path from repo root
  ADD COLUMN IF NOT EXISTS source_pages INT[],         -- 1-indexed PDF page numbers
  ADD COLUMN IF NOT EXISTS parse_version TEXT;         -- code-pdf-parser version tag

-- ============================================================================
-- code_book_loads — one row per (pdf, parse_version) run
-- ============================================================================
CREATE TABLE IF NOT EXISTS code_book_loads (
  load_id          UUID    PRIMARY KEY DEFAULT uuid_generate_v4(),
  pdf_path         TEXT    NOT NULL,           -- relative path from repo root
  code             TEXT    NOT NULL,           -- 'CBC', 'CRC', 'CMC', …
  effective_date   DATE    NOT NULL,
  parse_version    TEXT    NOT NULL,
  section_count    INT     NOT NULL DEFAULT 0,
  embedded_count   INT     NOT NULL DEFAULT 0,
  status           TEXT    NOT NULL DEFAULT 'pending'
                           CHECK (status IN ('pending','running','done','failed')),
  error_detail     TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_code_book_loads_pdf
  ON code_book_loads(pdf_path, parse_version);
