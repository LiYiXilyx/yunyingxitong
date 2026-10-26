"""Local synthetic rehearsal only. Credentials enter through stdin, never argv."""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo
from .ingestion.repository import IngestionRepository, canonical, scope_value

NAMESPACE=UUID('ff495ba1-f075-40f6-a774-91508e73f356')

def wire(value): return value.astimezone(timezone.utc).isoformat().replace('+00:00','Z')

def build_demo(snapshot, now=None):
    version=str(snapshot['version'])
    if not version.isdigit() or int(version)<1: raise ValueError('demo_version_invalid')
    allowed=scope_value(snapshot['scope'])
    if not allowed['store_ids']: raise ValueError('demo_authorized_store_required')
    scope={'store_ids':[allowed['store_ids'][0]],'warehouse_ids':[]}
    end=(now or datetime.now(timezone.utc)).astimezone(ZoneInfo('Asia/Shanghai')).replace(hour=0,minute=0,second=0,microsecond=0)
    start=end-timedelta(days=1); beginning,ending=wire(start),wire(end)
    # Keep one authoritative synthetic connection per scope; version each batch.
    cid=str(uuid5(NAMESPACE,canonical(['t05-synthetic-v1',scope])))
    ctx=dict(source_kind='synthetic',connection_id=cid,binding_version=version,mapping_version='t05-synthetic-v1',source_timezone='Asia/Shanghai',mapping_confirmed=True,store_bindings={'SYNTHETIC-SHOP':scope['store_ids'][0]},warehouse_bindings={},allowed_scope=scope,order_status_map={'SYNTHETIC-PAID':'paid'})
    spec=dict(batch_id=str(uuid5(NAMESPACE,canonical([cid,version,beginning,ending,'orders-v1']))),connection_id=cid,binding_version=version,data_type='orders',source_kind='synthetic',scope=scope,window_start=beginning,window_end=ending,expected_pages=1,expected_count=3,page_start=0,coverage_complete=True,coverage_kind='full',context=ctx,business_coverage=dict(start=beginning,end=ending,timezone='Asia/Shanghai',confirmed=True,synthetic=True,description='Only generated fixture records; no ERP coverage claim'))
    records=[]
    # Platform A split over two masters; master two merges A and B.
    for mid,lines in [('SYNTHETIC-M1',[('L1','A','1')]),('SYNTHETIC-M2',[('L2','A','2'),('L3','B','3')]),('SYNTHETIC-M3',[('L1-COPY','A','1')])]:
        rows=[dict(orderId=lid,srcTid='SYNTHETIC-'+tid,srcOid='L1' if lid=='L1-COPY' else lid,num=qty,apiSpecNo='SYNTHETIC-SKU') for lid,tid,qty in lines]
        records.append(dict(master=dict(tradeId=mid,shopId='SYNTHETIC-SHOP',tradeStatusCode='SYNTHETIC-PAID',payTime=wire(start+timedelta(hours=9)),modified=wire(start+timedelta(hours=10))),lines=rows))
    return {'spec':spec,'records':records}

def run_demo(snapshot, token, database_url):
    from .jobs.ledger import JobLedger
    from .jobs.health_scan import HealthScanner
    from .delivery.health import HealthOutbox, NocoBaseHealthTransport
    plan=build_demo(snapshot); spec=plan['spec']; cid=spec['connection_id']
    repo=IngestionRepository(database_url);repo.migrate()
    ledger=JobLedger(database_url);ledger.migrate()
    scanner=HealthScanner(database_url);scanner.migrate()
    repo.register_binding(cid,spec['binding_version'],spec['context'])
    bid=repo.begin_batch(spec);repo.stage_page(bid,0,plan['records'])
    receipt=repo.commit_batch(bid)
    if receipt['status']!='succeeded': raise ValueError('demo_batch_incomplete')
    metrics=repo.materialize_metrics(bid)
    stream_ids=[]
    for kind in ('orders','refunds'):
        sid=ledger.register_stream(cid,spec['binding_version'],kind,'synthetic',spec['scope'],'Asia/Shanghai',172800)
        stream_ids.append(sid)
        if kind=='refunds':
            jid=ledger.enqueue(sid,spec['window_start'],spec['window_end'],'history')
            job=ledger.get_job(jid)
            if job['status']=='queued':
                attempt=ledger.claim('t05-synthetic-demo',job_id=jid)
                if not attempt: raise ValueError('demo_job_not_claimed')
                ledger.finish(jid,attempt['lease_token'],'needs_user',error_class='needs_user')
    scanner.scan(connection_id=cid)
    outbox=HealthOutbox(database_url)
    transport=NocoBaseHealthTransport('http://nocobase:80',token,internal_origins=('http://nocobase:80',))
    receipts=0
    for sid in stream_ids:
        while outbox.pending(stream_id=sid):
            if not outbox.deliver_one(transport,stream_id=sid): raise ValueError('demo_health_delivery_unconfirmed')
            receipts+=1
    pending=sum(p['batch_id']==bid for p in repo.pending_evaluations())
    return dict(source_kind='synthetic',batch_id=bid,fact_count=receipt['fact_count'],quality=metrics['quality'],values=metrics['values'],pending_evaluations=str(pending),health_receipts=str(receipts))

def main():
    try:
        data=json.load(sys.stdin)
        result=run_demo(data['snapshot'],data['token'],os.environ['OPS_DATABASE_URL'])
        print(json.dumps(result,ensure_ascii=False))
    except Exception:
        print('T05合成演练失败；未输出原始数据、凭据或数据库错误。',file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':sys.exit(main())
