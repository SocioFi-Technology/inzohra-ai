-- Migration 0014 — Phase 09: QuestionChecklistAgent tables
-- Idempotent: all CREATE TABLE / CREATE INDEX use IF NOT EXISTS.

-- Checklist queries parsed from uploaded checklist documents
CREATE TABLE IF NOT EXISTS checklist_queries (
    query_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES projects(project_id),
    checklist_doc_id    UUID,                   -- source document_id if from DB
    item_id             TEXT,                   -- from submittal checklist (e.g. "sfr-001")
    description         TEXT NOT NULL,          -- plain-English question
    target_entity_class TEXT,                   -- 'door' | 'window' | 'room' | 'egress_path' | null
    filter_predicates   JSONB,                  -- [{field, op, value}]
    measurement_types   TEXT[],                 -- which measurements to fetch
    code_ref            TEXT,                   -- canonical_id e.g. 'CRC-R310.2.1'
    threshold_value     REAL,
    threshold_unit      TEXT,
    confirmed_by_user   BOOLEAN NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Answers produced by the answer pipeline for each query
CREATE TABLE IF NOT EXISTS checklist_answers (
    answer_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id            UUID NOT NULL REFERENCES checklist_queries(query_id),
    project_id          UUID NOT NULL REFERENCES projects(project_id),
    status              TEXT NOT NULL CHECK (status IN ('green','amber','red','unknown')),
    measured_value      REAL,
    unit                TEXT,
    required_value      REAL,
    code_citation       JSONB,                  -- frozen citation dict from code-RAG
    evidence_entity_ids TEXT[],
    confidence          REAL,
    answer_text         TEXT NOT NULL,          -- one-sentence human-readable answer
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Designer reports (PDF/JSON output per checklist run)
CREATE TABLE IF NOT EXISTS designer_reports (
    report_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(project_id),
    report_type     TEXT NOT NULL DEFAULT 'checklist',
    status          TEXT NOT NULL CHECK (status IN ('pending','complete','error')),
    pdf_path        TEXT,
    json_path       TEXT,
    query_count     INT NOT NULL DEFAULT 0,
    green_count     INT NOT NULL DEFAULT 0,
    amber_count     INT NOT NULL DEFAULT 0,
    red_count       INT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_checklist_queries_project
    ON checklist_queries(project_id);

CREATE INDEX IF NOT EXISTS idx_checklist_answers_query
    ON checklist_answers(query_id);

CREATE INDEX IF NOT EXISTS idx_designer_reports_project
    ON designer_reports(project_id, created_at DESC);
