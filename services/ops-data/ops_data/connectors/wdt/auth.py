"""Java/Postman key+value signing; caller reuses the exact UTF-8 body bytes."""
import hashlib
import json


def encode_body(payload: dict) -> bytes:
    """Compact UTF-8, preserve insertion order; Decimal must be supplied as text.

    Floats retain Python JSON's finite shortest representation; use strings for
    monetary precision/trailing zeros. Never serialize again after signing.
    """
    if not isinstance(payload, dict):
        raise ValueError('JSON payload must be an object')
    try:
        return json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError):
        raise ValueError('invalid JSON payload') from None


def sign(app_name: str, sid: str, key: str, timestamp: str, raw_body: str) -> str:
    values = {'appName': app_name, 'body': raw_body, 'sid': sid, 'timestamp': timestamp}
    source = key + ''.join(k + values[k] for k in sorted(values)) + key
    return hashlib.md5(source.encode('utf-8'), usedforsecurity=False).hexdigest()
