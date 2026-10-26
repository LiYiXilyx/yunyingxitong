import importlib.util
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

class WdtPreflightTests(unittest.TestCase):
    def load(self):
        script = ROOT / 'scripts/wdt-check.py'
        self.assertTrue(script.exists(), 'T04 local-only credential check is missing')
        spec = importlib.util.spec_from_file_location('wdt_check', script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_empty_credentials_are_needs_user_and_no_network(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'wdt.env'
            path.write_text('WDT_APP_NAME=\nWDT_SID=\nWDT_SIGNING_KEY=\nWDT_BASE_URL=\n')
            path.chmod(0o600)
            with patch('socket.socket', side_effect=AssertionError('network is forbidden')):
                report = module.inspect_config(path)
            self.assertEqual(report['status'], 'needs_user')
            self.assertFalse(report['network_request_sent'])
            self.assertEqual(len(report['missing_keys']), 4)

    def test_filled_credentials_are_never_reported_as_live_verified(self):
        module = self.load()
        secrets = ['private-app-name', 'private-seller-id', 'private-signing-key']
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'wdt.env'
            path.write_text('WDT_APP_NAME='+secrets[0]+'\nWDT_SID='+secrets[1]+'\nWDT_SIGNING_KEY='+secrets[2]+'\nWDT_BASE_URL=https://openapi.qizhishangke.com\n')
            path.chmod(0o600)
            with patch('socket.socket', side_effect=AssertionError('network is forbidden')):
                report = module.inspect_config(path)
            self.assertEqual(report['status'], 'configured_not_verified')
            self.assertFalse(report['live_verified'])
            self.assertFalse(report['network_request_sent'])
            output = json.dumps(report)
            for value in secrets:
                self.assertNotIn(value, output)

    def test_untrusted_destination_or_unsafe_file_is_rejected_without_values(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'wdt.env'
            path.write_text('WDT_APP_NAME=private-app\nWDT_SID=private-sid\nWDT_SIGNING_KEY=private-key\nWDT_BASE_URL=https://attacker.invalid/?secret=private-key\n')
            path.chmod(0o600)
            report = module.inspect_config(path)
            self.assertEqual(report['status'], 'needs_user')
            self.assertIn('base_url_not_allowed', report['issues'])
            self.assertNotIn('attacker', json.dumps(report))
            path.chmod(0o644)
            self.assertIn('private_file_permissions_required', module.inspect_config(path)['issues'])
            link = Path(folder) / 'link.env'
            link.symlink_to(path)
            self.assertIn('private_regular_file_required', module.inspect_config(link)['issues'])
