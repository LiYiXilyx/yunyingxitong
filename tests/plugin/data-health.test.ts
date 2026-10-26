import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {payloadHash} from '../../contracts/typescript/contracts.ts';
import {api,login,roleToken} from './backend-helper.ts';
const time='2026-10-25T00:00:00Z';
async function fixture() {
 const admin=await login(),token=await roleToken('integration');
 const config=(await (await api('opsConfig:snapshot',admin)).json()).data;
 const own=(await (await api('opsMemberships:list',token)).json()).data[0];
 const command:any={schema_version:'1',command_id:randomUUID(),binding_version:String(config.version),occurred_at:time,payload:{kind:'HealthEnvelope',scope:{store_ids:[own.store_id],warehouse_ids:[]},data_type:'synthetic-'+randomUUID(),health_revision:'2',last_attempt_at:time,last_success_at:null,expected_window:{start:'2026-10-24T00:00:00Z',end:time},freshness_deadline:time,status:'failed',missing_fields:[],error_class:'synthetic_failure'}};
 const sign=(c:any)=>({...c,payload_hash:payloadHash(c)});
 return {admin,token,command,sign};
}
test('health ingest authenticates integration, persists replay and stale receipt, merges and recovers issues without changing tasks',async()=>{
 const {admin,token,command,sign}=await fixture();
 const send=(c:any,t=token)=>api('opsDataHealth:ingest',t,sign(c));
 const before=(await (await api('opsTasks:list',admin)).json()).data;
 assert.equal((await send(command,await roleToken('operatorA'))).status,403);
 let r=await send(command); assert.equal(r.status,200);const receipt=(await r.json()).data;assert.equal(receipt.status,'applied');assert.ok(receipt.receipt_id);
 r=await send(command);assert.equal(r.status,200);assert.equal((await r.json()).data.status,'duplicate');
 assert.equal((await send({...command,payload:{...command.payload,status:'partial'}})).status,409);
 const next=(revision:string,status='failed')=>({...command,command_id:randomUUID(),payload:{...command.payload,health_revision:revision,status}});
 r=await send(next('1'));assert.equal(r.status,200);assert.equal((await r.json()).data.status,'ignored_stale');
 assert.equal((await send(next('2','partial'))).status,409);
 assert.equal((await send({...next('3'),binding_version:'999999'})).status,409);
 assert.equal((await send({...next('3'),payload:{...command.payload,scope:{store_ids:[],warehouse_ids:[]}}})).status,403);
 assert.equal((await send(next('3'))).status,200);
 const issues=()=>api(`opsDataIssues:list?filter=${encodeURIComponent(JSON.stringify({data_type:command.payload.data_type}))}`,admin).then(r=>r.json()).then(j=>j.data);
 assert.equal((await issues()).length,1);
 assert.equal((await send(next('4','succeeded'))).status,200);assert.equal((await issues())[0].status,'recovered');
 assert.deepEqual((await (await api('opsTasks:list',admin)).json()).data,before);
});
test('health replay rechecks revoked integration role and membership, rejects cross scope and warehouse bypass',async()=>{
 const {admin,token,command,sign}=await fixture();
 const send=(c:any)=>api('opsDataHealth:ingest',token,sign(c));
 assert.equal((await send(command)).status,200);
 const account=(await import('./backend-helper.ts')).accounts().integration;
 try {
  assert.equal((await api(`users/${account.id}/roles:set`,admin,['member'])).status,200);
  assert.equal((await send(command)).status,403);
 } finally {assert.equal((await api(`users/${account.id}/roles:set`,admin,['ops_integration'])).status,200);}
 const snap=()=>api('opsConfig:snapshot',admin).then(r=>r.json()).then(j=>j.data);
 const config=await snap();
 const member=config.opsMemberships.find((m:any)=>m.user_id===account.id&&m.store_id===command.payload.scope.store_ids[0]);
 const change=async(status:string)=>api('opsConfig:command',admin,{command:'saveMembership',command_id:randomUUID(),expected_version:(await snap()).version,reason:'synthetic health permission test',values:{business_id:member.business_id,store_id:member.store_id,user_id:member.user_id,membership_role:member.membership_role,environment:'synthetic',status}});
 try {assert.equal((await change('inactive')).status,200);assert.equal((await send(command)).status,403);}finally{assert.equal((await change('active')).status,200);}
 const fresh={...command,command_id:randomUUID(),binding_version:String((await snap()).version)};
 assert.equal((await send({...fresh,payload:{...fresh.payload,scope:{store_ids:[randomUUID()],warehouse_ids:[]}}})).status,403);
 assert.equal((await send({...fresh,payload:{...fresh.payload,data_type:'inventory'}})).status,403);
 assert.equal((await send({...fresh,payload:{...fresh.payload,scope:{store_ids:[],warehouse_ids:[randomUUID()]},data_type:'inventory'}})).status,403);
});
test('health list, detail and caller filters preserve full current scope isolation',async()=>{
 const operator=await roleToken('operatorA'),admin=await login();
 const tasks=(await (await api('opsTasks:list',operator)).json()).data;
 const store=tasks[0].store_id;
 const all=(await (await api('opsDataHealth:list?pageSize=200',admin)).json()).data;
 const foreign=all.find((r:any)=>r.store_id!==store||r.warehouse_id);
 assert.ok(foreign,'synthetic foreign health seed required');
 const own=(await (await api('opsDataHealth:list?pageSize=200',operator)).json()).data;
 assert.ok(own.length>0);
 assert.ok(own.every((r:any)=>r.store_id===store&&!r.warehouse_id));
 assert.equal((await api(`opsDataHealth:get?filterByTk=${foreign.id}`,operator)).status,404);
 const filtered=(await (await api(`opsDataHealth:list?filter=${encodeURIComponent(JSON.stringify({id:foreign.id}))}`,operator)).json()).data;
 assert.deepEqual(filtered,[]);
 assert.equal((await api('opsDataHealth:list?appends=anything',operator)).status,403);
 assert.equal((await api(`opsDataHealth:create`,operator,{store_id:store,status:'succeeded'})).status,403);
});
