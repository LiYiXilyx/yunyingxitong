"""Synthetic protocol checks; no ERP network requests or public credentials."""
import json
from decimal import Decimal
from pathlib import Path
import pytest
from ops_data.connectors.wdt.auth import sign, encode_body


def test_synthetic_independent_js_signature():
    f = json.loads((Path(__file__).parent/'fixtures/wdt/signature.json').read_text())
    assert sign(f['app_name'], f['sid'], f['key'], f['timestamp'], f['body']) == f['digest']


def test_unicode_spacing_and_decimal_policy():
    assert encode_body({'文本': '订单', 'amount': '12.30'}) == '{"文本":"订单","amount":"12.30"}'.encode()
    for value in (Decimal('12.30'), float('nan'), float('inf')):
        with pytest.raises(ValueError):
            encode_body({'amount': value})
    assert encode_body({'amount': 0.1}) == b'{"amount":0.1}'


def test_preflight_is_offline_and_secret_safe():
    from ops_data.connectors.wdt.client import WdtConfig, WdtClient, WdtError, preflight
    cfg = WdtConfig(app_name='private-app', sid='private-sid', app_key='private-key')
    assert preflight(cfg)['live_ready'] is False
    assert 'private' not in repr(cfg) + repr(preflight(cfg))
    with pytest.raises(WdtError, match='live disabled'):
        WdtClient(cfg).request('/arbitrary', {})


def test_limiter_requires_explicit_production_database():
    from ops_data.connectors.wdt.rate_limit import PostgresRateLimiter
    with pytest.raises(ValueError):
        PostgresRateLimiter('')


def ready_config(**kw):
    from ops_data.connectors.wdt.client import WdtConfig
    return WdtConfig(app_name='synthetic-app', sid='synthetic-sid', app_key='synthetic-key', live_enabled=True,
                     product_confirmed=True, scopes_confirmed=True, response_contract_confirmed=True, **kw)

class Limiter:
    def __init__(self, clock=None): self.clock = clock; self.calls = []
    def acquire(self, sid, endpoint):
        self.calls.append((sid, endpoint))
        if self.clock is not None: self.clock[0] += 7


def test_retry_resigns_after_limiter_wait_and_sends_identical_body():
    from ops_data.connectors.wdt.client import WdtClient, PREFIX
    now, seen, sleeps = [1792756800], [], []
    def transport(endpoint, query, body, timeout):
        seen.append((dict(query), body))
        return (429, {'Retry-After': '2'}, None) if len(seen) == 1 else (200, {}, {'code': 200, 'data': []})
    limiter = Limiter(now)
    result = WdtClient(ready_config(), limiter, transport=transport, clock=lambda: now[0], sleep=sleeps.append).request(
        PREFIX+'trade/v1/getSalesTradeList', {'文本': '订单', 'amount': '12.30'})
    assert result == {'code': 200, 'data': []}
    assert [x[0]['timestamp'] for x in seen] == ['1792756807', '1792756814']
    assert seen[0][0]['sign'] != seen[1][0]['sign']
    assert seen[0][1] == seen[1][1] == '{"文本":"订单","amount":"12.30"}'.encode()
    assert sleeps == [2] and len(limiter.calls) == 2


@pytest.mark.parametrize('status,data', [(200, {'code': 401, 'msg': 'secret'}), (200, {'data': []}),
                                         (200, {'code': True, 'data': []}), (302, {'code': 200, 'data': []}),
                                         (403, {'code': 200, 'data': []})])
def test_business_errors_and_redirects_do_not_retry_or_expose_body(status, data):
    from ops_data.connectors.wdt.client import WdtClient, WdtError, PREFIX
    seen = []
    def transport(*args): seen.append(1); return status, {}, data
    with pytest.raises(WdtError) as exc:
        WdtClient(ready_config(), Limiter(), transport=transport).request(PREFIX+'trade/v1/getApiRefundOrder', {})
    assert len(seen) == 1
    assert 'secret' not in str(exc.value)


@pytest.mark.parametrize('endpoint', ['https://evil.test/api', '/api/openservices/trade/v1/cancel',
                                     '/api/openservices/trade/v1/getSalesTradeList?redirect=evil',
                                     '//evil.test/api', '/api/openservices/stockSpec/v1/getIncrementalStockSpecList'])
def test_allowlist_rejects_before_transport(endpoint):
    from ops_data.connectors.wdt.client import WdtClient, WdtError
    def forbidden(*a): pytest.fail('network called')
    with pytest.raises(WdtError, match='endpoint not allowed'):
        WdtClient(ready_config(), Limiter(), transport=forbidden).request(endpoint, {})


@pytest.mark.parametrize('failure', ['timeout', 'http'])
def test_transient_failures_are_bounded_and_redacted(failure, caplog):
    from ops_data.connectors.wdt.client import WdtClient, WdtError, PREFIX
    seen, sleeps = [], []
    def transport(*args):
        seen.append(1)
        if failure == 'timeout': raise TimeoutError('secret-key https://private?sid=secret')
        return 503, {'Retry-After': '2'}, {'body': 'secret'}
    with pytest.raises(WdtError) as exc:
        WdtClient(ready_config(max_attempts=3), Limiter(), transport=transport, sleep=sleeps.append).request(
            PREFIX+'shop/v1/getShopList', {})
    assert len(seen) == 3 and len(sleeps) == 2 and max(sleeps) <= 30
    assert 'secret' not in str(exc.value) + caplog.text


def test_payload_must_be_object_before_network():
    from ops_data.connectors.wdt.client import WdtClient, WdtError, PREFIX
    with pytest.raises(ValueError, match='JSON payload must be an object'):
        WdtClient(ready_config(), Limiter(), transport=lambda *a: pytest.fail('network')).request(PREFIX+'shop/v1/getShopList', [])


def test_order_requires_explicit_status_and_frozen_scope():
    from ops_data.connectors.wdt.orders import OrdersConnector
    from ops_data.connectors.wdt.pagination import PageContract
    with pytest.raises(ValueError, match='explicit tradeStatusCode'):
        OrdersConnector(None).fetch(shop_id='two', begin='2026-10-01 00:00:00', end='2026-10-02 00:00:00',
                                    trade_status_code=None, contract=PageContract('nested', 'pagesize'))


def page(n, records, total, size=2, size_key='pageSize', nested=True):
    data = {'currentPage': n, 'data': records, 'total': total, size_key: size}
    return {'code': 200, 'data': data} if nested else {'code': 200, **data}

class PagesClient:
    def __init__(self, pages): self.pages = iter(pages); self.requests = []
    def request(self, endpoint, payload):
        self.requests.append((endpoint, dict(payload)))
        return next(self.pages)


def test_order_and_refund_endpoint_specific_payloads():
    from ops_data.connectors.wdt.orders import OrdersConnector
    from ops_data.connectors.wdt.refunds import RefundsConnector
    from ops_data.connectors.wdt.pagination import PageContract
    client = PagesClient([page(1, [{'id': 1}], 1, 200, 'pagesize', False)])
    result = OrdersConnector(client).fetch(shop_id='s2', begin='2026-10-01 00:00:00', end='2026-10-02 00:00:00',
                                           trade_status_code=0, contract=PageContract('flat', 'pagesize'))
    assert result.scope['tradeStatusCode'] == 0
    assert result.scope['business_timezone'] == 'unconfirmed'
    assert client.requests[0][1] == {'shopId': 's2', 'modifyTimeBegin': '2026-10-01 00:00:00',
                                    'modifyTimeEnd': '2026-10-02 00:00:00', 'tradeStatusCode': 0,
                                    'pageNo': 1, 'pageSize': 200}
    client = PagesClient([page(1, [{'shopName': 'ambiguous'}], 1, 50, 'pagesize')])
    result = RefundsConnector(client).fetch(begin='2026-10-01 00:00:00', end='2026-10-02 00:00:00',
                                           contract=PageContract('nested', 'pagesize'))
    assert 'pageSize' not in client.requests[0][1]
    assert result.scope['store_attribution'] == 'unresolved'
    assert 'shopId' not in result.scope


def test_inventory_requires_explicit_page_start_and_warehouse_scope():
    from ops_data.connectors.wdt.inventory import InventoryConnector
    client = PagesClient([page(0, [{'specId': 1}], 1, 200)])
    result = InventoryConnector(client).fetch(warehouse_no='warehouse-A', page_start=0)
    assert client.requests[0][1] == {'warehouseNo': 'warehouse-A', 'page_no': 0, 'page_size': 200}
    assert result.scope['warehouseNo'] == 'warehouse-A'
    assert result.scope['page_start_verified'] is False
    with pytest.raises(ValueError):
        InventoryConnector(client).fetch(warehouse_no='', page_start=0)


@pytest.mark.parametrize('pages', [
    [page(0, [{'id': 1}], 4), page(1, [{'id': 2}], 5)],
    [page(0, [{'id': 1}, {'id': 2}], 4), page(1, [{'id': 1}, {'id': 2}], 4)],
    [page(0, [], 1)],
    [page(0, [{'id': 1}], 2)],
    [page(2, [{'id': 1}], 1)],
    [{'code': 200, 'data': {'currentPage': 0, 'pageSize': 2, 'data': [], 'total': -1}}],
])
def test_incomplete_pagination_never_returns_success(pages):
    from ops_data.connectors.wdt.pagination import paginate, PageContract
    from ops_data.connectors.wdt.client import WdtError
    with pytest.raises(WdtError):
        paginate(PagesClient(pages), 'offline', {}, scope={}, page_start=0, page_size=2,
                 page_key='page_no', size_key='page_size', contract=PageContract('nested', 'pageSize'))


def test_pagination_page_cap_and_partial_error():
    from ops_data.connectors.wdt.pagination import paginate, PageContract
    from ops_data.connectors.wdt.client import WdtError
    for pages in ([page(0, [1, 2], 4)], [page(0, [1, 2], 4), {'code': 500, 'data': {}}]):
        with pytest.raises(WdtError):
            paginate(PagesClient(pages), 'offline', {}, scope={}, page_start=0, page_size=2,
                     page_key='page_no', size_key='page_size', max_pages=1 if len(pages)==1 else 2,
                     contract=PageContract('nested', 'pageSize'))


def test_profile_missing_code_and_conflicts_are_rejected():
    from ops_data.connectors.wdt.pagination import paginate, PageContract
    from ops_data.connectors.wdt.client import WdtError
    samples = [page(0, [], 0), page(0, [], 0), page(0, [], 0)]
    del samples[0]['code']
    samples[1]['data']['pagesize'] = 2
    samples[2]['total'] = 0
    for sample in samples:
        with pytest.raises(WdtError):
            paginate(PagesClient([sample]), 'offline', {}, scope={}, page_start=0, page_size=2,
                     page_key='page_no', size_key='page_size', contract=PageContract('nested', 'pageSize'))


def test_child_orders_no_pagination_and_bound():
    from ops_data.connectors.wdt.orders import OrdersConnector
    client = PagesClient([{'code': 200, 'data': [{'tradeId': 't1'}]}])
    result = OrdersConnector(client).fetch_items(trade_ids=['t1'])
    assert client.requests[0][1] == {'tradeIds': ['t1']}
    assert result.scope['response_profile_verified'] is False
    for ids in ([], list(range(101)), 't1'):
        with pytest.raises(ValueError):
            OrdersConnector(client).fetch_items(trade_ids=ids)


def test_invalid_windows_and_shop_explicit_base():
    from ops_data.connectors.wdt.shops import ShopsConnector
    from ops_data.connectors.wdt.refunds import RefundsConnector
    from ops_data.connectors.wdt.pagination import PageContract
    with pytest.raises(ValueError):
        RefundsConnector(None).fetch(begin='2026-10-02 00:00:00', end='2026-10-01 00:00:00', contract=PageContract('flat', 'pagesize'))
    with pytest.raises(TypeError):
        ShopsConnector(None).fetch(begin='2026-10-01 00:00:00', end='2026-10-02 00:00:00', status=0, contract=PageContract('nested','pageSize'))


def test_http_date_retry_after():
    from ops_data.connectors.wdt.client import WdtClient, PREFIX
    responses = iter([(429, {'Retry-After': 'Thu, 01 Jan 1970 00:00:10 GMT'}, None),
                      (200, {}, {'code': '200', 'data': []})])
    sleeps = []
    WdtClient(ready_config(), Limiter(), transport=lambda *a: next(responses), clock=lambda: 0,
              sleep=sleeps.append).request(PREFIX+'shop/v1/getShopList', {})
    assert sleeps == [10]


@pytest.mark.parametrize('retry_after', ['31', 'Thu, 01 Jan 1970 00:00:31 GMT'])
def test_retry_after_exceeds_wait_budget_defers_without_retry(retry_after):
    from ops_data.connectors.wdt.client import WdtClient, WdtError, PREFIX
    calls = []
    def transport(*args):
        calls.append(1)
        return 429, {'Retry-After': retry_after}, None
    with pytest.raises(WdtError, match='retry deferred'):
        WdtClient(ready_config(), Limiter(), transport=transport, clock=lambda: 0,
                  sleep=lambda _: pytest.fail('must defer')).request(PREFIX+'shop/v1/getShopList', {})
    assert calls == [1]


def test_confirmation_flags_require_literal_true():
    from dataclasses import replace
    from ops_data.connectors.wdt.client import preflight, WdtClient, WdtError, PREFIX
    for name in ('live_enabled', 'product_confirmed', 'scopes_confirmed', 'response_contract_confirmed'):
        cfg = replace(ready_config(), **{name: 'false'})
        checks = preflight(cfg)
        assert all(type(value) is bool for value in checks.values())
        assert checks['live_ready'] is False
        with pytest.raises(WdtError):
            WdtClient(cfg, Limiter(), transport=lambda *a: pytest.fail('network')).request(PREFIX+'shop/v1/getShopList', {})


def test_inventory_profile_confirmation_is_explicit_literal_true():
    from ops_data.connectors.wdt.inventory import InventoryConnector
    for supplied, expected in ((None, False), ('false', False), (True, True)):
        kwargs = {} if supplied is None else {'response_profile_verified': supplied}
        result = InventoryConnector(PagesClient([page(0, [{'id': 1}], 1, 200)])).fetch(
            warehouse_no='synthetic', page_start=0, **kwargs)
        assert result.scope['response_profile_verified'] is expected


@pytest.mark.parametrize('second', [[{'id': 2}, {'id': 1}], [{'id': 2}, {'id': 3}]])
def test_reordered_and_overlapping_records_reject_false_complete(second):
    from ops_data.connectors.wdt.pagination import paginate, PageContract
    from ops_data.connectors.wdt.client import WdtError
    with pytest.raises(WdtError, match='repeated record'):
        paginate(PagesClient([page(0, [{'id': 1}, {'id': 2}], 4), page(1, second, 4)]),
                 'offline', {}, scope={}, page_start=0, page_size=2, page_key='page_no',
                 size_key='page_size', contract=PageContract('nested', 'pageSize'))


def test_limiter_cumulative_wait_deadline_before_database():
    from ops_data.connectors.wdt.rate_limit import PostgresRateLimiter
    ticks = iter([0, 66])
    limiter = PostgresRateLimiter('synthetic-invalid', monotonic=lambda: next(ticks), max_wait=65)
    with pytest.raises(RuntimeError, match='limiter wait budget exhausted'):
        limiter.acquire('synthetic', '/offline')


def test_https_transport_offline_wire_contract(monkeypatch):
    import ops_data.connectors.wdt.client as module
    from decimal import Decimal
    seen = []
    class Response:
        status = 200
        def getheaders(self): return [('Content-Type', 'application/json')]
        def read(self, limit): return b'{"code":200,"data":{"amount":12.30}}'
    class Connection:
        def __init__(self, host, timeout): seen.append((host, timeout))
        def request(self, method, path, body, headers): seen.append((method, path, body, headers))
        def getresponse(self): return Response()
        def close(self): seen.append('closed')
    monkeypatch.setattr(module.http.client, 'HTTPSConnection', Connection)
    body = b'{"synthetic":true}'
    status, _, data = module.https_transport(module.PREFIX+'shop/v1/getShopList', {'sid':'synthetic'}, body, 3)
    assert seen[0] == (module.HOST, 3)
    assert seen[1][0] == 'POST' and seen[1][2] is body
    assert data['data']['amount'] == Decimal('12.30')
    assert seen[-1] == 'closed'
    Response.status = 302
    assert module.https_transport(module.PREFIX+'shop/v1/getShopList', {}, body, 3) == (302, {'Content-Type': 'application/json'}, None)
    assert seen.count('closed') == 2
    def broken(self): raise RuntimeError('synthetic')
    Connection.getresponse = broken
    with pytest.raises(RuntimeError): module.https_transport(module.PREFIX+'shop/v1/getShopList', {}, body, 3)
    assert seen[-1] == 'closed'


def test_duplicate_records_in_single_page_rejected():
    from ops_data.connectors.wdt.pagination import paginate, PageContract
    from ops_data.connectors.wdt.client import WdtError
    with pytest.raises(WdtError, match='repeated record'):
        paginate(PagesClient([page(0, [{'id': 1}, {'id': 1}], 2)]), 'offline', {}, scope={},
                 page_start=0, page_size=2, page_key='page_no', size_key='page_size',
                 contract=PageContract('nested', 'pageSize'))
