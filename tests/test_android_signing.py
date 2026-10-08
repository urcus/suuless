"""Release signing is mandatory, private, and cleaned up even on build failure."""
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/ci/build-android.sh'


class AndroidSigningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'android').mkdir()
        wrapper = self.root / 'android/gradlew'
        wrapper.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
key = os.environ.get('ANDROID_DEBUG_KEYSTORE_PATH')
pathlib.Path('build-observation.json').write_text(json.dumps({
    'key_path': key,
    'content': pathlib.Path(key).read_text() if key else None,
    'mode': pathlib.Path(key).stat().st_mode & 0o777 if key else None,
    'secret_in_child': 'ANDROID_DEBUG_KEYSTORE_BASE64' in os.environ,
}))
if os.environ.get('FAIL_BUILD'): sys.exit(1)
for variant, name in [('debug', 'app-debug.apk'), ('release', 'app-release-unsigned.apk')]:
    folder = pathlib.Path('android/app/build/outputs/apk') / variant
    folder.mkdir(parents=True)
    (folder / name).write_bytes(b'test APK')
''')
        wrapper.chmod(0o700)

    def run_build(self, **env):
        return subprocess.run(['bash', str(SCRIPT)], cwd=self.root,
                              env={'PATH': os.environ['PATH'], **env}, capture_output=True, text=True)

    def test_protected_release_requires_key(self):
        result = self.run_build(CI_COMMIT_TAG='v0.2.1', CI_COMMIT_REF_PROTECTED='true')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ANDROID_DEBUG_KEYSTORE_BASE64 is required', result.stderr)
        self.assertFalse((self.root / 'build-observation.json').exists())

    def test_local_build_keeps_local_signing(self):
        self.assertEqual(self.run_build().returncode, 0)
        observed = json.loads((self.root / 'build-observation.json').read_text())
        self.assertIsNone(observed['key_path'])

    def test_stable_signing_and_cleanup_after_success_or_failure(self):
        for fail in ['', '1']:
            with self.subTest(build_failure=bool(fail)):
                result = self.run_build(ANDROID_DEBUG_KEYSTORE_BASE64=base64.b64encode(b'private-test-fixture').decode(),
                                        CI_COMMIT_TAG='v0.2.1', CI_COMMIT_REF_PROTECTED='true', FAIL_BUILD=fail)
                self.assertEqual(result.returncode, 1 if fail else 0)
                observed = json.loads((self.root / 'build-observation.json').read_text())
                self.assertEqual(observed['content'], 'private-test-fixture')
                self.assertEqual(observed['mode'], 0o600)
                self.assertFalse(observed['secret_in_child'])
                self.assertFalse(Path(observed['key_path']).parent.exists())
                self.assertNotIn('private-test-fixture', result.stdout + result.stderr)

    def test_invalid_key_encoding_stops_before_build(self):
        result = self.run_build(ANDROID_DEBUG_KEYSTORE_BASE64='not!base64')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'build-observation.json').exists())
