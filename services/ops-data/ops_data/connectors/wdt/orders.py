"""Order candidate profiles require caller selection; no default shipped filter."""
from .client import PREFIX
from .pagination import paginate, RawResult, validate_window

class OrdersConnector:
    def __init__(self, client): self.client = client
    def fetch(self, *, shop_id, begin, end, trade_status_code, contract, page_start=1, max_pages=1000):
        if type(trade_status_code) is not int or trade_status_code not in (0, 1, 2, 3, 4, 7, 8):
            raise ValueError('explicit tradeStatusCode required')
        if not isinstance(shop_id, str) or not shop_id.strip():
            raise ValueError('explicit shop scope required')
        validate_window(begin, end, 90)
        payload = dict(shopId=shop_id, modifyTimeBegin=begin, modifyTimeEnd=end, tradeStatusCode=trade_status_code)
        return paginate(self.client, PREFIX+'trade/v1/getSalesTradeList', payload,
                        scope={**payload, 'business_timezone': 'unconfirmed', 'page_start_verified': False},
                        page_start=page_start, page_size=200, page_key='pageNo', size_key='pageSize',
                        contract=contract, max_pages=max_pages)
    def fetch_items(self, *, trade_ids, response_profile_verified=False):
        from .client import WdtError
        if not isinstance(trade_ids, list) or not 1 <= len(trade_ids) <= 100 or any(type(x) not in (str, int) or not str(x).strip() for x in trade_ids):
            raise ValueError('tradeIds must contain 1 to 100 identifiers')
        raw = self.client.request(PREFIX+'trade/v1/getSalesTradeOrderList', {'tradeIds': list(trade_ids)})
        if not isinstance(raw, dict) or type(raw.get('code')) not in (str, int) or raw['code'] not in (200, '200') or not isinstance(raw.get('data'), list):
            raise WdtError('child order response profile mismatch')
        return RawResult([raw], {'tradeIds': list(trade_ids), 'response_profile_verified': response_profile_verified is True})
