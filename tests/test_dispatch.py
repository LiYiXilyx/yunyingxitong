import subprocess
import sys
from pathlib import Path
import json
import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
import runpy
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
class DispatchTests(unittest.TestCase):
    def run_case(self, suite, case='', env=None):
        return subprocess.run([sys.executable,str(ROOT/'scripts/run-tests.py'),suite,'--case',case],capture_output=True,text=True,cwd=ROOT,env=env)
    def test_unknown_case_rejected(self):
        r=self.run_case('data','invented');self.assertNotEqual(r.returncode,0);self.assertIn('Unknown CASE',r.stderr)
    def test_known_unimplemented_cases_never_pass(self):
        for suite,case in [('data','test_ingestion'),('data','outbox'),('plugin','tasks'),('plugin','evidence'),('plugin','reviews'),('ego',''),('e2e','')]:
            with self.subTest(suite=suite,case=case):
                r=self.run_case(suite,case);self.assertNotEqual(r.returncode,0);self.assertIn('not implemented',r.stderr.lower())

    def plugin_dispatch(self, case='', exit_code=0):
        # Replace only Node execution: dispatch must not run the live database tests.
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder); log=path/'arguments.json'
            node=path/'node'
            node.write_text(f'#!{sys.executable}\nimport json, os, sys\nfrom pathlib import Path\nPath(os.environ["DISPATCH_LOG"]).write_text(json.dumps(sys.argv[1:]))\nsys.exit(int(os.environ["DISPATCH_EXIT"]))\n')
            node.chmod(0o700)
            env={**os.environ,'PATH':str(path)+os.pathsep+os.environ['PATH'],'DISPATCH_LOG':str(log),'DISPATCH_EXIT':str(exit_code)}
            result=self.run_case('plugin',case,env)
            return result,json.loads(log.read_text()) if log.exists() else []

    def test_default_plugin_runs_every_implemented_case_serially(self):
        result,args=self.plugin_dispatch()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('--test-concurrency=1',args)
        self.assertEqual([Path(a).name for a in args if a.endswith(('.test.ts','.test.js'))],['bootstrap.test.ts','scope.test.ts','rules.test.ts','pages.test.ts','client-behavior.test.js'])

    def test_each_implemented_plugin_case_can_run_alone(self):
        for case in ['bootstrap','scope','rules','pages','client']:
            with self.subTest(case=case):
                result,args=self.plugin_dispatch(case)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual([Path(a).name for a in args if a.endswith(('.test.ts','.test.js'))],['client-behavior.test.js' if case=='client' else case+'.test.ts'])

    def test_plugin_failure_is_not_reported_as_success(self):
        result,_=self.plugin_dispatch('bootstrap',exit_code=7)
        self.assertEqual(result.returncode,7)

    def data_dispatch(self, case=''):
        with patch.object(sys, 'argv', ['run-tests.py', 'data', '--case', case]), patch('subprocess.call', return_value=0) as execute:
            runpy.run_path(str(ROOT/'scripts/run-tests.py'), run_name='__main__')
        return [call.args[0] for call in execute.call_args_list]

    def test_wdt_case_runs_protocol_and_real_postgres_tests(self):
        commands = self.data_dispatch('test_wdt')
        self.assertEqual(len(commands), 1)
        command = commands[0]
        self.assertIn('services/ops-data/tests/test_wdt.py', command)
        self.assertIn('services/ops-data/tests/test_wdt_postgres.py', command)
        self.assertIn('OPS_TEST_DATABASE_URL="$OPS_DATABASE_URL"', command[6])

    def test_default_data_suite_includes_wdt_and_postgres(self):
        commands = self.data_dispatch()
        paths = [part for command in commands for part in command if part.endswith('.py')]
        for name in ('test_contracts.py', 'test_health.py', 'test_wdt.py', 'test_wdt_postgres.py'):
            self.assertTrue(any(path.endswith('/'+name) for path in paths), name)


class T03SetupTests(unittest.TestCase):
    def script(self):
        path=ROOT/'scripts/setup-t03.py'
        self.assertTrue(path.is_file(),'T03 setup script is missing')
        spec=importlib.util.spec_from_file_location('setup_t03',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_credentials_survive_repeated_setup_without_output(self):
        module=self.script()
        accounts={key:{'email':f'{key}@synthetic.local','password':f'private-{key}-password','id':index} for index,key in enumerate(['supervisor','operatorA','operatorB','integration'],1)}
        container=json.dumps(accounts).encode(); uploads=[]; pages=[]
        def process(command, **kwargs):
            nonlocal container
            if kwargs.get('input') is not None:
                uploads.append(kwargs['input']);container=kwargs['input']
            if command[:2]==['node','scripts/setup-nocobase-pages.mjs']:
                pages.append(command)
            output=container if command[-2:]==['cat','/tmp/t03-accounts.json'] else b''
            return subprocess.CompletedProcess(command,0,output,b'')
        with tempfile.TemporaryDirectory() as folder,patch.object(module.subprocess,'run',side_effect=process):
            root=Path(folder);captured=io.StringIO()
            with contextlib.redirect_stdout(captured):
                module.setup(root)
                saved=root/'.local/secrets/t03-accounts.json';before=saved.read_bytes()
                self.assertEqual(saved.stat().st_mode&0o777,0o600)
                self.assertEqual(saved.parent.stat().st_mode&0o777,0o700)
                module.setup(root)
            self.assertEqual(saved.read_bytes(),before)
            self.assertEqual(uploads,[before])
            self.assertEqual(len(pages),2)
            for account in accounts.values():
                self.assertNotIn(account['password'],captured.getvalue())

    def test_existing_invalid_or_symlink_credentials_stop_before_container_changes(self):
        module=self.script()
        for symlink in [False,True]:
            with self.subTest(symlink=symlink),tempfile.TemporaryDirectory() as folder,patch.object(module.subprocess,'run') as process:
                root=Path(folder);secret=root/'.local/secrets/t03-accounts.json';secret.parent.mkdir(parents=True)
                victim=root/'victim';victim.write_text('preserve')
                if symlink:secret.symlink_to(victim)
                else:secret.write_text('{"operatorA":{}}')
                with self.assertRaises(module.SetupError):module.setup(root)
                self.assertEqual(process.call_count,0)
                self.assertEqual(victim.read_text(),'preserve')

    def test_failed_seed_preserves_host_credentials_and_does_not_configure_pages(self):
        module=self.script()
        accounts={key:{'email':f'{key}@synthetic.local','password':f'private-{key}-password','id':index} for index,key in enumerate(['supervisor','operatorA','operatorB','integration'],1)}
        calls=[]
        def process(command,**kwargs):
            calls.append(command)
            status=1 if any('bootstrap-synthetic.js' in part for part in command) else 0
            return subprocess.CompletedProcess(command,status,b'',b'private failure detail')
        with tempfile.TemporaryDirectory() as folder,patch.object(module.subprocess,'run',side_effect=process):
            root=Path(folder);secret=root/'.local/secrets/t03-accounts.json';secret.parent.mkdir(parents=True);secret.write_text(json.dumps(accounts));before=secret.read_bytes()
            with self.assertRaises(module.SetupError):module.setup(root)
            self.assertEqual(secret.read_bytes(),before)
            self.assertFalse(any(command[0]=='node' for command in calls))

    def test_unexpected_password_rotation_does_not_replace_private_record(self):
        module=self.script()
        accounts={key:{'email':f'{key}@synthetic.local','password':f'private-{key}-password','id':index} for index,key in enumerate(['supervisor','operatorA','operatorB','integration'],1)}
        changed=json.loads(json.dumps(accounts));changed['operatorA']['password']='unexpected-replacement'
        def process(command,**kwargs):
            output=json.dumps(changed).encode() if command[-2:]==['cat','/tmp/t03-accounts.json'] else b''
            return subprocess.CompletedProcess(command,0,output,b'')
        with tempfile.TemporaryDirectory() as folder,patch.object(module.subprocess,'run',side_effect=process):
            root=Path(folder);secret=root/'.local/secrets/t03-accounts.json';secret.parent.mkdir(parents=True);secret.write_text(json.dumps(accounts));before=secret.read_bytes()
            with self.assertRaises(module.SetupError):module.setup(root)
            self.assertEqual(secret.read_bytes(),before)

    def test_partial_bootstrap_failure_recovers_credentials_and_resumes_after_container_recreation(self):
        module=self.script()
        partial={'supervisor':{'email':'supervisor@synthetic.local','password':'keep-before-user-created'}}
        full={key:{'email':f'{key}@synthetic.local','password':f'private-{key}-password','id':index} for index,key in enumerate(['supervisor','operatorA','operatorB','integration'],1)}
        full['supervisor']['password']=partial['supervisor']['password']
        container=None;failed=False;uploads=[];pages=[]
        def process(command,**kwargs):
            nonlocal container,failed
            if kwargs.get('input') is not None:
                uploads.append(kwargs['input']);container=kwargs['input']
            if any('bootstrap-synthetic.js' in part for part in command):
                if not failed:
                    failed=True;container=json.dumps(partial).encode()
                    return subprocess.CompletedProcess(command,1,b'',b'private backend failure')
                # A recreated container receives the previous partial record first.
                self.assertEqual(json.loads(container),partial)
                container=json.dumps(full).encode()
            if command[0]=='node':pages.append(command)
            output=container if command[-2:]==['cat','/tmp/t03-accounts.json'] else b''
            return subprocess.CompletedProcess(command,0,output,b'')
        with tempfile.TemporaryDirectory() as folder,patch.object(module.subprocess,'run',side_effect=process):
            root=Path(folder);captured=io.StringIO()
            with contextlib.redirect_stdout(captured):
                with self.assertRaises(module.SetupError):module.setup(root)
                secret=root/'.local/secrets/t03-accounts.json'
                self.assertTrue(secret.is_file(),'partial credentials must survive outside the failed container')
                saved=secret.read_bytes()
                self.assertEqual(json.loads(saved),partial)
                self.assertEqual(secret.stat().st_mode&0o777,0o600)
                self.assertEqual(pages,[])
                container=None
                module.setup(root)
            self.assertEqual(json.loads(secret.read_bytes()),full)
            self.assertEqual(uploads,[saved])
            self.assertEqual(len(pages),1)
            self.assertNotIn(partial['supervisor']['password'],captured.getvalue())
if __name__=='__main__':unittest.main()
