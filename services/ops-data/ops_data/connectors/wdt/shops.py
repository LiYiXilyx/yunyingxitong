"""Shop response and starting page require explicit protocol choices."""
from .client import PREFIX
from .pagination import paginate, validate_window

class ShopsConnector:
    def __init__(self, client): self.client = client
    def fetch(self, *, begin, end, status, page_start, contract, page_start_verified=False, max_pages=1000):
        validate_window(begin, end, 36500)
        if type(status) is not int or status not in (0, 1):
            raise ValueError('explicit shop time status required')
        payload = {'start_time': begin, 'end_time': end, 'status': status}
        return paginate(self.client, PREFIX+'shop/v1/getShopList', payload,
                        scope={**payload, 'business_timezone': 'unconfirmed', 'page_start_verified': page_start_verified is True},
                        page_start=page_start, page_size=200, page_key='page_no', size_key='page_size',
                        contract=contract, max_pages=max_pages)
