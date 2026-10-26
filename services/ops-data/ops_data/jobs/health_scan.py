"""Independent registered-stream health, committed atomically with durable delivery."""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from uuid import uuid4
import hashlib
from psycopg.types.json import Jsonb
from .ledger import JobLedger
from ..ingestion.repository import canonical, timestamp, contained, scope_value
from ..contracts import payload_hash, validate_command


def wire(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00','Z') if value else None


class HealthScanner(JobLedger):
    def migrate(self):
        with self._connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(51007)')
            c.execute((Path(__file__).parent/'migrations/002_health.sql').read_text())

    def scan(self, now=None, *, connection_id=None):
        now=now or datetime.now(timezone.utc)
        if now.tzinfo is None: raise ValueError('timezone_required')
        result=[]
        with self._connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(51008)')
            streams=c.execute('SELECT * FROM ops_ingestion_streams WHERE (%s::uuid IS NULL OR connection_id=%s::uuid) ORDER BY stream_id FOR UPDATE',(connection_id,connection_id)).fetchall()
            for s in streams:
                binding=c.execute('SELECT * FROM ops_ingestion_bindings WHERE connection_id=%s FOR SHARE',(s['connection_id'],)).fetchone()
                current_binding=bool(binding and binding['binding_version']==s['binding_version'] and binding['context']['source_kind']==s['source_kind'] and contained(s['scope'],scope_value(binding['context']['allowed_scope'])))
                if not current_binding:
                    replacement=c.execute('SELECT 1 FROM ops_ingestion_streams WHERE connection_id=%s AND binding_version=%s AND source_kind=%s AND data_type=%s AND scope=%s LIMIT 1',(s['connection_id'],binding['binding_version'] if binding else -1,s['source_kind'],s['data_type'],Jsonb(s['scope']))).fetchone()
                    if replacement:continue
                job=c.execute('SELECT * FROM ops_ingestion_jobs WHERE stream_id=%s AND window_end<=%s ORDER BY window_end DESC,updated_at DESC LIMIT 1',(s['stream_id'],now)).fetchone()
                attempt=c.execute('SELECT a.* FROM ops_ingestion_job_attempts a JOIN ops_ingestion_jobs j USING(job_id) WHERE j.stream_id=%s ORDER BY started_at DESC LIMIT 1',(s['stream_id'],)).fetchone()
                success=c.execute("SELECT * FROM ops_ingestion_batches WHERE connection_id=%s AND binding_version=%s AND source_kind=%s AND data_type=%s AND scope=%s AND status='succeeded' ORDER BY (spec->>'window_end')::timestamptz DESC LIMIT 1",(s['connection_id'],s['binding_version'],s['source_kind'],s['data_type'],Jsonb(s['scope']))).fetchone()
                if job:start,end=job['window_start'],job['window_end']
                else:
                    end=now.astimezone(ZoneInfo(s['timezone'])).replace(hour=0,minute=0,second=0,microsecond=0)
                    start=end-timedelta(days=1)
                deadline=end+timedelta(seconds=s['freshness_seconds'])
                status='failed';error='no_successful_batch';missing=[]
                if success:
                    covered=timestamp(success['spec']['window_start'])<=start and timestamp(success['spec']['window_end'])>=end
                    status='succeeded' if covered and now<=deadline else 'partial'
                    error=None if status=='succeeded' else 'freshness_expired' if now>deadline else 'coverage_incomplete'
                if job and job['status'] in ('failed','partial','needs_user'):
                    status=job['status'];error=job['error_class'] or 'batch_rejected'
                version=str(s['binding_version'])
                if not binding or binding['binding_version']!=s['binding_version'] or binding['context']['source_kind']!=s['source_kind'] or not contained(s['scope'],scope_value(binding['context']['allowed_scope'])):
                    status='needs_user';error='binding_changed'
                if s['source_kind']!='synthetic':
                    status='needs_user';error='health_source_not_supported';missing=['health_receiver_source_support']
                p=dict(kind='HealthEnvelope',scope=s['scope'],data_type=s['data_type'],last_attempt_at=wire(attempt['started_at']) if attempt else None,last_success_at=wire(success['updated_at']) if success else None,expected_window={'start':wire(start),'end':wire(end)},freshness_deadline=wire(deadline),status=status,missing_fields=missing,error_class=error)
                fingerprint=hashlib.sha256(canonical({'payload':p,'binding_version':version,'source_kind':s['source_kind']}).encode()).hexdigest()
                old=c.execute('SELECT * FROM ops_ingestion_health WHERE stream_id=%s',(s['stream_id'],)).fetchone()
                if old and old['fingerprint']==fingerprint:continue
                latest=c.execute("SELECT max(revision) AS revision FROM ops_ingestion_health WHERE command->'payload'->'scope'=%s AND command->'payload'->>'data_type'=%s",(Jsonb(s['scope']),s['data_type'])).fetchone()['revision']
                revision=(latest or 0)+1;p['health_revision']=str(revision)
                command=dict(schema_version='1',command_id=str(uuid4()),binding_version=version,occurred_at=wire(now),payload=p)
                command['payload_hash']=payload_hash(command);validate_command(command)
                c.execute('INSERT INTO ops_ingestion_health(stream_id,revision,fingerprint,command) VALUES (%s,%s,%s,%s) ON CONFLICT(stream_id) DO UPDATE SET revision=excluded.revision,fingerprint=excluded.fingerprint,command=excluded.command,updated_at=now()',(s['stream_id'],revision,fingerprint,Jsonb(command)))
                if s['source_kind']=='synthetic' and current_binding:c.execute('INSERT INTO ops_ingestion_health_outbox(command_id,stream_id,command) VALUES (%s,%s,%s)',(command['command_id'],s['stream_id'],Jsonb(command)))
                result.append(command)
        return result
