-- Migration 0011: Phase 07 — Comparison tables
-- Creates external_review_comments, alignment_records, and reviewer_edits.
-- All statements are idempotent (CREATE TABLE IF NOT EXISTS).

-- external_review_comments was created in the baseline schema with external_comment_id as PK.
-- This migration does not recreate it; instead it adds any Phase-07 columns that may be missing.
ALTER TABLE external_review_comments ADD COLUMN IF NOT EXISTS comment_number INT;
ALTER TABLE external_review_comments ADD COLUMN IF NOT EXISTS sheet_ref TEXT;
ALTER TABLE external_review_comments ADD COLUMN IF NOT EXISTS discipline TEXT;

-- One row per AI-finding <-> authority-comment alignment attempt.
-- comment_id references external_review_comments(external_comment_id) — the actual PK column name.
CREATE TABLE IF NOT EXISTS alignment_records (
    alignment_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL,
    review_round    INT  NOT NULL DEFAULT 1,
    finding_id      UUID REFERENCES findings(finding_id),
    comment_id      UUID REFERENCES external_review_comments(external_comment_id),
    bucket          TEXT NOT NULL CHECK (bucket IN ('matched','missed','false_positive','partial')),
    similarity_score FLOAT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Levenshtein edit distance between draft and approved text per finding
CREATE TABLE IF NOT EXISTS reviewer_edits (
    edit_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id      UUID NOT NULL REFERENCES findings(finding_id),
    rule_id         TEXT,
    draft_text      TEXT,
    approved_text   TEXT,
    edit_distance   INT,
    edit_ratio      FLOAT,  -- edit_distance / max(len(draft), len(approved))
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
