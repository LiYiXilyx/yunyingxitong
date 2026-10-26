#!/usr/bin/env node
// Local NocoBase only. Keep credentials and bearer token out of argv and output.
import { readFileSync, lstatSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
const root = new URL('../', import.meta.url);
const base = 'http://127.0.0.1:13000';
async function main() {
  const file = new URL('.local/secrets/t03-accounts.json', root);
  const stat = lstatSync(file);
  if (!stat.isFile() || stat.isSymbolicLink() || (stat.mode & 0o077)) throw Error('private_account_file_required');
  const account = JSON.parse(readFileSync(file, 'utf8')).integration;
  if (!account?.email || !account?.password) throw Error('integration_account_required');
  const login = await fetch(`${base}/api/auth:signIn`, {
    method: 'POST', headers: {'content-type':'application/json'},
    body: JSON.stringify({email:account.email,password:account.password}),
    redirect:'error', signal:AbortSignal.timeout(10000),
  });
  if (!login.ok) throw Error('local_login_failed');
  const token = (await login.json()).data?.token;
  if (typeof token !== 'string' || !token) throw Error('local_token_missing');
  const response = await fetch(`${base}/api/opsConfig:snapshot`, {
    headers:{authorization:`Bearer ${token}`}, redirect:'error', signal:AbortSignal.timeout(10000),
  });
  if (!response.ok) throw Error('local_snapshot_failed');
  const config = (await response.json()).data;
  const snapshot = {version:String(config.version),scope:{
    store_ids:[...new Set((config.opsMemberships || []).filter(r=>r.status==='active' && String(r.user_id)===String(account.id)).map(r=>r.store_id))].sort(),
    warehouse_ids:[...new Set((config.opsWarehouseScopes || []).filter(r=>r.status==='active' && String(r.user_id)===String(account.id)).map(r=>r.warehouse_id))].sort(),
  }};
  const result=spawnSync('scripts/compose.sh',['exec','-T','ops-data','python','-m','ops_data.demo_t05'],{
    cwd:root,input:JSON.stringify({snapshot,token}),encoding:'utf8',maxBuffer:1024*1024,timeout:120000,
  });
  if (result.status!==0) throw Error('synthetic_rehearsal_failed');
  // Python produces a strict aggregate result only. Parse and allowlist again.
  const output=JSON.parse(result.stdout);
  const keys=['source_kind','batch_id','fact_count','quality','values','pending_evaluations','health_receipts'];
  if (Object.keys(output).some(k=>!keys.includes(k)) || output.source_kind!=='synthetic') throw Error('unexpected_demo_output');
  console.log(JSON.stringify(output));
}
main().catch(()=>{console.error('T05合成演练失败；未输出账号、token或服务原始响应。');process.exitCode=1;});
