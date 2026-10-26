"""PostgreSQL leases with fencing tokens and immutable attempt history."""
import hashlib
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from ..ingestion.repository import canonical, scope_value, contained, timestamp

ERROR_CLASSES=frozenset(('source_unavailable','binding_changed','binding_mismatch','scope_forbidden','authentication_required','rate_limited','pagination_incomplete','normalization_failed','coverage_incomplete','batch_rejected','internal_error','lease_expired','needs_user','unknown_status','mapping_unconfirmed'))

class JobLedger:
    def __init__(self,dsn): self.database_url=dsn

    @contextmanager
    def _connect(self):
        try:
            with psycopg.connect(self.database_url,connect_timeout=5,options='-c statement_timeout=15000 -c lock_timeout=3000',row_factory=dict_row) as c: yield c
        except psycopg.Error as exc: raise ValueError('jobs_storage_error_'+str(exc.sqlstate)) from None

    def migrate(self):
        with self._connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(51006)')
            c.execute((Path(__file__).parent/'migrations/001_jobs.sql').read_text())

    def register_stream(self,connection_id,binding_version,data_type,source_kind,scope,timezone,freshness_seconds):
        cid=str(UUID(connection_id)); scope=scope_value(scope); ZoneInfo(timezone)
        if not any(scope.values()) or data_type not in ('orders','refunds','inventory','catalog') or source_kind not in ('synthetic','wdt_api','manual_import'): raise ValueError('stream_invalid')
        if not str(binding_version).isdigit() or int(binding_version)<1 or type(freshness_seconds) is not int or freshness_seconds<1: raise ValueError('stream_invalid')
        key=hashlib.sha256(canonical(scope).encode()).hexdigest()
        with self._connect() as c:
            b=c.execute('SELECT * FROM ops_ingestion_bindings WHERE connection_id=%s FOR SHARE',(cid,)).fetchone()
            if not b or b['binding_version']!=int(binding_version) or b['context']['source_kind']!=source_kind or not contained(scope,scope_value(b['context']['allowed_scope'])): raise ValueError('binding_mismatch')
            row=c.execute('INSERT INTO ops_ingestion_streams(stream_id,connection_id,binding_version,data_type,source_kind,scope_key,scope,timezone,freshness_seconds) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(connection_id,binding_version,data_type,source_kind,scope_key) DO UPDATE SET timezone=excluded.timezone,freshness_seconds=excluded.freshness_seconds RETURNING stream_id',(uuid4(),cid,binding_version,data_type,source_kind,key,Jsonb(scope),timezone,freshness_seconds)).fetchone()
            return str(row['stream_id'])

    def enqueue(self,stream_id,window_start,window_end,kind='incremental'):
        start=timestamp(window_start) if isinstance(window_start,str) else timestamp(window_start.isoformat()); end=timestamp(window_end) if isinstance(window_end,str) else timestamp(window_end.isoformat())
        if start>=end or kind not in ('incremental','history','backfill','rescan'): raise ValueError('window_invalid')
        with self._connect() as c:
            row=c.execute('INSERT INTO ops_ingestion_jobs(job_id,stream_id,window_start,window_end,kind) VALUES (%s,%s,%s,%s,%s) ON CONFLICT(stream_id,window_start,window_end,kind) DO UPDATE SET stream_id=excluded.stream_id RETURNING job_id',(uuid4(),stream_id,start,end,kind)).fetchone()
            return str(row['job_id'])

    def claim(self,worker,lease_seconds=60,*,job_id=None):
        if not isinstance(worker,str) or not worker or len(worker)>128 or type(lease_seconds) is not int or not 1<=lease_seconds<=3600: raise ValueError('lease_invalid')
        with self._connect() as c:
            j=c.execute("SELECT j.* FROM ops_ingestion_jobs j JOIN ops_ingestion_streams s USING(stream_id) JOIN ops_ingestion_bindings b ON b.connection_id=s.connection_id WHERE (j.status='queued' OR (j.status='running' AND j.lease_until<=clock_timestamp())) AND (%s::uuid IS NULL OR j.job_id=%s::uuid) AND j.window_end<=clock_timestamp() AND s.binding_version=b.binding_version AND s.source_kind=(b.context->>'source_kind') AND (s.scope->'store_ids') <@ (b.context->'allowed_scope'->'store_ids') AND (s.scope->'warehouse_ids') <@ (b.context->'allowed_scope'->'warehouse_ids') ORDER BY j.window_end,j.created_at FOR UPDATE OF j SKIP LOCKED LIMIT 1",(job_id,job_id)).fetchone()
            if not j: return None
            c.execute("UPDATE ops_ingestion_job_attempts SET status='expired',error_class='lease_expired',finished_at=clock_timestamp() WHERE job_id=%s AND generation=%s AND status='running'",(j['job_id'],j['generation']))
            token=uuid4()
            j=c.execute("UPDATE ops_ingestion_jobs SET status='running',generation=generation+1,lease_token=%s,lease_until=clock_timestamp()+%s*interval '1 second',worker=%s,error_class=NULL,updated_at=clock_timestamp() WHERE job_id=%s RETURNING *",(token,lease_seconds,worker,j['job_id'])).fetchone()
            c.execute("INSERT INTO ops_ingestion_job_attempts(job_id,generation,lease_token,worker,lease_until,status) VALUES (%s,%s,%s,%s,%s,'running')",(j['job_id'],j['generation'],token,worker,j['lease_until']))
            return self._read(c,j['job_id'])

    def _active(self,c,job_id,token):
        row=c.execute("SELECT * FROM ops_ingestion_jobs WHERE job_id=%s AND lease_token=%s AND status='running' AND lease_until>clock_timestamp() FOR UPDATE",(job_id,token)).fetchone()
        if not row: raise ValueError('lease_rejected')
        return row

    def heartbeat(self,job_id,token,lease_seconds=60):
        if type(lease_seconds) is not int or not 1<=lease_seconds<=3600: raise ValueError('lease_invalid')
        with self._connect() as c:
            j=self._active(c,job_id,token)
            c.execute("UPDATE ops_ingestion_jobs SET lease_until=clock_timestamp()+%s*interval '1 second' WHERE job_id=%s",(lease_seconds,job_id))
            c.execute('UPDATE ops_ingestion_job_attempts SET lease_until=(SELECT lease_until FROM ops_ingestion_jobs WHERE job_id=%s) WHERE job_id=%s AND generation=%s',(job_id,job_id,j['generation']))

    def finish(self,job_id,token,status,*,batch_id=None,error_class=None):
        if status not in ('succeeded','partial','failed','needs_user') or (error_class is not None and error_class not in ERROR_CLASSES): raise ValueError('result_invalid')
        with self._connect() as c:
            # Binding first matches ingestion commit lock order and fences config changes.
            s=c.execute('SELECT s.* FROM ops_ingestion_streams s JOIN ops_ingestion_jobs j USING(stream_id) WHERE j.job_id=%s',(job_id,)).fetchone()
            if not s: raise ValueError('job_missing')
            b=c.execute('SELECT * FROM ops_ingestion_bindings WHERE connection_id=%s FOR SHARE',(s['connection_id'],)).fetchone()
            j=self._active(c,job_id,token)
            if status=='succeeded':
                batch=c.execute('SELECT * FROM ops_ingestion_batches WHERE batch_id=%s FOR SHARE',(batch_id,)).fetchone() if batch_id else None
                if not b or b['binding_version']!=s['binding_version'] or b['context']['source_kind']!=s['source_kind'] or not contained(s['scope'],scope_value(b['context']['allowed_scope'])): raise ValueError('binding_changed')
                if not batch or batch['status']!='succeeded' or any(batch[k]!=s[k] for k in ('connection_id','binding_version','data_type','source_kind','scope')) or timestamp(batch['spec']['window_start'])!=j['window_start'] or timestamp(batch['spec']['window_end'])!=j['window_end']: raise ValueError('batch_mismatch')
                refs=batch['spec']
                if s['source_kind']=='wdt_api' or 'job_id' in refs or 'lease_token' in refs:
                    if refs.get('job_id')!=str(j['job_id']) or refs.get('lease_token')!=str(j['lease_token']): raise ValueError('batch_attempt_mismatch')
                if error_class: raise ValueError('result_invalid')
            c.execute('UPDATE ops_ingestion_jobs SET status=%s,batch_id=%s,error_class=%s,lease_until=NULL,updated_at=clock_timestamp() WHERE job_id=%s',(status,batch_id,error_class,job_id))
            c.execute('UPDATE ops_ingestion_job_attempts SET status=%s,batch_id=%s,error_class=%s,finished_at=clock_timestamp() WHERE job_id=%s AND generation=%s',(status,batch_id,error_class,job_id,j['generation']))

    def retry(self,job_id):
        with self._connect() as c:
            row=c.execute("UPDATE ops_ingestion_jobs SET status='queued',lease_token=NULL,lease_until=NULL,batch_id=NULL,error_class=NULL,updated_at=clock_timestamp() WHERE job_id=%s AND status IN ('failed','needs_user','partial') RETURNING job_id",(job_id,)).fetchone()
            if not row: raise ValueError('retry_rejected')

    def _read(self,c,job_id):
        row=c.execute('SELECT j.*,s.connection_id,s.binding_version,s.data_type,s.source_kind,s.scope,s.scope_key,s.timezone,s.freshness_seconds FROM ops_ingestion_jobs j JOIN ops_ingestion_streams s USING(stream_id) WHERE job_id=%s',(job_id,)).fetchone()
        if not row: raise ValueError('job_missing')
        for k in ('job_id','stream_id','connection_id','lease_token','batch_id'):
            if row[k] is not None: row[k]=str(row[k])
        row['binding_version']=str(row['binding_version'])
        return row

    def get_job(self,job_id):
        with self._connect() as c: return self._read(c,job_id)
