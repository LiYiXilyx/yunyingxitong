import os
import sys
from .repository import IngestionRepository


def main():
    try:
        IngestionRepository(os.environ['OPS_DATABASE_URL']).migrate()
    except Exception:
        print('Ingestion migration failed', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
