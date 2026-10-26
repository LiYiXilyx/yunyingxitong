import os
from uuid import uuid4
from datetime import datetime, timezone
import pytest
from ops_data.ingestion.repository import IngestionRepository
from ops_data.jobs.ledger import JobLedger
from ops_data.jobs.health_scan import HealthScanner
from ops_data.delivery.health import HealthOutbox

@pytest.fixture
def state():
    dsn=os.getenv('OPS_TEST_DATABASE_URL'); assert dsn, 'OPS_TEST_DATABASE_URL required'
    r=IngestionRepository(dsn);r.migrate(); l=JobLedger(dsn);l.migrate(); h=HealthScanner(dsn);h.migrate()
    cid=str(uuid4()); scope={'store_ids':[],'warehouse_ids':[str(uuid4())]}
    ctx=dict(connection_id=cid,binding_version='1',source_kind='synthetic',allowed_scope=scope,source_timezone='UTC',mapping_version='1',mapping_confirmed=True,store_bindings={},warehouse_bindings={'W':scope['warehouse_ids'][0]},order_status_map={})
    r.register_binding(cid,'1',ctx);sid=l.register_stream(cid,'1','inventory','synthetic',scope,'UTC',3600)
    yield r,l,h,HealthOutbox(dsn),sid,ctx
    with r._connect() as c:c.execute('DELETE FROM ops_ingestion_bindings WHERE connection_id=%s',(cid,))

def test_never_attempted_repeat_and_retry_receipt(state):
    r,l,h,o,sid,ctx=state
    now=datetime(2026,10,26,12,tzinfo=timezone.utc)
    commands=h.scan(now,connection_id=ctx['connection_id']); cmd=next(x for x in commands if x['payload']['scope']==ctx['allowed_scope'])
    assert cmd['payload']['last_attempt_at'] is None
    assert cmd['payload']['status']=='failed'
    assert h.scan(now,connection_id=ctx['connection_id'])==[]
    sent=[]
    def lost(c):sent.append(c['command_id']);raise TimeoutError()
    assert not o.deliver_one(lost,stream_id=sid)
    assert not o.deliver_one(lambda c:{'receipt_id':str(uuid4()),'command_id':str(uuid4()),'status':'applied','health_revision':c['payload']['health_revision']},stream_id=sid)
    def ok(c):
        sent.append(c['command_id']);return {'receipt_id':str(uuid4()),'command_id':c['command_id'],'status':'duplicate','health_revision':c['payload']['health_revision']}
    assert o.deliver_one(ok,stream_id=sid);assert sent==[cmd['command_id']]*2
    assert not HealthOutbox(o.database_url).pending(stream_id=sid)

def test_first_failure_and_binding_change(state):
    r,l,h,o,sid,ctx=state
    jid=l.enqueue(sid,'2026-01-01T00:00:00Z','2026-01-02T00:00:00Z'); j=l.claim('health-test');l.finish(jid,j['lease_token'],'partial',error_class='coverage_incomplete')
    cmd=next(x for x in h.scan(connection_id=ctx['connection_id']) if x['payload']['scope']==ctx['allowed_scope']); assert cmd['payload']['status']=='partial'
    r.register_binding(ctx['connection_id'],'2',{**ctx,'binding_version':'2'})
    cmd=next(x for x in h.scan(connection_id=ctx['connection_id']) if x['payload']['scope']==ctx['allowed_scope']);assert cmd['payload']['status']=='needs_user';assert cmd['payload']['health_revision']=='2'

def test_workers_receipt_validation_and_source_restriction(state):
    from concurrent.futures import ThreadPoolExecutor
    from ops_data.delivery.health import NocoBaseHealthTransport
    r,l,h,o,sid,ctx=state
    h.scan(connection_id=ctx['connection_id'])
    calls=[]
    def send(cmd):
        calls.append(cmd['command_id'])
        return dict(receipt_id=str(uuid4()),command_id=cmd['command_id'],health_revision=cmd['payload']['health_revision'],status='ignored_stale')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:HealthOutbox(o.database_url).deliver_one(send,stream_id=sid),range(2)))
    assert sorted(results)==[False,True];assert len(calls)==1
    with pytest.raises(ValueError):NocoBaseHealthTransport('https://example.com','secret')
    with pytest.raises(ValueError):NocoBaseHealthTransport('http://localhost@evil.example','secret')
    NocoBaseHealthTransport('http://nocobase:80','secret',internal_origins=('http://nocobase:80',))

def test_recent_historical_success_is_not_current(state):
    r,l,h,o,sid,ctx=state
    spec=dict(batch_id=str(uuid4()),connection_id=ctx['connection_id'],binding_version='1',data_type='inventory',source_kind='synthetic',scope=ctx['allowed_scope'],window_start='2026-01-01T00:00:00Z',window_end='2026-01-02T00:00:00Z',expected_pages=1,expected_count=0,page_start=0,coverage_complete=False,coverage_kind='incremental',context=ctx)
    bid=r.begin_batch(spec);r.stage_page(bid,0,[]);r.commit_batch(bid)
    cmd=h.scan(datetime(2026,10,26,12,tzinfo=timezone.utc),connection_id=ctx['connection_id'])[0]
    assert cmd['payload']['status']=='partial'
    assert cmd['payload']['error_class']=='freshness_expired'
    assert cmd['payload']['last_attempt_at'] is None
    assert cmd['payload']['expected_window']['end']=='2026-10-26T00:00:00Z'

def test_replaced_stream_pending_cannot_override_current_success(state):
    r,l,h,o,old,ctx=state
    now=datetime(2026,10,26,0,30,tzinfo=timezone.utc)
    first=h.scan(now,connection_id=ctx['connection_id'])[0]
    ctx2={**ctx,'binding_version':'2'};r.register_binding(ctx['connection_id'],'2',ctx2)
    current=l.register_stream(ctx['connection_id'],'2','inventory','synthetic',ctx['allowed_scope'],'UTC',3600)
    spec=dict(batch_id=str(uuid4()),connection_id=ctx['connection_id'],binding_version='2',data_type='inventory',source_kind='synthetic',scope=ctx['allowed_scope'],window_start='2026-10-25T00:00:00Z',window_end='2026-10-26T00:00:00Z',expected_pages=1,expected_count=0,page_start=0,coverage_complete=False,coverage_kind='incremental',context=ctx2)
    bid=r.begin_batch(spec);r.stage_page(bid,0,[]);r.commit_batch(bid)
    commands=h.scan(now,connection_id=ctx['connection_id'])
    assert len(commands)==1
    assert commands[0]['payload']['status']=='succeeded'
    assert int(commands[0]['payload']['health_revision'])>int(first['payload']['health_revision'])
    assert o.pending(stream_id=old)==[]
    assert not o.deliver_one(lambda _:pytest.fail('old stream sent'),stream_id=old)
    assert o.pending(stream_id=current)==commands
