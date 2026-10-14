"""Publication must remain gated by every independent validation branch."""
import os
import io
import importlib.util
import hashlib
from unittest.mock import patch
import json
import sys
import tarfile
import gzip
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


def needs(job):
    return {value if isinstance(value, str) else value['job'] for value in job.get('needs', [])}


def ancestors(jobs, name):
    result = set()
    pending = list(needs(jobs[name]))
    while pending:
        dependency = pending.pop()
        if dependency not in result:
            result.add(dependency)
            pending.extend(needs(jobs[dependency]))
    return result


class SecurityCITests(unittest.TestCase):
    def test_github_publication_waits_for_all_checks(self):
        jobs = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())['jobs']
        self.assertTrue({'api', 'web', 'android', 'container', 'security', 'metadata'} <= ancestors(jobs, 'publish'))
        self.assertEqual(needs(jobs['android']), {'metadata', 'api', 'web'})
        self.assertEqual(needs(jobs['container']), {'api', 'web'})
        for name in ('api', 'web'):
            self.assertEqual(needs(jobs[name]), {'security'})
        self.assertFalse(needs(jobs['security']))
        self.assertEqual(set(jobs['security']['strategy']['matrix']['scan']), {'python', 'npm', 'code', 'secrets', 'config'})
        self.assertEqual(jobs['container']['strategy']['matrix']['include'], [
            {'arch': 'amd64', 'runner': 'ubuntu-24.04'},
            {'arch': 'arm64', 'runner': 'ubuntu-24.04-arm'},
        ])
        self.assertFalse(jobs['container']['strategy']['fail-fast'])
        self.assertFalse(jobs['container'].get('continue-on-error', False))
        download = next(step['with'] for step in jobs['publish']['steps']
                        if step.get('with', {}).get('pattern') == 'scanned-image-*')
        self.assertTrue(download['merge-multiple'])
        steps = jobs['container']['steps']
        scan = next(i for i, step in enumerate(steps) if 'scan.sh image' in step.get('run', ''))
        upload = next(i for i, step in enumerate(steps) if step.get('with', {}).get('name') == 'scanned-image-${{ matrix.arch }}')
        self.assertLess(scan, upload)
        self.assertNotIn('if', steps[upload])
        publication = '\n'.join(step.get('run', '') for step in jobs['publish']['steps'])
        self.assertIn('push-multiarch-image.sh', publication)
        self.assertNotIn('docker build', publication)
        self.assertNotIn('always()', jobs['publish'].get('if', ''))

    def test_gitlab_publication_waits_for_all_checks(self):
        jobs = yaml.safe_load((ROOT / '.gitlab-ci.yml').read_text())
        required = {'quality:api', 'quality:web', 'android:build', 'security', 'security:npm', 'image:build', 'image:scan'}
        self.assertTrue(required <= ancestors(jobs, 'image:publish'))
        self.assertTrue(required | {'image:publish', 'image:sign'} <= ancestors(jobs, 'release:publish'))
        for name in ('security', 'security:npm'):
            self.assertEqual(jobs[name]['needs'], [])
            self.assertEqual(jobs[name]['stage'], 'security')
        for name in ('quality:api', 'quality:web'):
            self.assertEqual(needs(jobs[name]), {'security', 'security:npm'})
        for name in ('android:build', 'image:build'):
            self.assertEqual(needs(jobs[name]), {'quality:api', 'quality:web'})
        self.assertEqual(needs(jobs['image:scan']), {'image:build'})
        self.assertIn('--no-push', '\n'.join(jobs['image:build']['script']))
        self.assertNotIn('/kaniko/executor', '\n'.join(jobs['image:publish']['script']))
        for name in required:
            self.assertFalse(jobs[name].get('allow_failure', False))

    def test_scanner_errors_are_not_suppressed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / 'scripts/security/scan.sh'
            script.parent.mkdir(parents=True)
            script.write_bytes((ROOT / 'scripts/security/scan.sh').read_bytes())
            binary = root / 'bin'
            binary.mkdir()
            for command in ('bandit', 'pip-audit', 'npm', 'trivy'):
                stub = binary / command
                stub.write_text('#!/bin/sh\nexit 23\n')
                stub.chmod(0o755)
            for mode in ('python', 'npm', 'code', 'config', 'image'):
                with self.subTest(mode=mode):
                    result = subprocess.run(['bash', str(script), mode, 'image.tar.gz'],
                                            env={**os.environ, 'PATH': str(binary) + ':' + os.environ['PATH']},
                                            capture_output=True)
                    self.assertEqual(result.returncode, 23, result.stderr)

    def test_push_preserves_scanned_reference_and_rejects_invalid_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / '.cache/security-bin/crane'
            binary.parent.mkdir(parents=True)
            binary.write_text('''#!/bin/sh
[ "$1" = push ] && [ -f "$2" ] || exit 9
[ "$(cat "$2")" = "scanned archive" ] || exit 10
printf '%s' "$MOCK_REF" > "$5"
''')
            binary.chmod(0o755)
            (root / 'image.tar.gz').write_bytes(gzip.compress(b'scanned archive'))
            target = 'registry.example.com:5000/project/suuless:1.2.3'
            ref = 'registry.example.com:5000/project/suuless@sha256:' + 'a' * 64
            env = {**os.environ, 'MOCK_REF': ref, 'GITHUB_OUTPUT': str(root / 'output')}
            args = ['bash', str(ROOT / 'scripts/ci/push-scanned-image.sh'), 'image.tar.gz', target]
            result = subprocess.run(args, cwd=root, env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('SUULESS_IMAGE_REF=' + ref, (root / 'image.env').read_text())
            self.assertIn('digest=sha256:' + 'a' * 64, (root / 'output').read_text())
            result = subprocess.run(args, cwd=root, env={**env, 'MOCK_REF': 'invalid'}, capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_multiarch_publication_requires_both_scanned_platforms(self):
        for scenario in ('success', 'missing', 'wrong-platform', 'push-failure', 'wrong-index'):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for arch in ('amd64', 'arm64'):
                    if arch == 'arm64' and scenario == 'missing':
                        continue
                    config_arch = 'amd64' if scenario == 'wrong-platform' else arch
                    with tarfile.open(root / f'image-{arch}.tar.gz', 'w:gz') as archive:
                        for name, value in [('manifest.json', [{'Config': 'config.json', 'Layers': []}]),
                                            ('config.json', {'os': 'linux', 'architecture': config_arch})]:
                            data = json.dumps(value).encode()
                            entry = tarfile.TarInfo(name)
                            entry.size = len(data)
                            archive.addfile(entry, io.BytesIO(data))
                binary = root / '.cache/security-bin/crane'
                binary.parent.mkdir(parents=True)
                binary.write_text('#!' + sys.executable + '\n' + r'''import json, os, sys, tarfile
from pathlib import Path
args = sys.argv[1:]
with open('calls.jsonl', 'a') as log:
    log.write(json.dumps(args) + '\n')
a, b, c = ['sha256:' + char * 64 for char in 'abc']
repo = 'registry.example.com:5000/project/suuless'
if args[0] == 'push':
    with tarfile.open(args[1]) as archive:
        arch = json.load(archive.extractfile('config.json'))['architecture']
    if arch == 'arm64' and os.environ['SCENARIO'] == 'push-failure': sys.exit(23)
    Path(args[4]).write_text(repo + '@' + (a if arch == 'amd64' else b))
elif args[:2] == ['index', 'append']:
    assert args == ['index', 'append', '-m', repo + '@' + a, '-m', repo + '@' + b, '-t', repo + ':1.2.3']
elif args[0] == 'digest': print(c)
elif args[0] == 'manifest':
    assert args[1] == repo + '@' + c
    entries = [{'digest': digest, 'platform': {'os': 'linux', 'architecture': arch}}
               for arch, digest in [('amd64', a), ('arm64', b)]]
    if os.environ['SCENARIO'] == 'wrong-index': entries.pop()
    print(json.dumps({'manifests': entries}))
else: sys.exit(99)
''')
                binary.chmod(0o755)
                result = subprocess.run(['bash', str(ROOT / 'scripts/ci/push-multiarch-image.sh'),
                                         '.', 'registry.example.com:5000/project/suuless:1.2.3'],
                                        cwd=root, capture_output=True, text=True,
                                        env={**os.environ, 'SCENARIO': scenario, 'GITHUB_OUTPUT': str(root / 'output')})
                if scenario == 'success':
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual((root / 'output').read_text(), 'digest=sha256:' + 'c' * 64 + '\n')
                    self.assertIn('@sha256:' + 'c' * 64, (root / 'image.env').read_text())
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse((root / 'output').exists())
                    if scenario in ('missing', 'wrong-platform'):
                        self.assertFalse((root / 'calls.jsonl').exists(), 'Preflight must reject before any upload')
                    if scenario == 'push-failure':
                        self.assertNotIn('append', (root / 'calls.jsonl').read_text())

    def test_arm64_scanner_installation_verifies_the_archive(self):
        spec = importlib.util.spec_from_file_location('security_installer', ROOT / 'scripts/security/install-tool.py')
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
            entry = tarfile.TarInfo('trivy')
            entry.size = 4
            archive.addfile(entry, io.BytesIO(b'tool'))
        data = buffer.getvalue()
        url = installer.ARM64_TOOLS['trivy'][0]
        with tempfile.TemporaryDirectory() as tmp, patch.object(installer.platform, 'system', return_value='Linux'), \
             patch.object(installer.platform, 'machine', return_value='aarch64'), \
             patch.dict(installer.ARM64_TOOLS, {'trivy': (url, hashlib.sha256(data).hexdigest())}):
            with patch.object(installer, 'urlopen', return_value=io.BytesIO(data)) as download:
                installer.install('trivy', Path(tmp))
                download.assert_called_once_with(url, timeout=120)
                self.assertEqual((Path(tmp) / 'trivy').read_bytes(), b'tool')
            with patch.object(installer, 'urlopen', return_value=io.BytesIO(b'corrupt')):
                with self.assertRaisesRegex(SystemExit, 'SHA-256 mismatch'):
                    installer.install('trivy', Path(tmp))
            with self.assertRaisesRegex(SystemExit, 'no pinned archive'):
                installer.install('crane', Path(tmp))
