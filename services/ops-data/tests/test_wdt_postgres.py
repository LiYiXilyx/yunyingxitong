"""Requires dedicated OPS_TEST_DATABASE_URL; independent real PostgreSQL connections."""
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import uuid
import psycopg
from ops_data.connectors.wdt.rate_limit import PostgresRateLimiter


def test_postgres_independent_connections_recheck_expired_reservations():
    database = os.environ.get('OPS_TEST_DATABASE_URL')
    assert database, 'OPS_TEST_DATABASE_URL required for shared limiter verification'
    sid, endpoint = 'synthetic-'+uuid.uuid4().hex, '/synthetic-read-only'
    bucket = hashlib.sha256((sid+'\0'+endpoint).encode()).hexdigest()
    migration = Path(__file__).parents[1]/'ops_data/connectors/wdt/migrations/001_rate_reservations.sql'
    with psycopg.connect(database) as conn:
        conn.execute(migration.read_text())
        # Simulate workers waking after their old reservations expired.
        conn.execute("INSERT INTO wdt_rate_reservations SELECT %s, clock_timestamp()-interval '61 seconds' FROM generate_series(1,45)", (bucket,))
    class WouldWait(Exception): pass
    def blocked_sleep(delay):
        assert 0 < delay <= 60
        raise WouldWait
    def worker(_):
        try:
            PostgresRateLimiter(database, sleep=blocked_sleep).acquire(sid, endpoint)
            return 'admitted'
        except WouldWait:
            return 'blocked'
    try:
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(worker, range(45)))
        assert results.count('admitted') == 40
        assert results.count('blocked') == 5
        # A different SID or URI has its own bucket.
        PostgresRateLimiter(database, sleep=blocked_sleep).acquire(sid, endpoint+'-other')
        PostgresRateLimiter(database, sleep=blocked_sleep).acquire(sid+'-other', endpoint)
        with psycopg.connect(database) as conn:
            assert conn.execute('SELECT count(*) FROM wdt_rate_reservations WHERE bucket=%s', (bucket,)).fetchone()[0] == 40
    finally:
        buckets = [hashlib.sha256((s+'\0'+e).encode()).hexdigest() for s,e in
                   ((sid,endpoint),(sid,endpoint+'-other'),(sid+'-other',endpoint))]
        with psycopg.connect(database) as conn:
            conn.execute('DELETE FROM wdt_rate_reservations WHERE bucket=ANY(%s)', (buckets,))


def test_migrate_missing_environment_fails_safely(monkeypatch, capsys):
    from ops_data.connectors.wdt.migrate import main
    monkeypatch.delenv('OPS_DATABASE_URL', raising=False)
    assert main() == 1
    assert capsys.readouterr().err == 'WDT limiter migration failed\n'


def test_migrate_is_idempotent_and_preserves_existing_records(monkeypatch):
    from ops_data.connectors.wdt.migrate import main
    database = os.environ.get('OPS_TEST_DATABASE_URL')
    assert database, 'OPS_TEST_DATABASE_URL required for migration verification'
    monkeypatch.setenv('OPS_DATABASE_URL', database)
    assert main() == 0
    bucket = 'migration-synthetic-'+uuid.uuid4().hex
    with psycopg.connect(database) as conn:
        conn.execute('INSERT INTO wdt_rate_reservations VALUES (%s,clock_timestamp())', (bucket,))
    try:
        assert main() == 0
        with psycopg.connect(database) as conn:
            assert conn.execute('SELECT count(*) FROM wdt_rate_reservations WHERE bucket=%s', (bucket,)).fetchone()[0] == 1
    finally:
        with psycopg.connect(database) as conn:
            conn.execute('DELETE FROM wdt_rate_reservations WHERE bucket=%s', (bucket,))


def test_migrate_connection_failure_is_redacted(monkeypatch, capsys):
    from ops_data.connectors.wdt.migrate import main
    monkeypatch.setenv('OPS_DATABASE_URL', 'synthetic-private-dsn')
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic-secret password body query')
    monkeypatch.setattr(psycopg, 'connect', fail)
    assert main() == 1
    output = capsys.readouterr()
    assert output.err == 'WDT limiter migration failed\n'
    assert not output.out


def test_postgres_lock_contention_is_bounded_and_no_erp_request():
    import time
    from ops_data.connectors.wdt.client import WdtClient, WdtError, PREFIX
    from test_wdt import ready_config
    database = os.environ.get('OPS_TEST_DATABASE_URL')
    assert database, 'OPS_TEST_DATABASE_URL required for lock timeout verification'
    sid = 'lock-synthetic-'+uuid.uuid4().hex
    endpoint = PREFIX+'shop/v1/getShopList'
    key = hashlib.sha256((sid+'\0'+endpoint).encode()).hexdigest()
    lock = int.from_bytes(bytes.fromhex(key)[:8], 'big', signed=True)
    from dataclasses import replace
    with psycopg.connect(database) as holder:
        holder.execute('SELECT pg_advisory_xact_lock(%s)', (lock,))
        started = time.monotonic()
        with __import__('pytest').raises(WdtError, match='shared limiter unavailable'):
            WdtClient(replace(ready_config(), sid=sid), PostgresRateLimiter(database),
                      transport=lambda *a: __import__('pytest').fail('ERP transport called')).request(endpoint, {})
        assert time.monotonic()-started < 5


def test_migration_has_bounded_database_options(monkeypatch):
    from ops_data.connectors.wdt.migrate import main
    monkeypatch.setenv('OPS_DATABASE_URL', 'synthetic')
    seen = []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql): pass
    def connect(*args, **kwargs):
        seen.append(kwargs)
        return Connection()
    monkeypatch.setattr(psycopg, 'connect', connect)
    assert main() == 0
    assert seen[0]['connect_timeout'] == 3
    assert 'statement_timeout=3000' in seen[0]['options']
    assert 'lock_timeout=1000' in seen[0]['options']
