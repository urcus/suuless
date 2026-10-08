import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.ci.publish_release import publish


class FakeGitLab:
    base = 'https://gitlab.example/api/v4/projects/1'
    def __init__(self):
        self.files = {}
        self.release = None
        self.links = []
    def upload(self, path, content):
        if path in self.files and self.files[path] != content:
            raise RuntimeError('Different existing package')
        self.files[path] = content
    def json(self, method, path, payload=None, missing_ok=False):
        if method == 'GET':
            return self.links if path.endswith('/assets/links') else self.release
        if path.endswith('/releases'):
            self.release = payload
            self.links = [dict(link, id=i) for i, link in enumerate(payload['assets']['links'], 1)]
        elif '/assets/links/' in path:
            identifier = int(path.rsplit('/', 1)[-1])
            self.links = [dict(payload, id=identifier) if link['id'] == identifier else link for link in self.links]
        elif path.endswith('/assets/links'):
            self.links.append(dict(payload, id=len(self.links)+1))
        else:
            self.release.update(payload)
        return {}


class ReleaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        android = self.root / 'dist/android'
        android.mkdir(parents=True)
        sums = []
        for kind in ['debug', 'release-unsigned']:
            name = f'stop-clop-1.2.3-{kind}.apk'
            content = kind.encode()
            (android / name).write_bytes(content)
            sums.append(f'{hashlib.sha256(content).hexdigest()}  ./{name}\n')
        (android / 'SHA256SUMS').write_text(''.join(sums))
        (self.root / 'cosign.pub').write_text('public-key-fixture')
        digest = 'sha256:' + 'a'*64
        (self.root / 'signature-verification.json').write_text(json.dumps([{'critical': {'image': {'docker-manifest-digest': digest}}}]))
        self.env = dict(CI_COMMIT_TAG='v1.2.3', CI_COMMIT_REF_PROTECTED='true', CI_PIPELINE_IID='123',
                        CI_COMMIT_SHA='abc123', CI_PIPELINE_URL='https://gitlab.example/pipelines/123',
                        STOP_CLOP_IMAGE_NAME='harbor.example/project/stop-clop:1.2.3',
                        STOP_CLOP_IMAGE_REF='harbor.example/project/stop-clop@'+digest,
                        STOP_CLOP_IMAGE_DIGEST=digest)
        self.client = FakeGitLab()

    def test_create_and_retry_release(self):
        publish(self.env, self.root, self.client)
        publish(self.env, self.root, self.client)
        self.assertEqual(len(self.client.files), 6)
        self.assertEqual(len(self.client.links), 6)
        self.assertEqual(self.client.release['tag_name'], 'v1.2.3')
        self.assertTrue(all('/packages/generic/stop-clop/1.2.3-123/' in link['url'] for link in self.client.links))
        self.assertIn('non signé', self.client.release['description'])
        checksums = next(content for path,content in self.client.files.items() if path.endswith('/SHA256SUMS'))
        self.assertEqual(len(checksums.splitlines()), 5)

    def test_reject_non_release_or_unprotected_tag(self):
        for key, value in [('CI_COMMIT_TAG','v1.2.3-rc1'), ('CI_COMMIT_REF_PROTECTED','false')]:
            with self.assertRaises(ValueError):
                publish(dict(self.env, **{key:value}), self.root, self.client)
        self.assertFalse(self.client.files)

    def test_verify_inputs_before_upload(self):
        (self.root/'dist/android/stop-clop-1.2.3-debug.apk').write_bytes(b'corrupt')
        with self.assertRaises(ValueError): publish(self.env, self.root, self.client)
        self.assertFalse(self.client.files)

    def test_reject_wrong_signature_digest(self):
        (self.root/'signature-verification.json').write_text('[]')
        with self.assertRaises(ValueError): publish(self.env, self.root, self.client)
        self.assertFalse(self.client.files)

    def test_new_pipeline_updates_links_without_expiring_old_files(self):
        publish(self.env, self.root, self.client)
        publish(dict(self.env,CI_PIPELINE_IID='124'), self.root, self.client)
        self.assertEqual(len(self.client.files),12)
        self.assertTrue(all('/1.2.3-124/' in link['url'] for link in self.client.links))
