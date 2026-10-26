import unittest
from copy import deepcopy
from ops_data.ingestion.normalize import normalize_records
from ops_data.metrics.materialize import materialize_facts

S='11111111-1111-4111-8111-111111111111'
W='22222222-2222-4222-8222-222222222222'
def context():
 return dict(source_kind='synthetic',connection_id=S,binding_version='1',mapping_version='1',source_timezone='Asia/Shanghai',mapping_confirmed=True,store_bindings={'s':S},warehouse_bindings={'w':W},allowed_scope={'store_ids':[S],'warehouse_ids':[W]},order_status_map={'ok':'paid','cancel':'void'})
def order(oid='o',tid='t',qty='0.1',status='ok',modified='2026-10-25T00:00:00Z'):
 return {'master':{'tradeId':'m','shopId':'s','tradeStatusCode':status,'payTime':'2026-10-24 09:00:00','modified':modified},'lines':[{'orderId':oid,'srcTid':tid,'srcOid':oid,'num':qty,'apiSpecNo':'sku'}]}
def metrics(facts,kind='orders',complete=True):
 return materialize_facts(facts,data_type=kind,window_start='2026-10-23T00:00:00Z',window_end='2026-10-26T00:00:00Z',timezone='Asia/Shanghai',coverage_complete=complete)
class NormalizeTests(unittest.TestCase):
 def test_split_orders_count_once_decimal_and_latest_correction(self):
  r=normalize_records('orders',[order(),order('o2',qty='0.2'),order()],context())
  self.assertEqual(r.issues,[])
  self.assertEqual(len(r.facts),2)
  self.assertEqual(metrics(r.facts)['values']['paid_platform_orders'],'1')
  self.assertEqual(metrics(r.facts)['values']['paid_units'],'0.3')
  correction=normalize_records('orders',[order(status='cancel',modified='2026-10-25T01:00:00Z')],context()).facts
  self.assertEqual(metrics(r.facts+correction)['values']['paid_units'],'0.2')
 def test_unknown_mapping_and_missing_id_are_issues(self):
  c=context();c['mapping_confirmed']=False
  self.assertTrue(normalize_records('orders',[order()],c).issues)
  row=order();del row['lines'][0]['srcTid']
  self.assertTrue(normalize_records('orders',[row],context()).issues)
 def test_dst_ambiguous_and_nonexistent_rejected(self):
  for value in ['2026-11-01 01:30:00','2026-03-08 02:30:00']:
   c=context();c['source_timezone']='America/New_York';row=order();row['master']['payTime']=value
   self.assertTrue(normalize_records('orders',[row],c).issues)
 def test_shared_inventory_and_refund_origin(self):
  r=normalize_records('inventory',[dict(warehouseNo='w',specId='id',specNo='sku',availableNum='1.20',modified='2026-10-25T00:00:00Z')],context())
  self.assertEqual(metrics(r.facts,'inventory')['values']['available_units'],'1.20')
  c=context();c['refund_order_bindings']={'p:t':S}
  row=dict(platformId='p',refundNo='r',tid='t',modified='2026-10-25T00:00:00Z',created='2026-10-24T00:00:00Z',status='x',erpReturnId='return')
  r=normalize_records('refunds',[row,row],c)
  self.assertEqual(metrics(r.facts,'refunds')['values']['refund_applications'],'1')
  del c['refund_order_bindings'];self.assertTrue(normalize_records('refunds',[row],c).issues)
 def test_incomplete_never_zero(self):
  self.assertEqual(metrics([],complete=False)['values'],{})
 def test_bom_cycle_and_positive_multiplier(self):
  c=context();c['catalog_mapping_confirmed']=True
  rows=[dict(specId='a',modified='2026-10-25T00:00:00Z',components=[dict(specId='b',quantity='2')]),dict(specId='b',modified='2026-10-25T00:00:00Z',components=[dict(specId='a',quantity='1')])]
  self.assertTrue(normalize_records('catalog',rows,c).issues)
  rows[1]['components']=[]
  self.assertEqual(normalize_records('catalog',rows,c).issues,[])
 def test_same_platform_line_across_erp_split_does_not_double_units(self):
  a=order();b=order('other');b['lines'][0]['srcOid']='o'
  facts=normalize_records('orders',[a,b],context()).facts
  self.assertEqual(metrics(facts)['values']['paid_units'],'0.1')
 def test_large_decimal_is_exact(self):
  facts=normalize_records('orders',[order(qty='123456789012345678901234567890.1'),order('b',qty='0.2')],context()).facts
  self.assertEqual(metrics(facts)['values']['paid_units'],'123456789012345678901234567890.3')
 def test_equal_timestamp_conflict_is_private(self):
  r=normalize_records('orders',[order(),order(qty='PRIVATE_CUSTOMER')],context())
  self.assertTrue(r.issues);self.assertNotIn('PRIVATE',str(r.issues));self.assertEqual(r.facts,[])
  a=normalize_records('orders',[order()],context()).facts
  b=normalize_records('orders',[order(qty='0.2')],context()).facts
  self.assertEqual(metrics(a+b)['quality'],'insufficient')
 def test_old_version_does_not_override_new(self):
  a=normalize_records('orders',[order(status='cancel',modified='2026-10-25T01:00:00Z'),order()],context())
  self.assertEqual(metrics(a.facts)['values']['paid_platform_orders'],'0')
 def test_refund_ambiguous_binding_and_bom_cross_connection(self):
  c=context();c['refund_order_bindings']={'p:t':[S,W]}
  r=normalize_records('refunds',[dict(platformId='p',refundNo='r',tid='t',modified='2026-10-25T00:00:00Z',created='2026-10-25T00:00:00Z',status='x')],c)
  self.assertTrue(r.issues)
  c=context();c['catalog_mapping_confirmed']=True
  for component in [dict(specId='b',quantity='0'),dict(specId='b',quantity='2',connection_id=W)]:
   self.assertTrue(normalize_records('catalog',[dict(specId='a',modified='2026-10-25T00:00:00Z',components=[component])],c).issues)
 def test_fractional_timestamp_ordering(self):
  r=normalize_records('orders',[order(status='cancel',modified='2026-10-25T00:00:00.1Z'),order()],context())
  self.assertEqual(metrics(r.facts)['values']['paid_platform_orders'],'0')

class ReconciliationTests(unittest.TestCase):
 def test_reconcile_contract_and_classifications(self):
  import importlib.util
  self.assertIsNotNone(importlib.util.find_spec('ops_data.metrics.reconcile'))
  from ops_data.metrics.reconcile import reconcile_records
  window={'start':'2026-10-01','end':'2026-10-02','timezone':'Asia/Shanghai'}
  result=reconcile_records([{'id':'secret-customer','quantity':'1.00'},{'id':'missing','quantity':None},{'id':'mismatch','quantity':None}], [{'id':'secret-customer','quantity':'1'},{'id':'extra','quantity':'0'},{'id':'mismatch','quantity':'0'}],key_fields=['id'],value_fields=['quantity'],source_window=window,target_window=window)
  self.assertEqual(result['counts']['matched'],1)
  self.assertEqual(result['counts']['missing_field'],1)
  self.assertEqual(result['counts']['value_mismatch'],0)
  self.assertEqual(result['counts']['missing_in_source'],1)
  self.assertEqual(result['counts']['missing_in_target'],1)
  self.assertNotIn('secret-customer',str(result))
  self.assertTrue(all(d['unexplained'] for d in result['differences']))
 def test_reconcile_duplicate_and_different_windows(self):
  from ops_data.metrics.reconcile import reconcile_records
  result=reconcile_records([{'id':'x','n':'2'},{'id':'x','n':'2'}],[{'id':'x','n':'2'}],key_fields=['id'],value_fields=['n'],source_window={},target_window={})
  self.assertEqual(result['counts']['duplicate_key'],1)
  result=reconcile_records([],[],key_fields=['id'],value_fields=['n'],source_window={'end':'a'},target_window={'end':'b'})
  self.assertEqual(result['quality'],'insufficient'); self.assertEqual(result['issues'],['query_window_mismatch'])

class FailClosedTests(unittest.TestCase):
 def test_non_boolean_confirmation_and_unknown_source_status(self):
  for key,value in [('mapping_confirmed',1),('source_kind','unknown')]:
   c=context();c[key]=value
   self.assertTrue(normalize_records('orders',[order()],c).issues)
  self.assertTrue(normalize_records('orders',[order(status='UNMAPPED')],context()).issues)
 def test_malformed_context_is_static_issue(self):
  for c in [None,[],{}]:
   self.assertTrue(normalize_records('orders',[None],c).issues)
 def test_mixed_source_is_insufficient(self):
  a=normalize_records('orders',[order()],context()).facts
  c=context();c['source_kind']='manual_import'
  b=normalize_records('orders',[order('b')],c).facts
  self.assertEqual(metrics(a+b)['issues'],['mixed_source_kinds'])
 def test_synthetic_order_and_inventory_reconciliation(self):
  from ops_data.metrics.reconcile import reconcile_records
  facts=normalize_records('orders',[order(),order('other')],context()).facts
  actual=metrics(facts)['values']['paid_platform_orders']
  kw=dict(key_fields=['metric'],value_fields=['value'],source_window={'day':'2026-10-24'},target_window={'day':'2026-10-24'})
  self.assertEqual(reconcile_records([{'metric':'orders','value':'2'}],[{'metric':'orders','value':actual}],**kw)['counts']['value_mismatch'],1)
  self.assertEqual(reconcile_records([{'metric':'orders','value':'1'}],[{'metric':'orders','value':actual}],**kw)['counts']['matched'],1)
  self.assertEqual(reconcile_records([{'metric':'inventory','value':'1.20'}],[{'metric':'inventory','value':'1.2'}],**kw)['counts']['matched'],1)

class ReconcileMissingTests(unittest.TestCase):
 def test_both_none_are_missing_and_insufficient(self):
  from ops_data.metrics.reconcile import reconcile_records
  kw=dict(key_fields=['id'],value_fields=['amount'],source_window={},target_window={})
  for target in [None,'0']:
   r=reconcile_records([{'id':'x','amount':None}],[{'id':'x','amount':target}],**kw)
   self.assertEqual(r['quality'],'insufficient');self.assertEqual(r['counts']['missing_field'],1)
   self.assertEqual(r['counts']['matched'],0)
 def test_invalid_decimal_and_structure_insufficient(self):
  from ops_data.metrics.reconcile import reconcile_records
  kw=dict(key_fields=['id'],value_fields=['amount'],source_window={},target_window={})
  for rows in [[{'id':'x','amount':'SECRET_BAD_NUMBER'}],[None]]:
   r=reconcile_records(rows,[{'id':'x','amount':'0'}],**kw)
   self.assertEqual(r['quality'],'insufficient');self.assertNotIn('SECRET_BAD_NUMBER',str(r))
