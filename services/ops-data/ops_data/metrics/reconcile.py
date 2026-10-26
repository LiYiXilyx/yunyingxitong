"""Explicit synthetic/manual reconciliation; differences remain unexplained."""
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json


def reconcile_records(source, target, *, key_fields, value_fields, source_window, target_window):
    counts={k:0 for k in ('matched','missing_in_source','missing_in_target','value_mismatch','duplicate_key','missing_field','invalid_value')}
    result={'version':'1','quality':'complete','issues':[],'counts':counts,'differences':[]}
    if source_window != target_window:
        result.update(quality='insufficient',issues=['query_window_mismatch'])
        return result
    if not isinstance(source,list) or not isinstance(target,list) or any(not isinstance(row,dict) for row in source+target):
        result.update(quality='insufficient',issues=['invalid_record_structure'])
        return result
    if not key_fields or not value_fields or len(set(key_fields))!=len(key_fields) or len(set(value_fields))!=len(value_fields):
        result.update(quality='insufficient',issues=['invalid_field_configuration'])
        return result
    def difference(kind,key,fields):
        counts[kind]+=1
        if kind in ('missing_field','invalid_value'):
            result['quality']='insufficient'
        result['differences'].append({'classification':kind,'key_hash':sha256(key.encode()).hexdigest(),'fields':sorted(fields),'unexplained':True})
    def index(rows):
        entries={}
        for row in rows:
            if any(field not in row or row[field] is None for field in key_fields):
                difference('missing_field','missing-key',[f for f in key_fields if f not in row or row[f] is None]);continue
            key=json.dumps([row[f] for f in key_fields],sort_keys=True,separators=(',',':'),ensure_ascii=False)
            entries.setdefault(key,[]).append(row)
        return entries
    left,right=index(source),index(target)
    for key in sorted(set(left)|set(right)):
        a,b=left.get(key,[]),right.get(key,[])
        if len(a)>1 or len(b)>1:
            difference('duplicate_key',key,key_fields);continue
        if not a: difference('missing_in_source',key,[]);continue
        if not b: difference('missing_in_target',key,[]);continue
        missing=[f for f in value_fields if f not in a[0] or f not in b[0] or a[0][f] is None or b[0][f] is None]
        if missing: difference('missing_field',key,missing);continue
        mismatch=[];invalid=[]
        for field in value_fields:
            x,y=a[0][field],b[0][field]
            if x is None or y is None:
                if x is not y: mismatch.append(field)
                continue
            try:
                if isinstance(x,(bool,float)) or isinstance(y,(bool,float)): raise ValueError()
                dx,dy=Decimal(str(x)),Decimal(str(y))
                if not dx.is_finite() or not dy.is_finite(): raise ValueError()
                if dx!=dy: mismatch.append(field)
            except (InvalidOperation,ValueError): invalid.append(field)
        if invalid: difference('invalid_value',key,invalid)
        elif mismatch: difference('value_mismatch',key,mismatch)
        else: counts['matched']+=1
    return result
