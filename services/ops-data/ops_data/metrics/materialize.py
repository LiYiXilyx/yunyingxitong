"""Pure metrics from explicit normalized facts; half-open business windows."""
from datetime import datetime
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo
from functools import reduce
from ops_data.ingestion.normalize import timestamp


def exact_add(a, b):
    with localcontext() as ctx:
        ctx.prec = max(a.adjusted(), b.adjusted(), 0) - min(a.as_tuple().exponent, b.as_tuple().exponent, 0) + 3
        return a + b


def materialize_facts(facts, *, data_type, window_start, window_end, timezone, coverage_complete):
    result=dict(version='1',data_type=data_type,window=dict(start=window_start,end=window_end,timezone=timezone),scope={'store_ids':[],'warehouse_ids':[]},quality='insufficient',issues=[],values={})
    try:
        start=timestamp(window_start,timezone); end=timestamp(window_end,timezone); zone=ZoneInfo(timezone)
        if start>=end: raise ValueError('invalid_window')
        latest={}
        for fact in facts:
            for key in result['scope']: result['scope'][key]=sorted(set(result['scope'][key]+fact['scope'][key]))
            key=(fact['entity_type'],fact['source_id']); old=latest.get(key)
            if old and old['source_updated_at']==fact['source_updated_at'] and old!=fact: raise ValueError('source_version_conflict')
            if old is None or fact['source_updated_at']>old['source_updated_at']: latest[key]=fact
        kinds={f['data']['source_kind'] for f in latest.values()}
        if len(kinds)>1: raise ValueError('mixed_source_kinds')
        if not coverage_complete: raise ValueError('incomplete_coverage')
        if data_type=='orders':
            days={}; orders=set(); units=Decimal(0)
            platform_lines={}
            for f in latest.values():
                d=f['data']; key=(d['store_id'],d['platform_order_id'],d['platform_line_id'])
                old=platform_lines.get(key)
                if old and old['source_updated_at']==f['source_updated_at'] and old['data']!=d:
                    raise ValueError('source_version_conflict')
                if old is None or f['source_updated_at']>old['source_updated_at']: platform_lines[key]=f
            for f in platform_lines.values():
                d=f['data']
                if f['entity_type']!='order_line': raise ValueError('wrong_entity_type')
                if d['status']!='paid' or not start<=d['pay_time']<end: continue
                key=(d['store_id'],d['platform_order_id']); day=datetime.fromisoformat(d['pay_time'].replace('Z','+00:00')).astimezone(zone).date().isoformat()
                entry=days.setdefault(day,{'orders':set(),'units':Decimal(0)})
                entry['orders'].add(key); entry['units']=exact_add(entry['units'],Decimal(d['quantity'])); orders.add(key);units=exact_add(units,Decimal(d['quantity']))
            result['values']=dict(paid_platform_orders=str(len(orders)),paid_units=str(units),daily=[dict(date=day,paid_platform_orders=str(len(d['orders'])),paid_units=str(d['units'])) for day,d in sorted(days.items())])
        elif data_type=='refunds':
            selected=[]
            for f in latest.values():
                d=f['data']
                if f['entity_type']!='refund' or d['origin']!='platform_application': raise ValueError('wrong_refund_origin')
                if start<=d['created']<end: selected.append((d['platform_id'],d['refund_id']))
            result['values']={'refund_applications':str(len(set(selected)))}
        elif data_type=='inventory':
            items=[]
            for f in latest.values():
                if f['entity_type']!='inventory': raise ValueError('wrong_entity_type')
                d=f['data'];items.append(dict(warehouse_id=d['warehouse_id'],spec_id=d['spec_id'],available_units=d['available_units']))
            result['values']=dict(available_units=str(reduce(exact_add,(Decimal(i['available_units']) for i in items),Decimal(0))),items=sorted(items,key=lambda i:(i['warehouse_id'],i['spec_id'])))
        else: raise ValueError('unsupported_metrics')
        result['quality']='complete'
    except (KeyError,TypeError,ValueError) as error:
        result['issues']=[str(error) if str(error) in {'invalid_window','source_version_conflict','mixed_source_kinds','incomplete_coverage','wrong_entity_type','wrong_refund_origin','unsupported_metrics'} else 'invalid_fact']
        result['values']={}
    return result
