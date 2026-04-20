-- Registry of extractor and rule versions.

CREATE TABLE IF NOT EXISTS extractor_versions (
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  schema_uri TEXT,
  prompt_hash TEXT,
  model TEXT,
  deployed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deprecated_at TIMESTAMPTZ,
  PRIMARY KEY (name, version)
);

CREATE TABLE IF NOT EXISTS rule_versions (
  rule_id TEXT NOT NULL,
  version TEXT NOT NULL,
  discipline TEXT NOT NULL,
  code_sections TEXT[] NOT NULL,
  severity_default TEXT NOT NULL,
  requires_licensed_review BOOLEAN NOT NULL DEFAULT false,
  fixture_test_path TEXT,
  deployed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deprecated_at TIMESTAMPTZ,
  PRIMARY KEY (rule_id, version)
);

CREATE TABLE IF NOT EXISTS prompts (
  prompt_id TEXT NOT NULL,
  version TEXT NOT NULL,
  body TEXT NOT NULL,
  model TEXT NOT NULL,
  shadow BOOLEAN NOT NULL DEFAULT false,
  is_default BOOLEAN NOT NULL DEFAULT false,
  deployed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deprecated_at TIMESTAMPTZ,
  PRIMARY KEY (prompt_id, version)
);
