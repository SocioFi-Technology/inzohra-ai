-- Inzohra-ai baseline schema.
-- Append-only. Every table carries created_at + relevant version stamps.
-- Run: psql $DATABASE_URL -f db/migrations/0001_baseline.sql

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- Tenants & users
-- ============================================================================

CREATE TABLE IF NOT EXISTS tenants (
  tenant_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('reviewer_firm', 'design_firm', 'ahj')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
  email TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('reviewer', 'senior_reviewer', 'admin', 'designer')),
  is_licensed BOOLEAN NOT NULL DEFAULT false,
  license_number TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- Projects, submittals, documents, sheets
-- ============================================================================

CREATE TABLE IF NOT EXISTS projects (
  project_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
  address TEXT NOT NULL,
  apn TEXT,
  permit_number TEXT,
  jurisdiction TEXT NOT NULL,
  effective_date DATE NOT NULL,
  occupancy_class TEXT,
  construction_type TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS submittals (
  submittal_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID NOT NULL REFERENCES projects(project_id),
  parent_submittal_id UUID REFERENCES submittals(submittal_id),
  round_number INT NOT NULL DEFAULT 1,
  kind TEXT NOT NULL CHECK (kind IN ('initial', 'resubmittal', 'deferred')),
  received_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
  document_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  submittal_id UUID NOT NULL REFERENCES submittals(submittal_id),
  doc_type TEXT NOT NULL CHECK (doc_type IN ('plan_set','title24_report','plan_check_letter','narrative','question_checklist','deferred_submittal','supporting_doc')),
  content_hash TEXT NOT NULL UNIQUE,
  s3_uri TEXT NOT NULL,
  filename TEXT NOT NULL,
  page_count INT,
  authoring_org TEXT,
  extractor_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sheets (
  sheet_id TEXT PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects(project_id),
  document_id UUID NOT NULL REFERENCES documents(document_id),
  page INT NOT NULL,
  discipline_letter CHAR(1),
  sheet_number TEXT,
  canonical_id TEXT,
  sheet_type TEXT,
  declared_scale TEXT,
  calibrated_scale_ratio REAL,
  pdf_quality_class TEXT CHECK (pdf_quality_class IN ('vector','hybrid','raster','low_quality_scan')),
  thumb_uri TEXT,
  extract_raster_uri TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sheets_project ON sheets(project_id);
CREATE INDEX IF NOT EXISTS idx_documents_submittal ON documents(submittal_id);

-- ============================================================================
-- Entities, measurements, cross-doc claims
-- ============================================================================

CREATE TABLE IF NOT EXISTS entities (
  entity_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID NOT NULL REFERENCES projects(project_id),
  document_id UUID NOT NULL REFERENCES documents(document_id),
  sheet_id TEXT REFERENCES sheets(sheet_id),
  type TEXT NOT NULL,
  payload JSONB NOT NULL,
  bbox REAL[] NOT NULL,
  page INT NOT NULL,
  extractor_version TEXT NOT NULL,
  confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  source_track TEXT CHECK (source_track IN ('text','vision','merged')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_entities_project_type ON entities(project_id, type);
CREATE INDEX IF NOT EXISTS idx_entities_sheet ON entities(sheet_id);
CREATE INDEX IF NOT EXISTS idx_entities_payload_gin ON entities USING GIN (payload);

CREATE TABLE IF NOT EXISTS measurements (
  measurement_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID NOT NULL REFERENCES projects(project_id),
  sheet_id TEXT NOT NULL REFERENCES sheets(sheet_id),
  type TEXT NOT NULL,
  value REAL NOT NULL,
  unit TEXT NOT NULL,
  confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  trace JSONB NOT NULL,
  override_history JSONB NOT NULL DEFAULT '[]'::jsonb,
  extractor_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_measurements_project ON measurements(project_id);
CREATE INDEX IF NOT EXISTS idx_measurements_sheet_type ON measurements(sheet_id, type);

CREATE TABLE IF NOT EXISTS cross_doc_claims (
  claim_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID NOT NULL REFERENCES projects(project_id),
  claim_type TEXT NOT NULL,
  resolved_value JSONB NOT NULL,
  confidence REAL NOT NULL,
  sources JSONB NOT NULL,
  conflicts JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- Code KB
-- ============================================================================

CREATE TABLE IF NOT EXISTS jurisdictional_packs (
  pack_id TEXT PRIMARY KEY,
  jurisdiction TEXT NOT NULL,
  version TEXT NOT NULL,
  effective_date DATE NOT NULL,
  superseded_by TEXT REFERENCES jurisdictional_packs(pack_id),
  manifest JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS code_sections (
  section_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  canonical_id TEXT NOT NULL,
  code TEXT NOT NULL,
  section_number TEXT NOT NULL,
  title TEXT,
  body_text TEXT NOT NULL,
  tables_json JSONB,
  figures_json JSONB,
  effective_date DATE NOT NULL,
  superseded_by_id UUID REFERENCES code_sections(section_id),
  embedding vector(1536),
  cross_references TEXT[],
  referenced_standards TEXT[],
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_code_sections_canonical ON code_sections(canonical_id, effective_date);
CREATE INDEX IF NOT EXISTS idx_code_sections_embedding ON code_sections USING ivfflat (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS amendments (
  amendment_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  base_section_id UUID NOT NULL REFERENCES code_sections(section_id),
  pack_id TEXT NOT NULL REFERENCES jurisdictional_packs(pack_id),
  operation TEXT NOT NULL CHECK (operation IN ('replace','append','override','insert_before','insert_after')),
  amendment_text TEXT NOT NULL,
  effective_date DATE NOT NULL,
  superseded_by_id UUID REFERENCES amendments(amendment_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agency_policies (
  policy_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  pack_id TEXT NOT NULL REFERENCES jurisdictional_packs(pack_id),
  title TEXT NOT NULL,
  body_text TEXT NOT NULL,
  source_url TEXT,
  applies_to_sections TEXT[],
  effective_date DATE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- Findings, external comments, reviewer actions
-- ============================================================================

CREATE TABLE IF NOT EXISTS findings (
  finding_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID NOT NULL REFERENCES projects(project_id),
  submittal_id UUID NOT NULL REFERENCES submittals(submittal_id),
  review_round INT NOT NULL,
  discipline TEXT NOT NULL,
  rule_id TEXT,
  rule_version TEXT,
  llm_reasoner_id TEXT,
  prompt_hash TEXT,
  severity TEXT NOT NULL CHECK (severity IN ('revise','provide','clarify','reference_only')),
  requires_licensed_review BOOLEAN NOT NULL DEFAULT false,
  sheet_reference JSONB NOT NULL,
  evidence JSONB NOT NULL,
  citations JSONB NOT NULL,
  draft_comment_text TEXT NOT NULL,
  confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  approval_state TEXT NOT NULL DEFAULT 'pending' CHECK (approval_state IN ('pending','approved','edited','merged','split','rejected')),
  final_comment_text TEXT,
  extractor_versions_used TEXT[],
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_findings_project_discipline ON findings(project_id, discipline);
CREATE INDEX IF NOT EXISTS idx_findings_rule ON findings(rule_id, rule_version);

CREATE TABLE IF NOT EXISTS external_review_comments (
  external_comment_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID NOT NULL REFERENCES projects(project_id),
  submittal_id UUID NOT NULL REFERENCES submittals(submittal_id),
  review_round INT NOT NULL,
  discipline TEXT,
  comment_number INT NOT NULL,
  comment_text TEXT NOT NULL,
  citation_text TEXT,
  sheet_reference TEXT,
  bbox_crop_uri TEXT,
  typography TEXT CHECK (typography IN ('italic','bold','underlined')),
  source_document_id UUID NOT NULL REFERENCES documents(document_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reviewer_actions (
  action_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID NOT NULL REFERENCES projects(project_id),
  finding_id UUID REFERENCES findings(finding_id),
  measurement_id UUID REFERENCES measurements(measurement_id),
  reviewer_id UUID NOT NULL REFERENCES users(user_id),
  action TEXT NOT NULL CHECK (action IN ('approve','edit','merge','split','reject','override')),
  rationale TEXT,
  before_state JSONB,
  after_state JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- Logs — provenance & cost
-- ============================================================================

CREATE TABLE IF NOT EXISTS llm_call_log (
  call_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  prompt_hash TEXT NOT NULL,
  model TEXT NOT NULL,
  tokens_in INT NOT NULL,
  tokens_out INT NOT NULL,
  latency_ms INT NOT NULL,
  cost_usd NUMERIC(10,6) NOT NULL,
  retrieved_context_ids UUID[],
  caller_service TEXT,
  finding_id UUID REFERENCES findings(finding_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_llm_log_prompt ON llm_call_log(prompt_hash);

CREATE TABLE IF NOT EXISTS retrieval_log (
  retrieval_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  query TEXT NOT NULL,
  jurisdiction TEXT NOT NULL,
  effective_date DATE NOT NULL,
  matched_section_ids UUID[] NOT NULL,
  scores REAL[],
  retrieval_chain JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rule_metrics (
  rule_id TEXT NOT NULL,
  rule_version TEXT NOT NULL,
  jurisdiction TEXT NOT NULL,
  precision REAL,
  recall REAL,
  f1 REAL,
  sample_size INT NOT NULL,
  last_evaluated_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (rule_id, rule_version, jurisdiction)
);
