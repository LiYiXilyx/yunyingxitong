import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/bootstrap.py'

class BootstrapTest(unittest.TestCase):
    def test_private_idempotent_generation_without_secret_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run = lambda: subprocess.run([sys.executable, str(SCRIPT), '--root', str(root)], capture_output=True, text=True)
            first = run()
            self.assertEqual(first.returncode, 0, first.stderr)
            secret = root / '.local/secrets/deploy.env'
            before = secret.read_bytes()
            self.assertEqual(secret.stat().st_mode & 0o777, 0o600)
            values = dict(line.split('=',1) for line in before.decode().splitlines() if line and not line.startswith('#'))
            for key in ('APP_KEY','POSTGRES_PASSWORD','NOCO_DB_PASSWORD','OPS_DB_PASSWORD','INIT_ROOT_PASSWORD'):
                self.assertGreaterEqual(len(values[key]), 32)
                self.assertNotIn(values[key], first.stdout + first.stderr)
            self.assertEqual(run().returncode, 0)
            self.assertEqual(secret.read_bytes(), before)
            self.assertEqual((root / '.local/secrets/wdt.env').stat().st_mode & 0o777, 0o600)
            self.assertEqual((root / '.local/secrets').stat().st_mode & 0o777, 0o700)

    def test_refuses_symlink_secret_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); secret_dir=root/'.local/secrets'; secret_dir.mkdir(parents=True)
            victim=root/'victim'; victim.write_text('keep')
            (secret_dir/'deploy.env').symlink_to(victim)
            result=subprocess.run([sys.executable,str(SCRIPT),'--root',str(root)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(victim.read_text(),'keep')

if __name__=='__main__': unittest.main()
