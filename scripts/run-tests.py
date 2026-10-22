#!/usr/bin/env python3
"""Explicit test-case dispatch. Missing implementation must never look green."""
import argparse
import os
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser()
p.add_argument('suite',choices=['data','plugin','ego','e2e'])
p.add_argument('--case',default='')
a=p.parse_args()
commands=[]
env=os.environ.copy()
env['PYTHONPATH']=str(ROOT/'services/ops-data')
if a.suite=='data':
    known={'test_wdt','test_ingestion','test_rules','test_reviews','test_recovery','outbox','contracts','health'}
    if a.case and a.case not in known: raise SystemExit(f'Unknown CASE: {a.case}')
    for case in ([a.case] if a.case else ['contracts','health']):
        filename={'outbox':'test_outbox.py','contracts':'test_contracts.py','health':'test_health.py'}.get(case,case+'.py')
        target='services/ops-data/tests/'+filename
        if not (ROOT/target).exists(): raise SystemExit(f'Not implemented yet: {target}')
        if case=='contracts':
            commands.append([str(ROOT/'services/ops-data/.venv/bin/python'),'-m','pytest',target,'-q','--tb=short'])
        else:
            commands.append(['scripts/compose.sh','exec','-T','ops-data','sh','-c','OPS_TEST_DATABASE_URL="$OPS_DATABASE_URL" python -m pytest "$1" -q --tb=short -p no:cacheprovider','test',target])
elif a.suite=='plugin':
    implemented=['bootstrap','scope','rules','pages','client']
    known={*implemented,'tasks','evidence','reviews'}
    if a.case and a.case not in known: raise SystemExit(f'Unknown CASE: {a.case}')
    targets=[]
    for case in ([a.case] if a.case else implemented):
        target=ROOT/'tests/plugin'/('client-behavior.test.js' if case=='client' else f'{case}.test.ts')
        if case not in implemented or not target.exists(): raise SystemExit(f'Not implemented yet: {target.relative_to(ROOT)}')
        targets.append(str(target))
    # Scope and rule suites share the authoritative configuration version.
    commands.append(['node','--test','--test-concurrency=1',*targets])
else:
    raise SystemExit(f'{a.suite}: not implemented through T03; no tests executed')
for command in commands:
    result=subprocess.call(command,cwd=ROOT,env=env)
    if result: raise SystemExit(result)
