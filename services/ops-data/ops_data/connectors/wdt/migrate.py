"""Explicit opt-in migration of the ops-data limiter table only."""
import os
from pathlib import Path
import sys


def main():
    import psycopg
    database_url = os.environ.get('OPS_DATABASE_URL', '')
    if not database_url.strip():
        print('WDT limiter migration failed', file=sys.stderr)
        return 1
    try:
        sql = (Path(__file__).parent / 'migrations' / '001_rate_reservations.sql').read_text()
        with psycopg.connect(database_url, connect_timeout=3, options='-c statement_timeout=3000 -c lock_timeout=1000') as conn:
            conn.execute(sql)
    except Exception:
        print('WDT limiter migration failed', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
