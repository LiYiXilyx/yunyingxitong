'use strict';
const {randomUUID,createHash}=require('crypto');
const path=require('path');
const {identity,scope}=require('./access');
const {validateCommand,payloadHash}=require(path.join(process.env.OPS_CONTRACTS_DIR || path.resolve(__dirname,'../../../contracts'),'typescript/runtime.cjs'));
const digest=v=>createHash('sha256').update(JSON.stringify(v)).digest('hex');
const normalized=s=>({store_ids:[...s.store_ids].sort(),warehouse_ids:[...s.warehouse_ids].sort()});
function permitted(s,g){return s.store_ids.every(id=>g.stores.has(id))&&s.warehouse_ids.every(id=>g.warehouses.has(id));}
async function owner(db,s,transaction){
 const assigned=await db.getRepository('opsOwnerAssignments').find({filter:{rule_family:'DATA'},transaction});
 const members=await db.getRepository('opsMemberships').find({filter:{status:'active',membership_role:'ops_supervisor'},transaction});
 const candidates=[...assigned.filter(r=>(!r.get('store_id')||s.store_ids.includes(r.get('store_id')))&&(!r.get('warehouse_id')||s.warehouse_ids.includes(r.get('warehouse_id')))),...members];
 for(const candidate of candidates){
  const user=await db.getRepository('users').findOne({filterByTk:candidate.get('user_id'),appends:['roles'],transaction});
  const roles=(user?.get('roles')||[]).map(r=>r.get('name'));
  if(!roles.some(r=>['ops_supervisor','ops_operator','root','admin'].includes(r))||roles.includes('ops_integration'))continue;
  const grants=await scope(db,{id:user.id,admin:false},transaction);
  if(permitted(s,grants))return user.id;
 }
 return null;
}
async function integrity(db){
 const q=db.sequelize.getQueryInterface().queryGenerator;
 for(const [collection,field] of [['opsDataHealth','scope_key'],['opsDataIssues','issue_key']]){
  const table=q.quoteTable(db.getCollection(collection).model.getTableName());
  await db.sequelize.query(`CREATE UNIQUE INDEX IF NOT EXISTS ${q.quoteIdentifier('t05_'+field+'_unique')} ON ${table} (${q.quoteIdentifier(field)})`);
 }
}
function register(plugin, readActions){
 const db=plugin.db;
 plugin.app.resource({name:'opsDataHealth',actions:{...readActions,async ingest(ctx){
  const input=ctx.action.params.values;
  if(!validateCommand(input)||input.payload.kind!=='HealthEnvelope')ctx.throw(400,'Invalid health command');
  const h=input.payload,s=normalized(h.scope);
  if(!s.store_ids.length&&!s.warehouse_ids.length)ctx.throw(403,'Nonempty scope required');
  ctx.body=await db.sequelize.transaction(async transaction=>{
   // Same lock as configuration commands: current permissions/config and receipts share one serialization boundary.
   await db.sequelize.query('SELECT pg_advisory_xact_lock(734203)',{transaction});
   const who=await identity(db,ctx,transaction);
   if(!who.integration)ctx.throw(403,'Integration role required');
   const grants=await scope(db,{...who,admin:false},transaction);
   if(!permitted(s,grants)||(h.data_type==='inventory'&&!s.warehouse_ids.length))ctx.throw(403,'Scope denied');
   const version=await db.getRepository('opsConfigVersions').findOne({sort:['-version'],transaction});
   if(input.binding_version!==String(version?.get('version')||0))ctx.throw(409,'Binding version conflict');
   const receipts=db.getRepository('opsCommandReceipts');
   const previous=await receipts.findOne({filter:{business_id:input.command_id},transaction});
   if(previous){if(previous.get('title')!==input.payload_hash)ctx.throw(409,'Command content conflict');return {...previous.get('result'),status:'duplicate'};}
   const scopeKey=digest([s,h.data_type]);
   const healthRepo=db.getRepository('opsDataHealth');
   const existing=await healthRepo.findOne({filter:{scope_key:scopeKey},transaction});
   const envelopeHash=payloadHash({payload:{...h,scope:s}});
   const revision=BigInt(h.health_revision),old=existing?BigInt(existing.get('health_revision')):null;
   if(old!==null&&revision===old&&existing.get('envelope_hash')!==envelopeHash)ctx.throw(409,'Health revision content conflict');
   const status=old!==null&&revision<old?'ignored_stale':'applied';
   const receipt={receipt_id:randomUUID(),command_id:input.command_id,status,health_revision:h.health_revision};
   if(status==='applied'){
    const common={store_id:s.store_ids[0]||null,warehouse_id:s.warehouse_ids[0]||null,scope_type:s.warehouse_ids.length?'warehouse':'store',health_scope:s,environment:'synthetic'};
    const values={...common,title:`${h.data_type}: ${h.status}`,scope_key:scopeKey,data_type:h.data_type,health_revision:h.health_revision,envelope_hash:envelopeHash,status:h.status,last_attempt_at:h.last_attempt_at,last_success_at:h.last_success_at,freshness_deadline:h.freshness_deadline,expected_window:h.expected_window,missing_fields:h.missing_fields,error_class:h.error_class,details:h};
    if(existing)await existing.update(values,{transaction});else await healthRepo.create({values:{...values,business_id:randomUUID()},transaction});
    const issues=db.getRepository('opsDataIssues');
    if(['failed','partial','needs_user'].includes(h.status)){
     const error=h.error_class||h.status,issueKey=digest([scopeKey,error]);
     const issue=await issues.findOne({filter:{issue_key:issueKey},transaction});
     const assigned=await owner(db,s,transaction);
     const values={...common,title:`数据问题: ${h.data_type}`,issue_key:issueKey,data_type:h.data_type,error_class:error,health_revision:h.health_revision,status:assigned?'open':'unassigned',assignee_id:assigned,description:assigned?'数据采集需处理':'数据采集需处理（未分配）'};
     if(issue)await issue.update(values,{transaction});else await issues.create({values:{...values,business_id:randomUUID()},transaction});
    }else if(h.status==='succeeded'){
     for(const issue of await issues.find({filter:{data_type:h.data_type},transaction}))if(JSON.stringify(normalized(issue.get('health_scope')||{store_ids:[],warehouse_ids:[]}))===JSON.stringify(s))await issue.update({status:'recovered',health_revision:h.health_revision},{transaction});
    }
    await db.getRepository('opsEvents').create({values:{...common,business_id:randomUUID(),title:'数据健康摘要接收',event_type:'data_health.received',actor_id:who.id,payload:{command_id:input.command_id,receipt_id:receipt.receipt_id,health_revision:h.health_revision}},transaction});
   }
   await receipts.create({values:{business_id:input.command_id,command_id:input.command_id,title:input.payload_hash,result:receipt,environment:'synthetic'},transaction});
   return receipt;
  });
 }}});
 plugin.app.acl.allow('opsDataHealth','ingest','loggedIn');
}
module.exports={register,integrity};
