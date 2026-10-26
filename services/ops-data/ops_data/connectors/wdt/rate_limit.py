"""PostgreSQL rolling-window reservations shared by all connector processes."""
import hashlib
import time
import math

class PostgresRateLimiter:
    def __init__(self, database_url: str, *, sleep=time.sleep, monotonic=time.monotonic, max_wait=65):
        if not database_url:
            raise ValueError('shared limiter database required')
        if not isinstance(max_wait, (int, float)) or not math.isfinite(max_wait) or not 0 < max_wait <= 65:
            raise ValueError('invalid limiter wait budget')
        self._database_url, self.sleep = database_url, sleep
        self.monotonic, self.max_wait = monotonic, max_wait

    def __repr__(self):
        return 'PostgresRateLimiter(<redacted>)'

    def acquire(self, sid: str, endpoint: str):
        import psycopg
        # Persist only an opaque key. Advisory transaction lock serializes the
        # check+reservation across independent processes/connections.
        key = hashlib.sha256((sid + '\0' + endpoint).encode()).hexdigest()
        lock = int.from_bytes(bytes.fromhex(key)[:8], 'big', signed=True)
        deadline = self.monotonic() + self.max_wait
        while True:
            if self.monotonic() >= deadline:
                raise RuntimeError('limiter wait budget exhausted')
            with psycopg.connect(self._database_url, connect_timeout=3,
                                  options='-c statement_timeout=3000 -c lock_timeout=1000') as conn:
                with conn.cursor() as cur:
                    cur.execute('SELECT pg_advisory_xact_lock(%s)', (lock,))
                    cur.execute('SELECT clock_timestamp()')
                    now = cur.fetchone()[0]
                    cur.execute('DELETE FROM wdt_rate_reservations WHERE bucket=%s AND reserved_at <= %s - interval \'60 seconds\'', (key, now))
                    cur.execute('SELECT count(*), min(reserved_at) FROM wdt_rate_reservations WHERE bucket=%s', (key,))
                    count, earliest = cur.fetchone()
                    if count < 40:
                        cur.execute('INSERT INTO wdt_rate_reservations(bucket,reserved_at) VALUES (%s,%s)', (key, now))
                        return
                    delay = max(0.01, 60 - (now - earliest).total_seconds())
            if self.monotonic() + delay >= deadline:
                raise RuntimeError('limiter wait budget exhausted')
            self.sleep(delay)
