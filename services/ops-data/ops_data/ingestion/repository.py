"""PostgreSQL batch transaction boundary. Errors contain static classes only."""
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=lambda v: str(v) if isinstance(v, Decimal) else _invalid(), allow_nan=False)


def _invalid():
    raise ValueError('unsupported_value')


def clean(value):
    result = json.loads(canonical(value))
    def check(v):
        if isinstance(v, dict):
            for k, x in v.items():
                if any(word in k.lower() for word in ('password', 'secret', 'token', 'authorization', 'appkey', 'app_key')):
                    raise ValueError('credentials_forbidden')
                check(x)
        elif isinstance(v, list):
            for x in v: check(x)
    check(result)
    return result


def scope_value(scope):
    if not isinstance(scope, dict) or set(scope) != {'store_ids','warehouse_ids'}:
        raise ValueError('scope_invalid')
    return {k: sorted({str(UUID(x)) for x in scope[k]}) for k in ('store_ids','warehouse_ids')}


def contained(scope, allowed):
    return all(set(scope[k]) <= set(allowed[k]) for k in ('store_ids','warehouse_ids'))


def timestamp(value):
    dt = datetime.fromisoformat(value.replace('Z','+00:00'))
    if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
        raise ValueError('utc_required')
    return dt


class IngestionRepository:
    def __init__(self, database_url):
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, connect_timeout=5, options='-c statement_timeout=15000 -c lock_timeout=10000', row_factory=dict_row)

    def migrate(self):
        with self._connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(51005)')
            c.execute((Path(__file__).parent/'migrations/001_ingestion.sql').read_text())

    def register_binding(self, connection_id, binding_version, context):
        cid = str(UUID(connection_id)); ctx = clean(context)
        if not str(binding_version).isdigit() or int(binding_version)<1: raise ValueError('binding_version_invalid')
        if ctx.get('connection_id') != cid or ctx.get('binding_version') != str(binding_version): raise ValueError('binding_context_mismatch')
        scope_value(ctx['allowed_scope'])
        with self._connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(cid,))
            old=c.execute('SELECT * FROM ops_ingestion_bindings WHERE connection_id=%s FOR UPDATE',(cid,)).fetchone()
            if old and (old['binding_version']>int(binding_version) or (old['binding_version']==int(binding_version) and old['context']!=ctx)):
                raise ValueError('binding_conflict')
            c.execute('INSERT INTO ops_ingestion_bindings VALUES (%s,%s,%s) ON CONFLICT(connection_id) DO UPDATE SET binding_version=excluded.binding_version,context=excluded.context',(cid,binding_version,Jsonb(ctx)))
            c.execute('INSERT INTO ops_ingestion_binding_versions(connection_id,binding_version,context) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',(cid,binding_version,Jsonb(ctx)))

    def begin_batch(self, spec):
        raw=dict(spec)
        lease=raw.pop('lease_token',None)
        s=clean(raw)
        if ('job_id' in s)!=(lease is not None): raise ValueError('job_reference_invalid')
        if lease is not None:
            s['job_id']=str(UUID(s['job_id'])); s['lease_token']=str(UUID(lease))
        if s['source_kind']=='wdt_api' and lease is None: raise ValueError('job_required')
        bid=str(UUID(s['batch_id'])); cid=str(UUID(s['connection_id']))
        scope=scope_value(s['scope']); s['scope']=scope
        if not any(scope.values()) or s['source_kind'] not in ('synthetic','wdt_api','manual_import') or s['data_type'] not in ('orders','refunds','inventory','catalog'): raise ValueError('batch_invalid')
        if timestamp(s['window_start'])>=timestamp(s['window_end']): raise ValueError('window_invalid')
        for key in ('expected_pages','expected_count','page_start'):
            if type(s[key]) is not int or s[key]<0: raise ValueError('pagination_invalid')
        if s['expected_pages']<1 or type(s['coverage_complete']) is not bool or s['coverage_kind'] not in ('full','incremental'): raise ValueError('coverage_invalid')
        with self._connect() as c:
            binding=c.execute('SELECT * FROM ops_ingestion_bindings WHERE connection_id=%s FOR UPDATE',(cid,)).fetchone()
            if not binding or binding['binding_version']!=int(s['binding_version']) or binding['context']!=s['context'] or s['context']['source_kind']!=s['source_kind'] or not contained(scope,scope_value(binding['context']['allowed_scope'])): raise ValueError('binding_mismatch')
            old=c.execute('SELECT spec FROM ops_ingestion_batches WHERE batch_id=%s',(bid,)).fetchone()
            if old:
                if old['spec']!=s: raise ValueError('batch_conflict')
                return bid
            c.execute('INSERT INTO ops_ingestion_batches(batch_id,connection_id,binding_version,data_type,source_kind,scope,spec) VALUES (%s,%s,%s,%s,%s,%s,%s)',(bid,cid,s['binding_version'],s['data_type'],s['source_kind'],Jsonb(scope),Jsonb(s)))
        return bid

    def stage_page(self,batch_id,page_no,records):
        rows=clean(records)
        if not isinstance(rows,list): raise ValueError('records_invalid')
        digest=hashlib.sha256(canonical(rows).encode()).hexdigest()
        with self._connect() as c:
            b=c.execute('SELECT * FROM ops_ingestion_batches WHERE batch_id=%s FOR UPDATE',(batch_id,)).fetchone()
            if not b: raise ValueError('batch_missing')
            s=b['spec']
            if type(page_no) is not int or not s['page_start']<=page_no<s['page_start']+s['expected_pages']: raise ValueError('page_range')
            old=c.execute('SELECT hash FROM ops_ingestion_pages WHERE batch_id=%s AND page_no=%s',(batch_id,page_no)).fetchone()
            if old:
                if old['hash']!=digest: raise ValueError('page_conflict')
                return
            if b['status']=='succeeded': raise ValueError('batch_immutable')
            c.execute('INSERT INTO ops_ingestion_pages VALUES (%s,%s,%s,%s)',(batch_id,page_no,digest,Jsonb(rows)))

    def commit_batch(self,batch_id):
        from .normalize import normalize_records
        with self._connect() as c:
            # Uniform binding-before-batch lock ordering serializes object versions.
            first=c.execute('SELECT connection_id,spec,status,receipt FROM ops_ingestion_batches WHERE batch_id=%s',(batch_id,)).fetchone()
            if not first: raise ValueError('batch_missing')
            # A successful receipt is immutable. Replaying it performs no work
            # and must remain possible after its worker lease has finished.
            if first['status']=='succeeded': return first['receipt']
            binding=c.execute('SELECT * FROM ops_ingestion_bindings WHERE connection_id=%s FOR UPDATE',(first['connection_id'],)).fetchone()
            initial=first['spec']
            if initial.get('job_id'):
                job=c.execute('SELECT j.*,s.connection_id,s.binding_version,s.data_type,s.source_kind,s.scope FROM ops_ingestion_jobs j JOIN ops_ingestion_streams s USING(stream_id) WHERE j.job_id=%s FOR UPDATE OF j',(initial['job_id'],)).fetchone()
                alive=c.execute('SELECT %s::timestamptz>clock_timestamp() AS alive',(job['lease_until'],)).fetchone()['alive'] if job else False
                if not job or job['status']!='running' or str(job['lease_token'])!=initial.get('lease_token') or not alive: raise ValueError('lease_rejected')
                if any(str(job[k])!=str(initial[k]) for k in ('connection_id','binding_version','data_type','source_kind')) or job['scope']!=initial['scope'] or job['window_start']!=timestamp(initial['window_start']) or job['window_end']!=timestamp(initial['window_end']): raise ValueError('job_batch_mismatch')
            elif initial['source_kind']=='wdt_api': raise ValueError('job_required')
            b=c.execute('SELECT * FROM ops_ingestion_batches WHERE batch_id=%s FOR UPDATE',(batch_id,)).fetchone()
            if b['status']=='succeeded': return b['receipt']
            s=b['spec']; issues=[]
            pages=c.execute('SELECT * FROM ops_ingestion_pages WHERE batch_id=%s ORDER BY page_no',(batch_id,)).fetchall()
            if len(pages)!=s['expected_pages']: issues.append('pages_incomplete')
            if len({p['hash'] for p in pages})!=len(pages): issues.append('duplicate_page')
            records=[r for p in pages for r in p['records']]
            if len(records)!=s['expected_count']: issues.append('count_mismatch')
            if binding['binding_version']!=b['binding_version']: issues.append('binding_changed')
            result=normalize_records(s['data_type'],records,s['context']) if not issues else None
            if result: issues.extend(result.issues)
            facts={}
            if result and not issues:
                for f in result.facts:
                    key=(f['entity_type'],f['source_id'])
                    if not contained(scope_value(f['scope']),b['scope']): issues.append('fact_scope_mismatch')
                    prev=facts.get(key)
                    if prev and timestamp(prev['source_updated_at'])==timestamp(f['source_updated_at']) and prev!=f: issues.append('source_time_conflict')
                    if not prev or timestamp(f['source_updated_at'])>timestamp(prev['source_updated_at']): facts[key]=f
                for key,f in facts.items():
                    old=c.execute("SELECT f.fact,f.source_updated_at FROM ops_ingestion_facts f JOIN ops_ingestion_batches ob ON ob.batch_id=f.batch_id WHERE f.connection_id=%s AND f.data_type=%s AND f.source_kind=%s AND f.entity_type=%s AND f.source_id=%s AND ob.binding_version=%s AND ob.spec->'context'->>'mapping_version'=%s",(b['connection_id'],b['data_type'],b['source_kind'],*key,b['binding_version'],s['context']['mapping_version'])).fetchone()
                    if old and old['source_updated_at']==timestamp(f['source_updated_at']) and old['fact']!=f: issues.append('source_time_conflict')
            if issues:
                receipt={'batch_id':str(batch_id),'status':'partial','issues':sorted(set(issues))}
                c.execute("UPDATE ops_ingestion_batches SET status='partial',issues=%s,updated_at=clock_timestamp() WHERE batch_id=%s",(Jsonb(receipt['issues']),batch_id))
                return receipt
            for key,f in facts.items():
                c.execute('INSERT INTO ops_ingestion_fact_versions VALUES (%s,%s,%s,%s)',(batch_id,*key,Jsonb(f)))
                c.execute('INSERT INTO ops_ingestion_facts VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(connection_id,data_type,source_kind,entity_type,source_id) DO UPDATE SET scope=excluded.scope,fact=excluded.fact,source_updated_at=excluded.source_updated_at,batch_id=excluded.batch_id WHERE excluded.source_updated_at>ops_ingestion_facts.source_updated_at OR (SELECT binding_version FROM ops_ingestion_batches WHERE batch_id=ops_ingestion_facts.batch_id)<>(SELECT binding_version FROM ops_ingestion_batches WHERE batch_id=excluded.batch_id)',(b['connection_id'],b['data_type'],b['source_kind'],*key,Jsonb(f['scope']),Jsonb(f),f['source_updated_at'],batch_id))
            sk=hashlib.sha256(canonical(b['scope']).encode()).hexdigest()
            c.execute('INSERT INTO ops_ingestion_cursors VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(connection_id,data_type,source_kind,scope_key) DO UPDATE SET watermark=excluded.watermark,batch_id=excluded.batch_id WHERE excluded.watermark>ops_ingestion_cursors.watermark OR (SELECT binding_version FROM ops_ingestion_batches WHERE batch_id=ops_ingestion_cursors.batch_id)<>(SELECT binding_version FROM ops_ingestion_batches WHERE batch_id=excluded.batch_id)',(b['connection_id'],b['data_type'],b['source_kind'],sk,Jsonb(b['scope']),s['window_end'],batch_id))
            c.execute('INSERT INTO ops_ingestion_pending_evaluations(batch_id) VALUES (%s)',(batch_id,))
            receipt={'batch_id':str(batch_id),'status':'succeeded','fact_count':str(len(facts)),'issues':[]}
            c.execute("UPDATE ops_ingestion_batches SET status='succeeded',issues='[]',receipt=%s,updated_at=clock_timestamp() WHERE batch_id=%s",(Jsonb(receipt),batch_id))
            if initial.get('job_id') and not c.execute('SELECT lease_until>clock_timestamp() AS alive FROM ops_ingestion_jobs WHERE job_id=%s',(initial['job_id'],)).fetchone()['alive']:
                raise ValueError('lease_rejected')
            return receipt

    def get_batch(self,batch_id):
        with self._connect() as c:
            row=c.execute('SELECT * FROM ops_ingestion_batches WHERE batch_id=%s',(batch_id,)).fetchone()
            if not row: raise ValueError('batch_missing')
            row['batch_id']=str(row['batch_id']); row['connection_id']=str(row['connection_id']); row['binding_version']=str(row['binding_version'])
            return row

    def get_cursor(self,connection_id,data_type,scope,*,source_kind='synthetic'):
        sk=hashlib.sha256(canonical(scope_value(scope)).encode()).hexdigest()
        with self._connect() as c:
            row=c.execute("SELECT cur.* FROM ops_ingestion_cursors cur JOIN ops_ingestion_batches b ON b.batch_id=cur.batch_id JOIN ops_ingestion_bindings binding ON binding.connection_id=cur.connection_id WHERE cur.connection_id=%s AND cur.data_type=%s AND cur.source_kind=%s AND cur.scope_key=%s AND b.binding_version=binding.binding_version AND b.spec->'context'->>'mapping_version'=binding.context->>'mapping_version'",(connection_id,data_type,source_kind,sk)).fetchone()
            if row: row['batch_id']=str(row['batch_id']); row['connection_id']=str(row['connection_id'])
            return row

    def pending_evaluations(self):
        with self._connect() as c:
            return [{**r,'batch_id':str(r['batch_id'])} for r in c.execute('SELECT * FROM ops_ingestion_pending_evaluations ORDER BY created_at').fetchall()]

    def current_facts(self,connection_id,data_type,scope,*,source_kind='synthetic'):
        scope=scope_value(scope)
        with self._connect() as c:
            binding=c.execute('SELECT context FROM ops_ingestion_bindings WHERE connection_id=%s',(connection_id,)).fetchone()
            if not binding or not contained(scope,scope_value(binding['context']['allowed_scope'])): raise ValueError('scope_forbidden')
            rows=c.execute("SELECT f.fact FROM ops_ingestion_facts f JOIN ops_ingestion_batches b ON b.batch_id=f.batch_id JOIN ops_ingestion_bindings binding ON binding.connection_id=f.connection_id WHERE f.connection_id=%s AND f.data_type=%s AND f.source_kind=%s AND b.binding_version=binding.binding_version AND b.spec->'context'->>'mapping_version'=binding.context->>'mapping_version' ORDER BY f.entity_type,f.source_id",(connection_id,data_type,source_kind)).fetchall()
            return [r['fact'] for r in rows if contained(r['fact']['scope'],scope)]

    def materialize_metrics(self,batch_id):
        from ..metrics.materialize import materialize_facts
        with self._connect() as c:
            b=c.execute('SELECT * FROM ops_ingestion_batches WHERE batch_id=%s FOR UPDATE',(batch_id,)).fetchone()
            if not b or b['status']!='succeeded': raise ValueError('batch_not_available')
            old=c.execute('SELECT snapshot FROM ops_ingestion_snapshots WHERE batch_id=%s',(batch_id,)).fetchone()
            if old: return old['snapshot']
            s=b['spec']
            # Snapshot is as-of this batch's committed fact versions, never later facts.
            rows=c.execute('SELECT v.fact,v.batch_id,b.updated_at FROM ops_ingestion_fact_versions v JOIN ops_ingestion_batches b USING(batch_id) WHERE b.connection_id=%s AND b.data_type=%s AND b.source_kind=%s AND b.status=\'succeeded\' AND b.updated_at<=%s AND b.binding_version=%s AND b.spec->\'context\'->>\'mapping_version\'=%s ORDER BY b.updated_at',(b['connection_id'],b['data_type'],b['source_kind'],b['updated_at'],b['binding_version'],s['context']['mapping_version'])).fetchall()
            latest={}; provenance={}
            for r in rows:
                f=r['fact']
                key=(f['entity_type'],f['source_id']); prev=latest.get(key)
                if not prev or timestamp(f['source_updated_at'])>timestamp(prev['source_updated_at']):
                    latest[key]=f
                    provenance[key]=str(r['batch_id'])
            latest={key:f for key,f in latest.items() if contained(f['scope'],b['scope'])}
            sources={provenance[key] for key in latest}
            manifest=s.get('business_coverage',{})
            coverage=s['coverage_complete'] and s['coverage_kind']=='full' and s['context'].get('mapping_confirmed') is True and manifest.get('confirmed') is True
            start=manifest.get('start',s['window_start']); end=manifest.get('end',s['window_end'])
            zone=manifest.get('timezone',s['context']['source_timezone'])
            if coverage:
                try:
                    coverage=timestamp(start)<timestamp(end) and zone==s['context']['source_timezone']
                except (ValueError,TypeError,AttributeError):
                    coverage=False
            snap=materialize_facts(list(latest.values()),data_type=b['data_type'],window_start=start,window_end=end,timezone=zone,coverage_complete=coverage)
            snap['scope']=b['scope']
            snap.update(batch_id=str(batch_id),source_batch_ids=sorted(sources),source_kind=b['source_kind'],as_of=b['updated_at'].isoformat())
            c.execute('INSERT INTO ops_ingestion_snapshots VALUES (%s,%s,now())',(batch_id,Jsonb(snap)))
            return snap
