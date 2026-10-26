"""Strict, opt-in, read-only transport. No secrets, URL or payload are logged."""
from dataclasses import dataclass, field
import http.client
import json
import math
import socket
import time
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode
from .auth import encode_body, sign

HOST = 'openapi.qizhishangke.com'
PREFIX = '/api/openservices/'
ENDPOINTS = frozenset(PREFIX + p for p in (
    'shop/v1/getShopList', 'trade/v1/getSalesTradeList',
    'trade/v1/getSalesTradeOrderList', 'stockSpec/v1/getStockSpecList',
    'stockSpec/v1/getSmtStockSpecList', 'trade/v1/getApiRefundOrder',
))

class WdtError(RuntimeError):
    """Only static safe messages; never include remote error bodies."""

@dataclass(frozen=True, repr=False)
class WdtConfig:
    app_name: str = field(default='', repr=False)
    sid: str = field(default='', repr=False)
    app_key: str = field(default='', repr=False)
    live_enabled: bool = False
    product_confirmed: bool = False
    scopes_confirmed: bool = False
    response_contract_confirmed: bool = False
    timeout: float = 10.0
    max_attempts: int = 3

    def __repr__(self):
        return 'WdtConfig(<redacted>)'


def preflight(config: WdtConfig) -> dict:
    checks = {
        'credentials_present': all(isinstance(x, str) and bool(x.strip()) for x in (config.app_name, config.sid, config.app_key)),
        'live_enabled': config.live_enabled is True,
        'product_confirmed': config.product_confirmed is True,
        'scopes_confirmed': config.scopes_confirmed is True,
        'response_contract_confirmed': config.response_contract_confirmed is True,
    }
    return {**checks, 'live_ready': all(checks.values()), 'network_attempted': False}


def https_transport(endpoint, query, raw_body, timeout):
    """Fixed host, POST only, no redirects and no httpx URL logging."""
    conn = http.client.HTTPSConnection(HOST, timeout=timeout)
    try:
        conn.request('POST', endpoint + '?' + urlencode(query), body=raw_body,
                     headers={'Content-Type': 'application/json; charset=utf-8'})
        response = conn.getresponse()
        status, headers = response.status, dict(response.getheaders())
        # Bound memory and do not parse/error-expose any response on HTTP errors.
        raw = response.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise WdtError('response too large')
        data = json.loads(raw, parse_float=__import__('decimal').Decimal) if status == 200 else None
        return status, headers, data
    finally:
        conn.close()


class WdtClient:
    def __init__(self, config: WdtConfig, limiter=None, *, transport=None, clock=time.time, sleep=time.sleep):
        self.config, self.limiter = config, limiter
        self.transport, self.clock, self.sleep = transport or https_transport, clock, sleep
        if not 1 <= config.max_attempts <= 5 or not 0 < config.timeout <= 60 or not math.isfinite(config.timeout):
            raise ValueError('invalid transport bounds')

    def __repr__(self):
        return 'WdtClient(<redacted>)'

    def request(self, endpoint: str, payload: dict) -> dict:
        if self.config.live_enabled is not True:
            raise WdtError('live disabled')
        if not preflight(self.config)['live_ready']:
            raise WdtError('live prerequisites unconfirmed')
        if endpoint not in ENDPOINTS:
            raise WdtError('endpoint not allowed')
        if self.limiter is None:
            raise WdtError('shared limiter required')
        body = encode_body(payload)
        for attempt in range(self.config.max_attempts):
            try:
                self.limiter.acquire(self.config.sid, endpoint)
            except Exception:
                raise WdtError('shared limiter unavailable') from None
            timestamp = str(int(self.clock()))
            query = {'appName': self.config.app_name, 'sid': self.config.sid, 'timestamp': timestamp,
                     'sign': sign(self.config.app_name, self.config.sid, self.config.app_key, timestamp, body.decode('utf-8'))}
            try:
                status, headers, data = self.transport(endpoint, query, body, self.config.timeout)
            except (TimeoutError, socket.timeout, ConnectionError):
                if attempt + 1 == self.config.max_attempts:
                    raise WdtError('transport retries exhausted') from None
                self.sleep(min(2 ** attempt, 10))
                continue
            except Exception:
                raise WdtError('transport failed') from None
            if status == 429 or status in (500, 502, 503, 504):
                if attempt + 1 == self.config.max_attempts:
                    raise WdtError('HTTP retries exhausted')
                retry_after = next((v for k, v in headers.items() if k.lower() == 'retry-after'), '')
                try:
                    delay = float(retry_after)
                    if not math.isfinite(delay) or delay < 0:
                        raise ValueError
                except (ValueError, TypeError):
                    try:
                        retry_date = parsedate_to_datetime(retry_after)
                        delay = max(0, retry_date.timestamp() - self.clock())
                    except (ValueError, TypeError, OverflowError):
                        delay = min(2 ** attempt, 10)
                if delay > 30:
                    raise WdtError('retry deferred')
                self.sleep(delay)
                continue
            if status != 200:
                raise WdtError('HTTP request rejected')
            # Numeric/string 200 are the sole documented success candidates.
            if not isinstance(data, dict) or type(data.get('code')) not in (str, int) or data['code'] not in (200, '200'):
                raise WdtError('business response rejected')
            if 'data' not in data:
                raise WdtError('response contract mismatch')
            return data
        raise WdtError('transport retries exhausted')
