#!/usr/bin/env python3
"""Inspect a local WDT configuration without executing it or sending requests."""
import argparse
import json
import os
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[1]
KEYS = ('WDT_APP_NAME', 'WDT_SID', 'WDT_SIGNING_KEY', 'WDT_BASE_URL')
ALLOWED_URLS = {'https://openapi.qizhishangke.com', 'https://openapi.qizhishangke.com/'}


def inspect_config(path: Path) -> dict:
    report = {'status': 'needs_user', 'live_verified': False,
              'network_request_sent': False, 'missing_keys': list(KEYS), 'issues': []}
    descriptor = None
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            report['issues'].append('private_regular_file_required')
            return report
        # O_NOFOLLOW also protects the final component if replaced after lstat.
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            report['issues'].append('private_regular_file_required')
            return report
        if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
            report['issues'].append('private_file_permissions_required')
            return report
        if info.st_size > 65536:
            report['issues'].append('invalid_config_format')
            return report
        with os.fdopen(descriptor, encoding='utf-8') as stream:
            descriptor = None
            source = stream.read(65537)
        if len(source) > 65536:
            report['issues'].append('invalid_config_format')
            return report
    except FileNotFoundError:
        report['issues'].append('private_file_missing')
        return report
    except (OSError, UnicodeError):
        report['issues'].append('private_file_unreadable')
        return report
    finally:
        if descriptor is not None:
            os.close(descriptor)

    values = {}
    for line in source.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if not separator or key not in KEYS or key in values:
            report['issues'].append('invalid_config_format')
            break
        # Literal values only. No shell evaluation, interpolation or inline comments.
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                report['issues'].append('invalid_config_format')
                break
            value = value[1:-1]
        values[key] = value
    report['missing_keys'] = [key for key in KEYS if not values.get(key, '').strip()]
    if values.get('WDT_BASE_URL') and values['WDT_BASE_URL'] not in ALLOWED_URLS:
        report['issues'].append('base_url_not_allowed')
    if not report['issues'] and not report['missing_keys']:
        report['status'] = 'configured_not_verified'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, default=ROOT / '.local/secrets/wdt.env')
    report = inspect_config(parser.parse_args().file)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'configured_not_verified' else 2


if __name__ == '__main__':
    raise SystemExit(main())
