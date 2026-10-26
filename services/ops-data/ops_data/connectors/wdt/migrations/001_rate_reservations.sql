-- Apply only to the ops-data service database (never NocoBase/ERP).
CREATE TABLE IF NOT EXISTS wdt_rate_reservations (
    bucket text NOT NULL,
    reserved_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS wdt_rate_reservations_bucket_time
    ON wdt_rate_reservations (bucket, reserved_at);
