-- Add page dimension columns to sheets.
-- These are filled during PDF ingestion from PyMuPDF page rect.
-- Needed by the UI to scale bbox overlays correctly.

ALTER TABLE sheets ADD COLUMN IF NOT EXISTS page_width_pts  REAL;
ALTER TABLE sheets ADD COLUMN IF NOT EXISTS page_height_pts REAL;
