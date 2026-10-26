CREATE TABLE IF NOT EXISTS ops_ingestion_bindings (
 connection_id uuid PRIMARY KEY, binding_version numeric NOT NULL, context jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS ops_ingestion_batches (
 batch_id uuid PRIMARY KEY, connection_id uuid NOT NULL REFERENCES ops_ingestion_bindings ON DELETE CASCADE,
 binding_version numeric NOT NULL, data_type text NOT NULL, source_kind text NOT NULL,
 scope jsonb NOT NULL, spec jsonb NOT NULL, status text NOT NULL DEFAULT 'staging',
 issues jsonb NOT NULL DEFAULT '[]', receipt jsonb, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ops_ingestion_pages (
 batch_id uuid REFERENCES ops_ingestion_batches ON DELETE CASCADE, page_no integer, hash text NOT NULL, records jsonb NOT NULL,
 PRIMARY KEY(batch_id,page_no)
);
CREATE TABLE IF NOT EXISTS ops_ingestion_fact_versions (
 batch_id uuid REFERENCES ops_ingestion_batches ON DELETE CASCADE, entity_type text, source_id text, fact jsonb NOT NULL,
 PRIMARY KEY(batch_id,entity_type,source_id)
);
CREATE TABLE IF NOT EXISTS ops_ingestion_facts (
 connection_id uuid REFERENCES ops_ingestion_bindings ON DELETE CASCADE, data_type text, source_kind text,
 entity_type text, source_id text, scope jsonb NOT NULL, fact jsonb NOT NULL, source_updated_at timestamptz NOT NULL,
 batch_id uuid REFERENCES ops_ingestion_batches ON DELETE CASCADE,
 PRIMARY KEY(connection_id,data_type,source_kind,entity_type,source_id)
);
CREATE TABLE IF NOT EXISTS ops_ingestion_cursors (
 connection_id uuid REFERENCES ops_ingestion_bindings ON DELETE CASCADE, data_type text, source_kind text, scope_key text,
 scope jsonb NOT NULL, watermark timestamptz NOT NULL, batch_id uuid REFERENCES ops_ingestion_batches ON DELETE CASCADE,
 PRIMARY KEY(connection_id,data_type,source_kind,scope_key)
);
CREATE TABLE IF NOT EXISTS ops_ingestion_pending_evaluations (
 batch_id uuid PRIMARY KEY REFERENCES ops_ingestion_batches ON DELETE CASCADE, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ops_ingestion_snapshots (
 batch_id uuid PRIMARY KEY REFERENCES ops_ingestion_batches ON DELETE CASCADE, snapshot jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ops_ingestion_binding_versions (
 connection_id uuid REFERENCES ops_ingestion_bindings ON DELETE CASCADE,
 binding_version numeric NOT NULL, context jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(connection_id,binding_version)
);
INSERT INTO ops_ingestion_binding_versions(connection_id,binding_version,context)
 SELECT connection_id,binding_version,context FROM ops_ingestion_bindings ON CONFLICT DO NOTHING;
