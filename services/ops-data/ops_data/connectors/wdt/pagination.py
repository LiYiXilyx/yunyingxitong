"""Conservative raw-page collection; response layouts remain explicit candidates."""
from copy import deepcopy
from dataclasses import dataclass, field
import json
from .client import WdtError

@dataclass(frozen=True)
class PageContract:
    layout: str
    size_field: str
    verified: bool = False

ResponseProfile = PageContract

@dataclass(repr=False)
class RawResult:
    pages: list = field(repr=False)
    scope: dict = field(repr=False)
    def __repr__(self):
        return 'RawResult(<redacted>)'


def paginate(client, endpoint, payload, *, scope, page_start, page_size,
             page_key, size_key, contract, max_pages=1000):
    if type(page_start) is not int or page_start < 0 or type(page_size) is not int or not 1 <= page_size <= 200:
        raise ValueError('invalid pagination bounds')
    if type(max_pages) is not int or not 1 <= max_pages <= 10000:
        raise ValueError('invalid page cap')
    if contract.layout not in ('flat', 'nested') or contract.size_field not in ('pageSize', 'pagesize'):
        raise ValueError('explicit response profile required')
    frozen = deepcopy(payload)
    pages, seen, total, count = [], set(), None, 0
    seen_records = set()
    for number in range(page_start, page_start + max_pages):
        request = {**deepcopy(frozen), page_key: number}
        if size_key is not None:
            request[size_key] = page_size
        raw = client.request(endpoint, request)
        if not isinstance(raw, dict) or type(raw.get('code')) not in (str, int) or raw['code'] not in (200, '200'):
            raise WdtError('business response rejected')
        data = raw.get('data') if contract.layout == 'nested' else raw
        if not isinstance(data, dict):
            raise WdtError('response profile mismatch')
        # Ambiguous alternative outer/size fields must never silently win.
        if contract.layout == 'nested' and any(k in raw for k in ('currentPage', 'total', 'pageSize', 'pagesize')):
            raise WdtError('conflicting pagination fields')
        alternative = 'pagesize' if contract.size_field == 'pageSize' else 'pageSize'
        if alternative in data:
            raise WdtError('conflicting page size fields')
        records, current, size, reported = (data.get(k) for k in ('data', 'currentPage', contract.size_field, 'total'))
        if not isinstance(records, list) or any(type(v) is not int for v in (current, size, reported)):
            raise WdtError('invalid pagination metadata')
        if current != number or size != page_size or reported < 0 or len(records) > size:
            raise WdtError('inconsistent pagination metadata')
        if 'empty' in data and (type(data['empty']) is not bool or data['empty'] != (len(records) == 0)):
            raise WdtError('conflicting empty flag')
        if total is None:
            total = reported
        if reported != total:
            raise WdtError('total changed during collection')
        fingerprint = json.dumps(records, sort_keys=True, ensure_ascii=False, default=str)
        if records and fingerprint in seen:
            raise WdtError('repeated page')
        record_fingerprints = [json.dumps(record, sort_keys=True, ensure_ascii=False, default=str) for record in records]
        if len(record_fingerprints) != len(set(record_fingerprints)) or any(value in seen_records for value in record_fingerprints):
            raise WdtError('repeated record across pages')
        seen_records.update(record_fingerprints)
        seen.add(fingerprint)
        pages.append(deepcopy(raw))
        count += len(records)
        if count > total:
            raise WdtError('record count exceeds total')
        if count == total:
            return RawResult(pages, {**deepcopy(scope), 'response_profile_verified': contract.verified is True,
                                     'response_profile': contract.layout, 'collection_complete': True, 'completeness_basis': 'candidate_profile_and_count_only'})
        if len(records) < size:
            raise WdtError('short page before total')
    raise WdtError('page cap exceeded')


def validate_window(begin, end, days):
    from datetime import datetime
    try:
        start, stop = (datetime.strptime(v, '%Y-%m-%d %H:%M:%S') for v in (begin, end))
    except (ValueError, TypeError):
        raise ValueError('explicit business time window required') from None
    if not 0 <= (stop-start).total_seconds() <= days * 86400:
        raise ValueError('invalid business time window')
