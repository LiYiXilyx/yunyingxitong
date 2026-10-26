"""Synthetic demo planning is deterministic, private and uses explicit coverage."""
import unittest
from datetime import datetime, timezone
from ops_data.demo_t05 import build_demo
from ops_data.ingestion.normalize import normalize_records
from ops_data.metrics.materialize import materialize_facts

class DemoTests(unittest.TestCase):
 def test_demo_split_merge_and_repeat(self):
  snapshot={'version':7,'scope':{'store_ids':['11111111-1111-4111-8111-111111111111'],'warehouse_ids':[]}}
  plan=build_demo(snapshot,datetime(2026,10,26,1,tzinfo=timezone.utc))
  self.assertEqual(plan,build_demo(snapshot,datetime(2026,10,26,8,tzinfo=timezone.utc)))
  spec=plan['spec']; result=normalize_records('orders',plan['records'],spec['context'])
  self.assertEqual(result.issues,[])
  metrics=materialize_facts(result.facts,data_type='orders',window_start=spec['window_start'],window_end=spec['window_end'],timezone='Asia/Shanghai',coverage_complete=True)
  self.assertEqual(metrics['quality'],'complete')
  self.assertEqual(metrics['values']['paid_platform_orders'],'2')
  self.assertEqual(metrics['values']['paid_units'],'6')
  self.assertTrue(spec['business_coverage']['synthetic'])
  self.assertNotIn('token',str(plan))
 def test_binding_upgrade_reuses_connection_but_not_batch(self):
  snapshot={'version':7,'scope':{'store_ids':['11111111-1111-4111-8111-111111111111'],'warehouse_ids':[]}}
  old=build_demo(snapshot)['spec']; new=build_demo({**snapshot,'version':8})['spec']
  self.assertEqual(old['connection_id'],new['connection_id'])
  self.assertNotEqual(old['batch_id'],new['batch_id'])
 def test_no_authorized_store_rejected(self):
  with self.assertRaises(ValueError): build_demo({'version':1,'scope':{'store_ids':[],'warehouse_ids':[]}})

class DemoFlowTests(unittest.TestCase):
 def test_flow_only_claims_and_delivers_owned_records(self):
  from unittest.mock import patch, MagicMock
  from ops_data.demo_t05 import run_demo
  snapshot={'version':'7','scope':{'store_ids':['11111111-1111-4111-8111-111111111111'],'warehouse_ids':[]}}
  repo=MagicMock();repo.begin_batch.return_value='batch';repo.commit_batch.return_value={'status':'succeeded','fact_count':'4'}
  repo.materialize_metrics.return_value={'quality':'complete','values':{'paid_platform_orders':'2','paid_units':'6'}}
  repo.pending_evaluations.return_value=[{'batch_id':'other'},{'batch_id':'batch'}]
  ledger=MagicMock();ledger.register_stream.side_effect=['owned-orders','owned-refunds'];ledger.enqueue.return_value='owned-job'
  ledger.get_job.return_value={'status':'queued'};ledger.claim.return_value={'lease_token':'private-lease'}
  outbox=MagicMock();outbox.pending.side_effect=[['command'],[],['command'],[]];outbox.deliver_one.return_value=True
  with patch('ops_data.demo_t05.IngestionRepository',return_value=repo),patch('ops_data.jobs.ledger.JobLedger',return_value=ledger),patch('ops_data.jobs.health_scan.HealthScanner') as scanner,patch('ops_data.delivery.health.HealthOutbox',return_value=outbox),patch('ops_data.delivery.health.NocoBaseHealthTransport'):
   result=run_demo(snapshot,'PRIVATE-TOKEN','PRIVATE-DSN')
  ledger.claim.assert_called_once_with('t05-synthetic-demo',job_id='owned-job')
  self.assertEqual([c.kwargs for c in outbox.deliver_one.call_args_list],[{'stream_id':'owned-orders'},{'stream_id':'owned-refunds'}])
  self.assertEqual(result['pending_evaluations'],'1')
  self.assertEqual(result['health_receipts'],'2')
  self.assertNotIn('PRIVATE',str(result))
  self.assertIn('connection_id',scanner.return_value.scan.call_args.kwargs)
