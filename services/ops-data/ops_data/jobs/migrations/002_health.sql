CREATE TABLE IF NOT EXISTS ops_ingestion_health (
 stream_id uuid PRIMARY KEY REFERENCES ops_ingestion_streams ON DELETE CASCADE,
 revision bigint NOT NULL, fingerprint text NOT NULL, command jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ops_ingestion_health_outbox (
 command_id uuid PRIMARY KEY, stream_id uuid NOT NULL REFERENCES ops_ingestion_streams ON DELETE CASCADE,
 command jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), acknowledged_at timestamptz,
 receipt_id uuid, attempts integer NOT NULL DEFAULT 0, last_error text
);
