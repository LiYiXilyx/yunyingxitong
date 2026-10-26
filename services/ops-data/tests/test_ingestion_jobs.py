import os
from datetime import datetime, timezone
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest


def test_planner_dst_and_inventory():
    from ops_data.jobs.planner import history_plan, incremental_plan
    for date, hours in [('2026-03-09',23),('2026-11-02',25)]:
        windows=history_plan('orders','America/New_York',now=datetime.fromisoformat(date+'T12:00:00+00:00'),days=1)
        assert (windows[0][1]-windows[0][0]).total_seconds()==hours*3600
    start=datetime(2026,1,1,tzinfo=timezone.utc); end=datetime(2026,1,2,tzinfo=timezone.utc)
    with pytest.raises(ValueError): incremental_plan('inventory',start,end)
    assert incremental_plan('inventory',start,end,timestamp_api_confirmed=True)[0][0]==start

@pytest.fixture
def jobs():
    from ops_data.jobs.ledger import JobLedger
    from ops_data.ingestion.repository import IngestionRepository
    dsn=os.environ.get('OPS_TEST_DATABASE_URL'); assert dsn, 'OPS_TEST_DATABASE_URL required'
    repo=IngestionRepository(dsn); repo.migrate(); ledger=JobLedger(dsn); ledger.migrate()
    cid=str(uuid4()); scope={'store_ids':[],'warehouse_ids':[str(uuid4())]}
    ctx=dict(connection_id=cid,binding_version='1',source_kind='synthetic',allowed_scope=scope,source_timezone='UTC',mapping_version='1',mapping_confirmed=True,store_bindings={},warehouse_bindings={'W':scope['warehouse_ids'][0]},order_status_map={})
    repo.register_binding(cid,'1',ctx)
    sid=ledger.register_stream(cid,'1','inventory','synthetic',scope,'UTC',3600)
    yield ledger,repo,sid,ctx,scope
    with repo._connect() as c:
        c.execute('DELETE FROM ops_ingestion_streams WHERE connection_id=%s',(cid,))
        c.execute('DELETE FROM ops_ingestion_bindings WHERE connection_id=%s',(cid,))

def test_leases_restart_retry_and_binding(jobs):
    ledger,repo,sid,ctx,scope=jobs
    jid=ledger.enqueue(sid,'2026-01-01T00:00:00Z','2026-01-02T00:00:00Z')
    assert ledger.enqueue(sid,'2026-01-01T00:00:00Z','2026-01-02T00:00:00Z')==jid
    with ThreadPoolExecutor(max_workers=2) as pool: claims=list(pool.map(lambda w:ledger.claim(w),['a','b']))
    first=next(j for j in claims if j); assert sum(j is not None for j in claims)==1
    with repo._connect() as c: c.execute("UPDATE ops_ingestion_jobs SET lease_until=now()-interval '1 second' WHERE job_id=%s",(jid,))
    second=ledger.claim('c'); assert second['generation']==2
    with pytest.raises(ValueError): ledger.finish(jid,first['lease_token'],'failed',error_class='source_unavailable')
    with pytest.raises(ValueError): ledger.finish(jid,second['lease_token'],'succeeded',batch_id=str(uuid4()))
    spec=dict(batch_id=str(uuid4()),connection_id=ctx['connection_id'],binding_version='1',data_type='inventory',source_kind='synthetic',scope=scope,window_start='2026-01-01T00:00:00Z',window_end='2026-01-02T00:00:00Z',expected_pages=1,expected_count=0,page_start=0,coverage_complete=False,coverage_kind='incremental',context=ctx)
    bid=repo.begin_batch(spec); repo.stage_page(bid,0,[]); assert repo.commit_batch(bid)['status']=='succeeded'
    ledger.heartbeat(jid,second['lease_token'])
    repo.register_binding(ctx['connection_id'],'2',{**ctx,'binding_version':'2'})
    with pytest.raises(ValueError): ledger.finish(jid,second['lease_token'],'succeeded',batch_id=bid)
    ledger.finish(jid,second['lease_token'],'needs_user',error_class='binding_changed')
    ledger.retry(jid)
    from ops_data.jobs.ledger import JobLedger
    assert JobLedger(ledger.database_url).get_job(jid)['status']=='queued'
    assert ledger.claim('d') is None

def test_success_requires_exact_batch(jobs):
    ledger,repo,sid,ctx,scope=jobs
    jid=ledger.enqueue(sid,'2026-01-01T00:00:00Z','2026-01-02T00:00:00Z'); job=ledger.claim('worker')
    spec=dict(batch_id=str(uuid4()),connection_id=ctx['connection_id'],binding_version='1',data_type='inventory',source_kind='synthetic',scope=scope,window_start='2026-01-01T00:00:00Z',window_end='2026-01-03T00:00:00Z',expected_pages=1,expected_count=0,page_start=0,coverage_complete=False,coverage_kind='incremental',context=ctx)
    bid=repo.begin_batch(spec); repo.stage_page(bid,0,[]); repo.commit_batch(bid)
    with pytest.raises(ValueError): ledger.finish(jid,job['lease_token'],'succeeded',batch_id=bid)
    spec.update(batch_id=str(uuid4()),window_end='2026-01-02T00:00:00Z')
    bid=repo.begin_batch(spec); repo.stage_page(bid,0,[]); repo.commit_batch(bid)
    ledger.finish(jid,job['lease_token'],'succeeded',batch_id=bid)
    assert ledger.get_job(jid)['status']=='succeeded'

def test_registration_validation_and_stale_stream_does_not_block(jobs):
    ledger,repo,sid,ctx,scope=jobs
    with pytest.raises(ValueError): ledger.register_stream(ctx['connection_id'],'1','inventory','synthetic',{'store_ids':[],'warehouse_ids':[]},'UTC',60)
    with pytest.raises(ValueError): ledger.register_stream(ctx['connection_id'],'1','inventory','wdt_api',scope,'UTC',60)
    with pytest.raises(ValueError): ledger.enqueue(sid,'2026-01-02T00:00:00Z','2026-01-01T00:00:00Z')
    old=ledger.enqueue(sid,'2026-01-01T00:00:00Z','2026-01-02T00:00:00Z')
    repo.register_binding(ctx['connection_id'],'2',{**ctx,'binding_version':'2'})
    new=ledger.register_stream(ctx['connection_id'],'2','inventory','synthetic',scope,'UTC',60)
    jid=ledger.enqueue(new,'2026-01-02T00:00:00Z','2026-01-03T00:00:00Z')
    job=ledger.claim('new'); assert job['job_id']==jid
    with pytest.raises(ValueError): ledger.finish(jid,job['lease_token'],'failed',error_class='customer raw value')
    ledger.finish(jid,job['lease_token'],'failed',error_class='source_unavailable')
    ledger.retry(jid); next_job=ledger.claim('retry'); assert next_job['generation']==2
    with repo._connect() as c:
        attempts=c.execute('SELECT status FROM ops_ingestion_job_attempts WHERE job_id=%s ORDER BY generation',(jid,)).fetchall()
        assert [a['status'] for a in attempts]==['failed','running']
    assert ledger.get_job(old)['status']=='queued'

def test_planner_slices_freezes_and_overlap():
    from ops_data.jobs.planner import history_plan, incremental_plan
    plan=history_plan('refunds','Asia/Shanghai',datetime(2026,5,1,13,tzinfo=timezone.utc),days=91)
    assert len(plan)==4
    assert all((b-a).total_seconds()<=30*86400 for a,b in plan)
    start=datetime(2026,1,1,tzinfo=timezone.utc); end=datetime(2026,1,2,tzinfo=timezone.utc)
    windows=incremental_plan('orders',start,end,overlap_seconds=60)
    assert windows[0][0].timestamp()==start.timestamp()-60
    assert windows[-1][1]==end

def test_claim_specific_job_and_attempt_batch_fencing(jobs):
    ledger,repo,sid,ctx,scope=jobs
    older=ledger.enqueue(sid,'2026-01-01T00:00:00Z','2026-01-02T00:00:00Z')
    target=ledger.enqueue(sid,'2026-01-02T00:00:00Z','2026-01-03T00:00:00Z')
    first=ledger.claim('demo',job_id=target)
    assert first['job_id']==target
    assert ledger.get_job(older)['status']=='queued'
    assert ledger.claim('other',job_id=target) is None
    spec=dict(batch_id=str(uuid4()),connection_id=ctx['connection_id'],binding_version='1',data_type='inventory',source_kind='synthetic',scope=scope,window_start='2026-01-02T00:00:00Z',window_end='2026-01-03T00:00:00Z',expected_pages=1,expected_count=0,page_start=0,coverage_complete=False,coverage_kind='incremental',context=ctx,job_id=target,lease_token=first['lease_token'])
    bid=repo.begin_batch(spec); repo.stage_page(bid,0,[]); assert repo.commit_batch(bid)['status']=='succeeded'
    with repo._connect() as c: c.execute("UPDATE ops_ingestion_jobs SET lease_until=now()-interval '1 second' WHERE job_id=%s",(target,))
    second=ledger.claim('new',job_id=target)
    with pytest.raises(ValueError): ledger.finish(target,second['lease_token'],'succeeded',batch_id=bid)
    spec.update(batch_id=str(uuid4()),lease_token=second['lease_token'])
    current=repo.begin_batch(spec); repo.stage_page(current,0,[])
    assert repo.commit_batch(current)['status']=='succeeded'
    ledger.finish(target,second['lease_token'],'succeeded',batch_id=current)
    assert ledger.get_job(target)['status']=='succeeded'
