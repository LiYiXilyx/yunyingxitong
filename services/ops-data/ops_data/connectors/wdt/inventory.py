"""Ordinary inventory is warehouse scoped, independent of store count."""
from .client import PREFIX
from .pagination import PageContract, paginate

class InventoryConnector:
    def __init__(self, client): self.client = client
    def fetch(self, *, warehouse_no, page_start, page_start_verified=False, response_profile_verified=False, max_pages=1000):
        if not isinstance(warehouse_no, str) or not warehouse_no.strip():
            raise ValueError('explicit warehouse scope required')
        return paginate(self.client, PREFIX+'stockSpec/v1/getStockSpecList', {'warehouseNo': warehouse_no},
                        scope={'warehouseNo': warehouse_no, 'page_start_verified': page_start_verified is True,
                               'documented_profile_source': 'official_stock_example'},
                        page_start=page_start, page_size=200, page_key='page_no', size_key='page_size',
                        contract=PageContract('nested', 'pageSize', response_profile_verified is True), max_pages=max_pages)
