import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).parents[1] / 'scripts/community_guard.py'

class CommunityGuardTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), '缺少生产守门脚本')
        spec = importlib.util.spec_from_file_location('community_guard', SCRIPT)
        self.guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.guard)
        self.policy = {'official_plugins': {'@nocobase/plugin-a': {'version': '2.2.30', 'license': 'Apache-2.0', 'source_path': 'packages/plugins/@nocobase/plugin-a/package.json'}}, 'project_plugins': {'@project2/plugin-ops': {'version': '0.1.0'}}, 'source_commit': 'a'*40}
        self.installed = [{'name': '@nocobase/plugin-a', 'version': '2.2.30', 'license': 'Apache-2.0'}]

    def test_accepts_known_matching_package_and_enabled_subset(self):
        self.assertEqual(self.guard.validate(self.policy, self.installed, ['@nocobase/plugin-a']), [])

    def test_rejects_unknown_even_when_not_enabled(self):
        self.installed.append({'name': '@nocobase/plugin-commercial', 'version': '2.2.30'})
        self.assertTrue(self.guard.validate(self.policy, self.installed, []))

    def test_rejects_changed_version(self):
        self.installed[0]['version'] = '2.2.31'
        self.assertTrue(self.guard.validate(self.policy, self.installed, []))

    def test_rejects_changed_license(self):
        self.installed[0]['license'] = 'Commercial'
        self.assertTrue(self.guard.validate(self.policy, self.installed, []))

    def test_rejects_unknown_enabled_plugin(self):
        self.assertTrue(self.guard.validate(self.policy, self.installed, ['@nocobase/plugin-trial']))

    def test_missing_enabled_inventory_is_not_success(self):
        self.assertTrue(self.guard.validate(self.policy, self.installed, None))

    def test_rejects_empty_installed_inventory(self):
        self.assertTrue(self.guard.validate(self.policy, [], []))

    def test_rejects_duplicate_names(self):
        self.assertTrue(self.guard.validate(self.policy, self.installed * 2, []))

    def test_project_plugin_allowed_only_at_fixed_version(self):
        self.installed.append({'name': '@project2/plugin-ops', 'version': '0.1.0'})
        self.assertEqual(self.guard.validate(self.policy, self.installed, ['@project2/plugin-ops']), [])
        self.installed[-1]['version'] = '0.2.0'
        self.assertTrue(self.guard.validate(self.policy, self.installed, []))


class SourceLicenseFallbackTests(CommunityGuardTests):
    def test_absent_license_needs_explicit_reviewed_source_fallback(self):
        self.installed[0].pop('license')
        self.policy['official_plugins']['@nocobase/plugin-a']['license'] = None
        self.assertTrue(self.guard.validate(self.policy, self.installed, []))
        self.policy['official_plugins']['@nocobase/plugin-a']['license_fallback'] = 'repository-root-package-json'
        self.policy['repository_license'] = 'Apache-2.0'
        self.assertEqual(self.guard.validate(self.policy, self.installed, []), [])

class RuntimeInventoryTests(CommunityGuardTests):
    def setUp(self):
        super().setUp()
        self.assertTrue(callable(getattr(self.guard, "validate_runtime", None)), "缺少运行时核验")

    def test_runtime_database_version_must_match_package(self):
        rows = [{'packageName': '@nocobase/plugin-a', 'version': '2.2.31', 'enabled': True, 'installed': True}]
        self.assertTrue(self.guard.validate_runtime(self.installed, rows))
        rows[0]['version'] = '2.2.30'
        self.assertEqual(self.guard.validate_runtime(self.installed, rows), [])

    def test_database_unknown_installed_package_cannot_hide_by_disabled_state(self):
        rows = [{'packageName': '@commercial/plugin-x', 'version': '1', 'enabled': False, 'installed': True}]
        self.assertTrue(self.guard.validate_runtime(self.installed, rows))

    def test_empty_runtime_inventory_is_incomplete(self):
        self.assertTrue(self.guard.validate_runtime(self.installed, []))

class ImageReferenceTests(unittest.TestCase):
    def test_exact_pinned_image_required(self):
        spec = importlib.util.spec_from_file_location('community_guard', SCRIPT)
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        self.assertTrue(callable(getattr(guard, 'validate_image', None)), '缺少实际容器镜像核验')
        policy = {'image': 'nocobase/nocobase:2.2.30', 'image_digest': 'sha256:abc'}
        self.assertEqual(guard.validate_image(policy, 'nocobase/nocobase:2.2.30@sha256:abc'), [])
        self.assertTrue(guard.validate_image(policy, 'nocobase/nocobase:2.2.30'))
        self.assertTrue(guard.validate_image(policy, 'nocobase/nocobase:2.2.30@sha256:def'))
        self.assertTrue(guard.validate_image(policy, ''))

if __name__ == '__main__':
    unittest.main()
