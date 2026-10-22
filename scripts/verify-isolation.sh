#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
scripts/compose.sh exec -T ops-data python - <<'PY'
import os
import psycopg
from psycopg.conninfo import conninfo_to_dict
kwargs=conninfo_to_dict(os.environ['OPS_DATABASE_URL'])
with psycopg.connect(**kwargs) as c:
    assert c.execute('select current_user, current_database()').fetchone()==('ops_app','ops')
    assert c.execute("select has_database_privilege(current_user, 'nocobase', 'CONNECT')").fetchone()==(False,)
kwargs['dbname']='nocobase'
try:
    psycopg.connect(**kwargs)
except psycopg.Error as e:
    assert 'permission denied for database' in str(e), 'Failure was not database permission denial'
else:
    raise SystemExit('Isolation failure: ops can connect to nocobase')
print('PASS: ops account denied access to nocobase database')
PY
scripts/compose.sh exec -T nocobase node - <<'JS'
const {Client}=require('pg');
const config={host:process.env.DB_HOST,user:process.env.DB_USER,password:process.env.DB_PASSWORD,database:process.env.DB_DATABASE};
(async()=>{
 const own=new Client(config);await own.connect();const r=await own.query('select current_user, current_database()');await own.end();
 if(r.rows[0].current_user!=='nocobase_app'||r.rows[0].current_database!=='nocobase') throw Error('Unexpected own account');
 const other=new Client({...config,database:'ops'});
 try {await other.connect();await other.end();throw Error('Isolation failure: nocobase can connect to ops');}
 catch(e){if(e.code!=='42501')throw Error('Failure was not database permission denial');}
 console.log('PASS: nocobase account denied access to ops database');
})().catch(()=>{console.error('Database isolation check failed');process.exit(1)});
JS
