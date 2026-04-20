-- Phase 06: comment_drafts (polished BV-dialect text) + letter_renders (output tracking)
-- Idempotent — safe to run multiple times.

CREATE TABLE IF NOT EXISTS comment_drafts (
    draft_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id       UUID NOT NULL REFERENCES findings(finding_id) ON DELETE CASCADE,
    project_id       UUID NOT NULL,
    review_round     INT  NOT NULL,
    polished_text    TEXT NOT NULL,
    prompt_hash      TEXT NOT NULL,
    model            TEXT NOT NULL,
    tokens_in        INT  NOT NULL DEFAULT 0,
    tokens_out       INT  NOT NULL DEFAULT 0,
    latency_ms       INT  NOT NULL DEFAULT 0,
    cost_usd         NUMERIC(12,8) NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_comment_drafts_finding
    ON comment_drafts (finding_id);
CREATE INDEX IF NOT EXISTS idx_comment_drafts_project_round
    ON comment_drafts (project_id, review_round);

CREATE TABLE IF NOT EXISTS letter_renders (
    render_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id       UUID NOT NULL,
    review_round     INT  NOT NULL,
    pdf_path         TEXT,
    docx_path        TEXT,
    json_path        TEXT,
    finding_count    INT  NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_letter_renders_project
    ON letter_renders (project_id, review_round);
