import subprocess
import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class DispatchTests(unittest.TestCase):
    def run_case(self, suite, case=''):
        return subprocess.run([sys.executable,str(ROOT/'scripts/run-tests.py'),suite,'--case',case],capture_output=True,text=True,cwd=ROOT)
    def test_unknown_case_rejected(self):
        r=self.run_case('data','invented');self.assertNotEqual(r.returncode,0);self.assertIn('Unknown CASE',r.stderr)
    def test_known_unimplemented_cases_never_pass(self):
        for suite,case in [('data','test_wdt'),('data','outbox'),('plugin','scope'),('ego',''),('e2e','')]:
            with self.subTest(suite=suite,case=case):
                r=self.run_case(suite,case);self.assertNotEqual(r.returncode,0);self.assertIn('not implemented',r.stderr.lower())
if __name__=='__main__':unittest.main()
