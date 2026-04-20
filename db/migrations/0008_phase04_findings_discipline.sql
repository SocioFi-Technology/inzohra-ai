-- Phase 04: ensure findings discipline index exists for metric queries
-- Idempotent: CREATE INDEX IF NOT EXISTS

CREATE INDEX IF NOT EXISTS idx_findings_project_discipline
    ON findings (project_id, discipline, review_round);

CREATE INDEX IF NOT EXISTS idx_findings_rule_id
    ON findings (project_id, rule_id);

-- external_review_comments already has project_id; add index for metric join
CREATE INDEX IF NOT EXISTS idx_ext_comments_project
    ON external_review_comments (project_id);
