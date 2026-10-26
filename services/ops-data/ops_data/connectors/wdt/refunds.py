"""Refund pages have fixed size 50 and unresolved store attribution."""
from .client import PREFIX
from .pagination import paginate, validate_window

class RefundsConnector:
    def __init__(self, client): self.client = client
    def fetch(self, *, begin, end, contract, page_start=1, max_pages=1000):
        validate_window(begin, end, 30)
        payload = {'modifiedBegin': begin, 'modifiedEnd': end}
        return paginate(self.client, PREFIX+'trade/v1/getApiRefundOrder', payload,
                        scope={**payload, 'store_attribution': 'unresolved', 'business_timezone': 'unconfirmed',
                               'page_start_verified': False}, page_start=page_start, page_size=50,
                        page_key='pageNo', size_key=None, contract=contract, max_pages=max_pages)
