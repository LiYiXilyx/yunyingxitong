"""Receipt-checked delivery. The row lock is held for one bounded transport call."""
from uuid import UUID
from urllib.parse import urlsplit
import ipaddress
import httpx
from ..jobs.ledger import JobLedger

# Check authoritative binding again at send time, including queued commands from before
# a configuration change. Invalid entries remain durable but are never delivered.
ELIGIBLE="""EXISTS (SELECT 1 FROM ops_ingestion_streams s JOIN ops_ingestion_bindings b USING(connection_id)
 WHERE s.stream_id=ops_ingestion_health_outbox.stream_id
 AND s.binding_version=b.binding_version AND s.source_kind='synthetic'
 AND s.source_kind=b.context->>'source_kind'
 AND (s.scope->'store_ids') <@ (b.context->'allowed_scope'->'store_ids')
 AND (s.scope->'warehouse_ids') <@ (b.context->'allowed_scope'->'warehouse_ids')
 AND (command->>'binding_version')::numeric=b.binding_version)"""

class HealthOutbox(JobLedger):
    def pending(self, *, stream_id=None):
        with self._connect() as c:
            return [r['command'] for r in c.execute('SELECT command FROM ops_ingestion_health_outbox WHERE '+ELIGIBLE+' AND acknowledged_at IS NULL AND (%s::uuid IS NULL OR stream_id=%s::uuid) ORDER BY created_at,command_id',(stream_id,stream_id)).fetchall()]

    def deliver_one(self,send_callable, *, stream_id=None):
        with self._connect() as c:
            row=c.execute('SELECT * FROM ops_ingestion_health_outbox WHERE '+ELIGIBLE+' AND acknowledged_at IS NULL AND (%s::uuid IS NULL OR stream_id=%s::uuid) ORDER BY created_at,command_id FOR UPDATE SKIP LOCKED LIMIT 1',(stream_id,stream_id)).fetchone()
            if not row:return False
            binding=c.execute('SELECT b.* FROM ops_ingestion_bindings b JOIN ops_ingestion_streams s USING(connection_id) WHERE s.stream_id=%s FOR SHARE OF b',(row['stream_id'],)).fetchone()
            # Keep the authority version stable until the bounded send completes.
            if not binding or str(int(binding['binding_version']))!=row['command']['binding_version']:return False
            command=row['command'];receipt=None
            try:
                receipt=send_callable(command)
                if isinstance(receipt,dict) and 'data' in receipt:receipt=receipt['data']
                UUID(receipt['receipt_id'])
                if receipt['command_id']!=command['command_id'] or receipt['health_revision']!=command['payload']['health_revision'] or receipt['status'] not in ('applied','duplicate','ignored_stale'):raise ValueError('receipt_invalid')
            except Exception:
                c.execute("UPDATE ops_ingestion_health_outbox SET attempts=attempts+1,last_error='delivery_unconfirmed' WHERE command_id=%s",(row['command_id'],))
                return False
            c.execute('UPDATE ops_ingestion_health_outbox SET acknowledged_at=now(),receipt_id=%s,attempts=attempts+1,last_error=NULL WHERE command_id=%s',(receipt['receipt_id'],row['command_id']))
            return True

class NocoBaseHealthTransport:
    def __init__(self,base_url,token,*,internal_origins=()):
        u=urlsplit(base_url)
        origin=f'{u.scheme}://{u.netloc}'
        local=u.hostname=='localhost'
        try:local=local or ipaddress.ip_address(u.hostname).is_loopback
        except ValueError:pass
        if u.scheme not in ('http','https') or u.username or u.password or u.query or u.fragment or u.path not in ('','/') or not (local or origin in internal_origins):raise ValueError('health_origin_forbidden')
        self.url=origin+'/api/opsDataHealth:ingest';self._token=token
    def __call__(self,command):
        try:
            with httpx.Client(timeout=10,follow_redirects=False,trust_env=False) as client:
                response=client.post(self.url,json=command,headers={'Authorization':'Bearer '+self._token})
                if response.status_code<200 or response.status_code>=300:raise ValueError('health_http_failure')
                return response.json()
        except Exception:raise ValueError('health_transport_failure') from None
