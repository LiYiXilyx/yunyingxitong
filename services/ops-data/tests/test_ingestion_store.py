"""Real PostgreSQL; no DSN means failure, never a skip."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest


def test_repository_contract_exists():
    import importlib.util
    assert importlib.util.find_spec('ops_data.ingestion.repository'), 'durable ingestion repository missing'


@pytest.fixture
def setup_store():
    from ops_data.ingestion.repository import IngestionRepository
    dsn = os.environ.get('OPS_TEST_DATABASE_URL')
    assert dsn, 'OPS_TEST_DATABASE_URL required for ingestion verification'
    repo = IngestionRepository(dsn)
    repo.migrate()
    cid, wid = str(uuid.uuid4()), str(uuid.uuid4())
    scope = {'store_ids': [], 'warehouse_ids': [wid]}
    context = dict(source_kind='synthetic', connection_id=cid, binding_version='1', mapping_version='1', source_timezone='UTC', mapping_confirmed=True, store_bindings={}, warehouse_bindings={'W':wid}, allowed_scope=scope, order_status_map={})
    repo.register_binding(cid, '1', context)
    def spec(**kw):
        return dict(batch_id=str(uuid.uuid4()), connection_id=cid, binding_version='1', data_type='inventory', source_kind='synthetic', window_start='2026-01-01T00:00:00Z', window_end='2026-01-02T00:00:00Z', scope=scope, expected_pages=1, expected_count=1, page_start=0, coverage_complete=False, coverage_kind='incremental', context=context, **kw)
    row = dict(warehouseNo='W', specId='S', specNo='SKU', availableNum='4', modified='2026-01-01T12:00:00Z')
    yield repo, spec, row, scope
    with repo._connect() as conn:
        conn.execute('DELETE FROM ops_ingestion_bindings WHERE connection_id=%s', (cid,))


def test_atomic_recovery_idempotence_and_snapshot(setup_store):
    repo, spec, row, scope = setup_store
    s = spec(); bid = repo.begin_batch(s)
    assert repo.begin_batch(s) == bid
    assert repo.commit_batch(bid)['status'] == 'partial'
    assert repo.get_cursor(s['connection_id'], 'inventory', scope) is None
    repo.stage_page(bid, 0, [row]); repo.stage_page(bid, 0, [row])
    with pytest.raises(ValueError): repo.stage_page(bid, 0, [{**row,'availableNum':'8'}])
    with ThreadPoolExecutor(max_workers=3) as pool:
        receipts = list(pool.map(lambda _: repo.commit_batch(bid), range(3)))
    assert all(r == receipts[0] for r in receipts)
    assert receipts[0]['status'] == 'succeeded'
    from ops_data.ingestion.repository import IngestionRepository
    recovered = IngestionRepository(repo.database_url)
    assert bid in [r['batch_id'] for r in recovered.pending_evaluations()]
    assert len(repo.current_facts(s['connection_id'], 'inventory', scope)) == 1
    snap = repo.materialize_metrics(bid)
    assert snap['quality'] == 'insufficient'
    assert snap == repo.materialize_metrics(bid)


def test_source_timestamp_conflict_and_old_version(setup_store):
    repo, spec, row, scope = setup_store
    def commit(r):
        s=spec(); bid=repo.begin_batch(s); repo.stage_page(bid,0,[r]); return bid,repo.commit_batch(bid)
    bid,_=commit(row)
    _,conflict=commit({**row,'availableNum':'99'})
    assert conflict['status'] == 'partial'
    assert 'source_time_conflict' in conflict['issues']
    _,old=commit({**row,'availableNum':'1','modified':'2026-01-01T11:00:00Z'})
    assert old['status'] == 'succeeded'
    assert repo.current_facts(spec()['connection_id'],'inventory',scope)[0]['source_updated_at']=='2026-01-01T12:00:00.000000Z'
    assert repo.current_facts(spec()['connection_id'],'inventory',scope,source_kind='wdt_api') == []


def test_binding_and_duplicate_page_guard(setup_store):
    repo,spec,row,scope=setup_store
    s=spec(); s.update(expected_pages=2,expected_count=2)
    bid=repo.begin_batch(s); repo.stage_page(bid,0,[row]); repo.stage_page(bid,1,[row])
    assert repo.commit_batch(bid)['status']=='partial'
    with pytest.raises(ValueError): repo.register_binding(s['connection_id'],'1',{**s['context'],'mapping_version':'2'})
    newer={**s['context'],'binding_version':'2'}
    repo.register_binding(s['connection_id'],'2',newer)
    with pytest.raises(ValueError): repo.register_binding(s['connection_id'],'1',s['context'])
    assert repo.get_cursor(s['connection_id'],'inventory',scope) is None


def test_binding_snapshots_are_retained(setup_store):
    repo,spec,_,_=setup_store
    s=spec()
    repo.register_binding(s['connection_id'],'2',{**s['context'],'binding_version':'2'})
    with repo._connect() as c:
        rows=c.execute('SELECT binding_version,context FROM ops_ingestion_binding_versions WHERE connection_id=%s ORDER BY binding_version',(s['connection_id'],)).fetchall()
    assert [str(r['binding_version']) for r in rows]==['1','2']
    assert rows[0]['context']==s['context']


def test_pg_exception_rolls_back_facts_cursor_pending(setup_store):
    repo,spec,row,scope=setup_store
    s=spec(); bid=repo.begin_batch(s); repo.stage_page(bid,0,[row])
    # A server-side constraint failure late in commit simulates process/DB failure.
    with repo._connect() as c:
        c.execute('INSERT INTO ops_ingestion_pending_evaluations(batch_id) VALUES (%s)',(bid,))
    import psycopg
    with pytest.raises(psycopg.errors.UniqueViolation): repo.commit_batch(bid)
    assert repo.get_batch(bid)['status']=='staging'
    assert repo.current_facts(s['connection_id'],'inventory',scope)==[]
    assert repo.get_cursor(s['connection_id'],'inventory',scope) is None
    with repo._connect() as c:
        c.execute('DELETE FROM ops_ingestion_pending_evaluations WHERE batch_id=%s',(bid,))
    assert repo.commit_batch(bid)['status']=='succeeded'


def test_completed_snapshot_does_not_include_later_facts(setup_store):
    repo,spec,row,scope=setup_store
    s=spec(); first=repo.begin_batch(s); repo.stage_page(first,0,[row]); repo.commit_batch(first)
    newer=spec(); newer['window_end']='2026-01-03T00:00:00Z'
    second=repo.begin_batch(newer); repo.stage_page(second,0,[{**row,'modified':'2026-01-02T12:00:00Z','availableNum':'50'}]); repo.commit_batch(second)
    snap=repo.materialize_metrics(first)
    assert second not in snap['source_batch_ids']
    assert repo.get_cursor(s['connection_id'],'inventory',scope)['batch_id']==second


def test_query_window_alone_is_not_business_coverage(setup_store):
    repo,spec,row,_=setup_store
    s=spec(); s.update(coverage_complete=True,coverage_kind='full')
    bid=repo.begin_batch(s); repo.stage_page(bid,0,[row]); repo.commit_batch(bid)
    assert repo.materialize_metrics(bid)['quality']=='insufficient'


def test_explicit_business_coverage_and_concurrent_snapshot(setup_store):
    repo,spec,row,scope=setup_store
    s=spec(); s.update(coverage_complete=True,coverage_kind='full',business_coverage={'start':s['window_start'],'end':s['window_end'],'timezone':'UTC','confirmed':True})
    bid=repo.begin_batch(s); repo.stage_page(bid,0,[row]); repo.commit_batch(bid)
    with ThreadPoolExecutor(max_workers=3) as pool:
        snapshots=list(pool.map(lambda _:repo.materialize_metrics(bid),range(3)))
    assert snapshots[0]['quality']=='complete'
    assert snapshots[0]['scope']==scope
    assert all(snap==snapshots[0] for snap in snapshots)


def test_binding_source_scope_rejected(setup_store):
    repo,spec,row,scope=setup_store
    s=spec(); s['source_kind']='wdt_api'; s.update(job_id=str(uuid.uuid4()),lease_token=str(uuid.uuid4()))
    with pytest.raises(ValueError,match='binding_mismatch'): repo.begin_batch(s)
    s=spec(); s['scope']={'store_ids':[],'warehouse_ids':[str(uuid.uuid4())]}
    with pytest.raises(ValueError,match='binding_mismatch'): repo.begin_batch(s)
    with pytest.raises(ValueError,match='scope_forbidden'): repo.current_facts(s['connection_id'],'inventory',s['scope'])


def test_pending_batch_cannot_commit_after_binding_changes(setup_store):
    repo,spec,row,scope=setup_store
    s=spec(); bid=repo.begin_batch(s); repo.stage_page(bid,0,[row])
    repo.register_binding(s['connection_id'],'2',{**s['context'],'binding_version':'2'})
    receipt=repo.commit_batch(bid)
    assert receipt=={'batch_id':bid,'status':'partial','issues':['binding_changed']}
    assert repo.current_facts(s['connection_id'],'inventory',scope)==[]
    assert bid not in [x['batch_id'] for x in repo.pending_evaluations()]


def test_older_window_and_facts_do_not_regress_cursor(setup_store):
    repo,spec,row,scope=setup_store
    s=spec(); s['window_end']='2026-01-04T00:00:00Z'
    first=repo.begin_batch(s); repo.stage_page(first,0,[row]); repo.commit_batch(first)
    old=spec(); second=repo.begin_batch(old)
    repo.stage_page(second,0,[{**row,'modified':'2026-01-01T11:00:00Z'}]); repo.commit_batch(second)
    assert repo.get_cursor(s['connection_id'],'inventory',scope)['batch_id']==first
    assert repo.current_facts(s['connection_id'],'inventory',scope)[0]['data']['available_units']=='4'


def test_migration_failure_is_redacted(monkeypatch,capsys):
    from ops_data.ingestion.migrate import main
    monkeypatch.delenv('OPS_DATABASE_URL',raising=False)
    assert main()==1
    assert capsys.readouterr().err=='Ingestion migration failed\n'


def test_snapshot_does_not_resurrect_old_store_membership(setup_store):
    repo,spec,_,_=setup_store
    s=spec(); stores=[str(uuid.uuid4()),str(uuid.uuid4())]
    ctx={**s['context'],'binding_version':'2','allowed_scope':{'store_ids':stores,'warehouse_ids':[]},'store_bindings':{'A':stores[0],'B':stores[1]},'order_status_map':{'1':'paid'}}
    repo.register_binding(s['connection_id'],'2',ctx)
    def commit(shop,time,scope,count=1):
        b=spec(); b.update(binding_version='2',context=ctx,data_type='orders',scope=scope,expected_count=count)
        bid=repo.begin_batch(b)
        rows=[{'master':{'tradeId':'T','shopId':shop,'tradeStatusCode':'1','payTime':'2026-01-01T00:00:00Z','modified':time},'lines':[{'orderId':'L','srcTid':'P','srcOid':'PL','num':'1','apiSpecNo':'S'}]}] if count else []
        repo.stage_page(bid,0,rows); assert repo.commit_batch(bid)['status']=='succeeded'
        return bid
    first=commit('A','2026-01-01T01:00:00Z',ctx['allowed_scope'])
    commit('B','2026-01-01T02:00:00Z',ctx['allowed_scope'])
    last=commit('A','2026-01-01T03:00:00Z',{'store_ids':[stores[0]],'warehouse_ids':[]},0)
    snap=repo.materialize_metrics(last)
    # No current fact belongs to A; the old A version must not reappear.
    assert first not in snap['source_batch_ids']


def test_mapping_upgrade_reinterprets_same_source_time_and_hides_old_facts(setup_store):
    repo,spec,row,scope=setup_store
    s=spec(); first=repo.begin_batch(s); repo.stage_page(first,0,[row]); repo.commit_batch(first)
    old_snapshot=repo.materialize_metrics(first)
    ctx={**s['context'],'binding_version':'2','mapping_version':'2'}
    repo.register_binding(s['connection_id'],'2',ctx)
    assert repo.current_facts(s['connection_id'],'inventory',scope)==[]
    assert repo.get_cursor(s['connection_id'],'inventory',scope) is None
    empty=spec(); empty.update(binding_version='2',context=ctx,expected_count=0)
    eb=repo.begin_batch(empty); repo.stage_page(eb,0,[]); repo.commit_batch(eb)
    assert repo.materialize_metrics(eb)['source_batch_ids']==[]
    newer=spec(); newer.update(binding_version='2',context=ctx)
    nb=repo.begin_batch(newer); repo.stage_page(nb,0,[{**row,'availableNum':'5'}])
    assert repo.commit_batch(nb)['status']=='succeeded'
    assert repo.current_facts(s['connection_id'],'inventory',scope)[0]['data']['available_units']=='5'
    assert repo.materialize_metrics(first)==old_snapshot


def test_expired_job_attempt_cannot_commit_any_usable_state(setup_store):
    from ops_data.jobs.ledger import JobLedger
    repo,spec,row,scope=setup_store
    s=spec(); jobs=JobLedger(repo.database_url); jobs.migrate()
    stream=jobs.register_stream(s['connection_id'],'1','inventory','synthetic',scope,'UTC',3600)
    jid=jobs.enqueue(stream,s['window_start'],s['window_end'])
    attempt=jobs.claim('store-fence',job_id=jid)
    s.update(job_id=jid,lease_token=attempt['lease_token'])
    bid=repo.begin_batch(s); repo.stage_page(bid,0,[row])
    with repo._connect() as c:
        c.execute("UPDATE ops_ingestion_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE job_id=%s",(jid,))
    assert jobs.claim('store-reclaim',job_id=jid)['lease_token']!=attempt['lease_token']
    with pytest.raises(ValueError,match='lease_rejected'): repo.commit_batch(bid)
    assert repo.current_facts(s['connection_id'],'inventory',scope)==[]
    assert repo.get_cursor(s['connection_id'],'inventory',scope) is None
    assert bid not in [r['batch_id'] for r in repo.pending_evaluations()]


def test_wdt_batch_requires_job_attempt(setup_store):
    repo,spec,_,_=setup_store
    s=spec(); ctx={**s['context'],'source_kind':'wdt_api','binding_version':'2'}
    repo.register_binding(s['connection_id'],'2',ctx)
    s.update(context=ctx,binding_version='2',source_kind='wdt_api')
    with pytest.raises(ValueError,match='job_required'): repo.begin_batch(s)


def test_status_mapping_upgrade_same_modified_and_attempt_mismatch(setup_store):
    repo,spec,_,_=setup_store
    s=spec(); store=str(uuid.uuid4()); scope={'store_ids':[store],'warehouse_ids':[]}
    ctx={**s['context'],'binding_version':'2','mapping_version':'2','allowed_scope':scope,'store_bindings':{'A':store},'order_status_map':{'X':'paid'}}
    repo.register_binding(s['connection_id'],'2',ctx)
    row={'master':{'tradeId':'T','shopId':'A','tradeStatusCode':'X','payTime':'2026-01-01T00:00:00Z','modified':'2026-01-01T01:00:00Z'},'lines':[{'orderId':'L','srcTid':'P','srcOid':'PL','num':'1','apiSpecNo':'S'}]}
    def submit(context):
        b=spec();b.update(binding_version=context['binding_version'],context=context,data_type='orders',scope=scope)
        bid=repo.begin_batch(b);repo.stage_page(bid,0,[row]);return bid,repo.commit_batch(bid)
    old,_=submit(ctx)
    ctx={**ctx,'binding_version':'3','mapping_version':'3','order_status_map':{'X':'void'}}
    repo.register_binding(s['connection_id'],'3',ctx)
    new,receipt=submit(ctx)
    assert receipt['status']=='succeeded'
    assert repo.current_facts(s['connection_id'],'orders',scope)[0]['data']['status']=='void'
    assert repo.materialize_metrics(new)['source_batch_ids']==[new]
    assert repo.materialize_metrics(old)['source_batch_ids']==[old]


def test_job_window_mismatch_cannot_commit(setup_store):
    from ops_data.jobs.ledger import JobLedger
    repo,spec,row,scope=setup_store;s=spec();jobs=JobLedger(repo.database_url);jobs.migrate()
    stream=jobs.register_stream(s['connection_id'],'1','inventory','synthetic',scope,'UTC',3600)
    jid=jobs.enqueue(stream,s['window_start'],s['window_end']);attempt=jobs.claim('mismatch',job_id=jid)
    s.update(job_id=jid,lease_token=attempt['lease_token'],window_end='2026-01-03T00:00:00Z')
    bid=repo.begin_batch(s);repo.stage_page(bid,0,[row])
    with pytest.raises(ValueError,match='job_batch_mismatch'):repo.commit_batch(bid)
    assert repo.get_cursor(s['connection_id'],'inventory',scope) is None


def test_lease_expiring_during_normalization_rolls_back(setup_store,monkeypatch):
    import time
    from ops_data.jobs.ledger import JobLedger
    import ops_data.ingestion.normalize as normalizer
    repo,spec,row,scope=setup_store;s=spec();jobs=JobLedger(repo.database_url);jobs.migrate()
    stream=jobs.register_stream(s['connection_id'],'1','inventory','synthetic',scope,'UTC',3600)
    jid=jobs.enqueue(stream,s['window_start'],s['window_end']);attempt=jobs.claim('slow',lease_seconds=1,job_id=jid)
    s.update(job_id=jid,lease_token=attempt['lease_token']);bid=repo.begin_batch(s);repo.stage_page(bid,0,[row])
    original=normalizer.normalize_records
    def slow(*args):
        time.sleep(1.1)
        return original(*args)
    monkeypatch.setattr(normalizer,'normalize_records',slow)
    with pytest.raises(ValueError,match='lease_rejected'):repo.commit_batch(bid)
    assert repo.current_facts(s['connection_id'],'inventory',scope)==[]
    assert repo.get_cursor(s['connection_id'],'inventory',scope) is None
    assert bid not in [r['batch_id'] for r in repo.pending_evaluations()]


def test_completed_job_batch_replays_original_receipt_after_restart(setup_store):
    from ops_data.jobs.ledger import JobLedger
    repo,spec,row,scope=setup_store;s=spec();jobs=JobLedger(repo.database_url);jobs.migrate()
    stream=jobs.register_stream(s['connection_id'],'1','inventory','synthetic',scope,'UTC',3600)
    jid=jobs.enqueue(stream,s['window_start'],s['window_end']);attempt=jobs.claim('replay',job_id=jid)
    s.update(job_id=jid,lease_token=attempt['lease_token'])
    bid=repo.begin_batch(s);repo.stage_page(bid,0,[row]);receipt=repo.commit_batch(bid)
    jobs.finish(jid,attempt['lease_token'],'succeeded',batch_id=bid)
    restarted=type(repo)(repo.database_url)
    assert restarted.commit_batch(bid)==receipt
    assert len([r for r in restarted.pending_evaluations() if r['batch_id']==bid])==1
