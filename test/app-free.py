from contextlib import chdir
import json
import hashlib
import gzip
import io
import os
from pathlib import Path
import runpy
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
fixture = runpy.run_path(str(ROOT / 'scripts/app-free.py'))


class AppFreeFixtureTests(unittest.TestCase):
    def test_native_assets_are_deterministic_and_execute_the_selected_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for version in ['0.0.100-rc.0', '0.0.100']:
                a, b = root / ('a-' + version), root / ('b-' + version)
                fixture['build'](version, a, True)
                fixture['build'](version, b, True)
                name = 'npm-actions-native-fixture_linux_x64.tar.gz'
                self.assertEqual((a / name).read_bytes(), (b / name).read_bytes())
                with tarfile.open(fileobj=io.BytesIO((a / name).read_bytes()), mode='r:gz') as archive:
                    entry = archive.getmembers()[0]
                    self.assertEqual(entry.name, 'bin/npm-actions-native-fixture')
                    target = root / 'native'
                    target.write_bytes(archive.extractfile(entry).read())
                    target.chmod(0o755)
                self.assertEqual(subprocess.check_output([str(target), '--version'], text=True).strip(), version)
                self.assertEqual((a / 'version.txt').read_text(), version + '\n')

    def test_invalid_versions_fail_before_output_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'output'
            for version in ['latest', '1.2.3; touch /tmp/unwanted', '01.2.3', '1.2.3-beta.0']:
                with self.assertRaises(ValueError): fixture['build'](version, path, True)
                self.assertFalse(path.exists())

    def test_candidate_and_reconciliation_guards(self):
        env = dict(GITHUB_REPOSITORY='releaseway/release-fixture', ACTIONS_REF='a' * 40, RC_TAG='', STABLE_TAG='')
        with patch.dict(os.environ, env, clear=True): fixture['validate']()
        for changed in [dict(ACTIONS_REF='main'), dict(GITHUB_REPOSITORY='other/repo'), dict(RC_TAG='app-free-v0.1.0-rc.0'), dict(ACTIONS_REF='0' * 40)]:
            with patch.dict(os.environ, {**env, **changed}, clear=True):
                with self.assertRaises(ValueError): fixture['validate']()


    def test_pages_digest_adapts_the_existing_prefixed_output(self):
        version = b'0.1.2\n'
        original = dict(channels={'stable': {'asset_sha256': hashlib.sha256(version).hexdigest()}})
        env = dict(HOMEBREW='skipped', PAGES='success', PAGE_URL='https://releaseway.github.io/release-fixture/', DEPLOYMENT_ID='123', CONTENT_DIGEST='sha256:' + 'e' * 64)
        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            path = Path('app-free-acceptance.json')
            path.write_text(json.dumps(original))
            with patch.dict(os.environ, env, clear=True), patch('urllib.request.urlopen', return_value=io.BytesIO(version)):
                fixture['delivery']()
            result = json.loads(path.read_text())
            self.assertEqual(result['pages']['content_digest'], 'e' * 64)
            self.assertEqual(result['pages']['served_sha256'], hashlib.sha256(version).hexdigest())
            with patch.dict(os.environ, {**env, 'CONTENT_DIGEST': 'e' * 64}, clear=True), patch('urllib.request.urlopen', return_value=io.BytesIO(version)):
                with self.assertRaises(ValueError): fixture['delivery']()



if __name__ == '__main__': unittest.main()
