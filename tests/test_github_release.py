"""Exercise release publication without contacting GitHub."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/ci/publish-github-release.sh'


class GitHubReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / 'dist/release'
        self.assets.mkdir(parents=True)
        self.apks = ['suuless-1.2.3-debug.apk', 'suuless-1.2.3-release-unsigned.apk']
        for name in self.apks:
            (self.assets / name).write_bytes(name.encode())
        (self.assets / 'SHA256SUMS').write_text(''.join(
            f'{hashlib.sha256(name.encode()).hexdigest()}  ./{name}\n' for name in self.apks))
        for name in ['image-reference.txt', 'cosign-identity.txt', 'signature-verification.json']:
            (self.assets / name).write_text('example evidence\n')
        binary = self.root / 'gh'
        binary.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
with open(os.environ['CALL_LOG'], 'a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\\n')
command = sys.argv[2]
if command == 'view':
    state = os.environ['RELEASE_STATE']
    if state == 'missing':
        sys.exit(1)
    print(json.dumps({'isDraft': state == 'draft'}))
if command == 'upload' and os.environ.get('FAIL_UPLOAD'):
    sys.exit(1)
if '--notes-file' in sys.argv:
    notes = Path(sys.argv[sys.argv.index('--notes-file') + 1]).read_text()
    assert 'Android versionName' in notes
    Path(os.environ['CALL_LOG'] + '.notes').write_text(notes)
''')
        binary.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ['PATH'],
                        RELEASE_TAG='v1.2.3', VERSION_CODE='42', GITHUB_SHA='a' * 40,
                        GITHUB_SERVER_URL='https://github.com', GITHUB_REPOSITORY='urcus/suuless',
                        GITHUB_RUN_ID='123', RELEASE_STATE='missing', CALL_LOG=str(self.root / 'calls'))

    def run_script(self):
        return subprocess.run(['bash', str(SCRIPT)], cwd=self.root, env=self.env,
                              capture_output=True, text=True)

    def calls(self):
        path = self.root / 'calls'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_create_upload_then_publish_with_complete_checksums(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call[1] for call in self.calls()], ['view', 'create', 'upload', 'edit'])
        checks = (self.assets / 'SHA256SUMS').read_text().splitlines()
        self.assertEqual(len(checks), 5)
        for line in checks:
            digest, name = line.split()
            self.assertEqual(digest, hashlib.sha256((self.assets / name).read_bytes()).hexdigest())

    def test_first_stable_release_has_downloads_and_is_latest(self):
        self.env['RELEASE_TAG'] = 'v1.0.0'
        for name in self.apks:
            (self.assets / name).rename(self.assets / name.replace('1.2.3', '1.0.0'))
        (self.assets / 'SHA256SUMS').write_text(''.join(
            f'{hashlib.sha256(path.read_bytes()).hexdigest()}  ./{path.name}\n'
            for path in self.assets.glob('*.apk')))
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        notes = (self.root / 'calls.notes').read_text()
        self.assertIn('first stable release', notes)
        self.assertIn('ghcr.io/urcus/suuless:1.0.0', notes)
        self.assertIn('/releases/download/v1.0.0/suuless-1.0.0-debug.apk', notes)
        self.assertIn('--latest=true', self.calls()[-1])

    def test_patch_release_has_exports_and_admin_fix_notes(self):
        self.env['RELEASE_TAG'] = 'v1.0.1'
        for name in self.apks:
            (self.assets / name).rename(self.assets / name.replace('1.2.3', '1.0.1'))
        (self.assets / 'SHA256SUMS').write_text(''.join(
            f'{hashlib.sha256(path.read_bytes()).hexdigest()}  ./{path.name}\n'
            for path in self.assets.glob('*.apk')))
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        notes = (self.root / 'calls.notes').read_text()
        self.assertIn('first administrator', notes)
        self.assertIn('ghcr.io/urcus/suuless:1.0.1', notes)
        self.assertIn('/releases/download/v1.0.1/suuless-1.0.1-debug.apk', notes)
        self.assertIn('--latest=true', self.calls()[-1])

    def test_resume_draft(self):
        self.env['RELEASE_STATE'] = 'draft'
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual([call[1] for call in self.calls()], ['view', 'upload', 'edit'])

    def test_published_release_is_not_modified(self):
        self.env['RELEASE_STATE'] = 'published'
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual([call[1] for call in self.calls()], ['view'])

    def test_corrupt_apk_prevents_network_calls(self):
        (self.assets / self.apks[0]).write_bytes(b'corrupt')
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_missing_evidence_prevents_network_calls(self):
        (self.assets / 'signature-verification.json').unlink()
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_failed_upload_leaves_draft_unpublished(self):
        self.env['FAIL_UPLOAD'] = '1'
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual([call[1] for call in self.calls()], ['view', 'create', 'upload'])

    def test_non_release_tag_prevents_network_calls(self):
        self.env['RELEASE_TAG'] = 'v1.2.3-rc1'
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.calls(), [])
