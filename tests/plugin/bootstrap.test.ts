import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const base=process.env.NOCOBASE_TEST_URL || 'http://127.0.0.1:13000';
const env=Object.fromEntries(readFileSync(new URL('../../.local/secrets/deploy.env',import.meta.url),'utf8').split('\n').filter(l=>l && !l.startsWith('#')).map(l=>{ const i=l.indexOf('='); return [l.slice(0,i),l.slice(i+1)]; }));
test('bootstrap resource denies anonymous users and returns scope-limited status after login',async()=>{
  const anonymous=await fetch(`${base}/api/opsBootstrap:status`);
  assert.ok([401,403].includes(anonymous.status),`anonymous status ${anonymous.status}`);
  const login=await fetch(`${base}/api/auth:signIn`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({email:env.INIT_ROOT_EMAIL,password:env.INIT_ROOT_PASSWORD})});
  assert.equal(login.status,200,'local admin login failed');
  const {data}=await login.json();
  assert.equal(typeof data.token,'string');
  const result=await fetch(`${base}/api/opsBootstrap:status`,{headers:{authorization:`Bearer ${data.token}`}});
  assert.equal(result.status,200);
  const body=await result.json();
  assert.deepEqual(body.data,{schema_version:'1',stage:'T02',business_ready:false});
});
