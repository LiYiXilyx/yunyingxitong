"""Explicit, fail-closed source normalization. No ERP calls or inferred mappings."""
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

@dataclass(frozen=True)
class NormalizationResult:
    facts: list[dict]
    issues: list[str]


def timestamp(value, zone):
    if not isinstance(value, str) or not value:
        raise ValueError('missing_time')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        tz = ZoneInfo(zone)
        candidates = {dt.replace(tzinfo=tz, fold=f).astimezone(timezone.utc) for f in (0, 1)
                      if dt.replace(tzinfo=tz, fold=f).astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) == dt}
        if len(candidates) != 1:
            raise ValueError('ambiguous_or_nonexistent_time')
        dt = candidates.pop()
    return dt.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def decimal(value, positive=False):
    if isinstance(value, (float, bool)) or value is None:
        raise ValueError('invalid_decimal')
    number = Decimal(str(value))
    if not number.is_finite() or (positive and number <= 0):
        raise ValueError('invalid_decimal')
    return str(number)


def identity(value):
    if not isinstance(value, (str, int)) or isinstance(value, bool) or str(value) == '':
        raise ValueError('missing_identity')
    return str(value)


def normalize_records(data_type, records, context):
    facts, issues = {}, []
    try:
        if context.get('source_kind') not in ('synthetic', 'wdt_api', 'manual_import'):
            raise ValueError('unknown_source_kind')
        if context.get('mapping_confirmed') is not True:
            raise ValueError('mapping_unconfirmed')
        for field in ('connection_id', 'mapping_version'):
            identity(context.get(field))
        v = context.get('binding_version')
        if not isinstance(v,str) or not v.isdecimal() or int(v)<=0:
            raise ValueError('invalid_binding_version')
        zone = context['source_timezone']; ZoneInfo(zone)
        allowed = context['allowed_scope']
        def scope(store=None, warehouse=None):
            result = {'store_ids': [store] if store else [], 'warehouse_ids': [warehouse] if warehouse else []}
            if any(not set(result[k]).issubset(allowed[k]) for k in result):
                raise ValueError('scope_not_allowed')
            return result
        def add(entity, sid, updated, sc, data):
            data['source_kind'] = context['source_kind']
            fact = dict(entity_type=entity,source_id=sid,source_updated_at=timestamp(updated,zone),scope=sc,data=data)
            key=(entity,sid)
            old=facts.get(key)
            if old and old['source_updated_at']==fact['source_updated_at'] and old!=fact:
                raise ValueError('source_version_conflict')
            if not old or old['source_updated_at']<fact['source_updated_at']:
                facts[key]=fact
        for row in records:
            if data_type == 'orders':
                master=row['master']; shop=identity(master['shopId']); store=context['store_bindings'][shop]
                identity(master['tradeId'])
                status=context['order_status_map'][str(master['tradeStatusCode'])]
                if status not in ('paid','void','pending'): raise ValueError('unknown_status')
                if not row['lines']: raise ValueError('missing_order_lines')
                for line in row['lines']:
                    oid=identity(line['orderId']); tid=identity(line['srcTid']); src_oid=identity(line['srcOid'])
                    add('order_line',oid,master['modified'],scope(store),dict(store_id=store,platform_order_id=tid,platform_line_id=src_oid,spec_id=identity(line['apiSpecNo']),quantity=decimal(line['num'],True),status=status,pay_time=timestamp(master['payTime'],zone)))
            elif data_type == 'inventory':
                wh=context['warehouse_bindings'][identity(row['warehouseNo'])]; spec=identity(row['specId'])
                add('inventory',json.dumps([wh,spec],separators=(',',':')),row['modified'],scope(warehouse=wh),dict(warehouse_id=wh,spec_id=spec,spec_no=identity(row['specNo']),available_units=decimal(row['availableNum'])))
            elif data_type == 'refunds':
                platform=identity(row['platformId']); tid=identity(row['tid']); rid=identity(row['refundNo'])
                store=context['refund_order_bindings'][platform+':'+tid]
                if row.get('shopId') is not None and context['store_bindings'][str(row['shopId'])]!=store: raise ValueError('refund_store_conflict')
                add('refund',json.dumps([platform,rid],separators=(',',':')),row['modified'],scope(store),dict(store_id=store,platform_id=platform,platform_order_id=tid,refund_id=rid,created=timestamp(row['created'],zone),status=identity(row['status']),origin='platform_application'))
            elif data_type == 'catalog':
                if context['source_kind']=='wdt_api' or context.get('catalog_mapping_confirmed') is not True: raise ValueError('catalog_mapping_unconfirmed')
                spec=identity(row['specId']); components=[]
                for part in row.get('components',[]):
                    if part.get('connection_id',context['connection_id'])!=context['connection_id']: raise ValueError('cross_connection_bom')
                    components.append(dict(spec_id=identity(part['specId']),quantity=decimal(part['quantity'],True)))
                if len({p['spec_id'] for p in components})!=len(components): raise ValueError('ambiguous_bom')
                add('catalog',spec,row['modified'],scope(),dict(spec_id=spec,components=components))
            else: raise ValueError('unknown_data_type')
        if data_type=='catalog':
            graph={f['data']['spec_id']:[p['spec_id'] for p in f['data']['components']] for f in facts.values()}
            def visit(node, path):
                if node in path: raise ValueError('cyclic_bom')
                if node not in graph: raise ValueError('missing_bom_component')
                for child in graph[node]: visit(child,path|{node})
            for node in graph: visit(node,set())
    except (KeyError, TypeError, AttributeError, ValueError, InvalidOperation) as error:
        # Never echo raw identifiers, statuses, payloads, or customer values.
        code=str(error) if isinstance(error,ValueError) and str(error) in {'mapping_unconfirmed','unknown_source_kind','invalid_binding_version','scope_not_allowed','source_version_conflict','unknown_status','missing_order_lines','refund_store_conflict','catalog_mapping_unconfirmed','cross_connection_bom','ambiguous_bom','cyclic_bom','missing_bom_component','missing_identity','invalid_decimal','missing_time','ambiguous_or_nonexistent_time','unknown_data_type'} else 'invalid_or_unmapped_record'
        issues.append(code)
    return NormalizationResult(list(facts.values()) if not issues else [],issues)
