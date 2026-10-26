CREATE TABLE IF NOT EXISTS ops_ingestion_streams (
 stream_id uuid PRIMARY KEY, connection_id uuid NOT NULL REFERENCES ops_ingestion_bindings(connection_id) ON DELETE CASCADE,
 binding_version bigint NOT NULL, data_type text NOT NULL, source_kind text NOT NULL,
 scope_key text NOT NULL, scope jsonb NOT NULL, timezone text NOT NULL, freshness_seconds integer NOT NULL CHECK(freshness_seconds>0),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(connection_id,binding_version,data_type,source_kind,scope_key)
);
CREATE TABLE IF NOT EXISTS ops_ingestion_jobs (
 job_id uuid PRIMARY KEY, stream_id uuid NOT NULL REFERENCES ops_ingestion_streams ON DELETE CASCADE,
 window_start timestamptz NOT NULL, window_end timestamptz NOT NULL CHECK(window_end>window_start), kind text NOT NULL,
 status text NOT NULL DEFAULT 'queued', generation integer NOT NULL DEFAULT 0, lease_token uuid, lease_until timestamptz, worker text,
 batch_id uuid, error_class text, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(stream_id,window_start,window_end,kind)
);
CREATE TABLE IF NOT EXISTS ops_ingestion_job_attempts (
 job_id uuid NOT NULL REFERENCES ops_ingestion_jobs ON DELETE CASCADE, generation integer NOT NULL, lease_token uuid NOT NULL,
 worker text NOT NULL, started_at timestamptz NOT NULL DEFAULT now(), lease_until timestamptz NOT NULL,
 finished_at timestamptz, status text NOT NULL, error_class text, batch_id uuid,
 PRIMARY KEY(job_id,generation)
);
CREATE INDEX IF NOT EXISTS ops_ingestion_jobs_due ON ops_ingestion_jobs(status,window_end);
