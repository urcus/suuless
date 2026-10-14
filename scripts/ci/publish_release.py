"""Upload durable release files and upsert a GitLab release using CI_JOB_TOKEN."""
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


class GitLab:
    def __init__(self, environment):
        self.base = f"{environment['CI_API_V4_URL']}/projects/{environment['CI_PROJECT_ID']}"
        self.token = environment['CI_JOB_TOKEN']
        self.context = ssl.create_default_context()
        ca = environment.get('CI_SERVER_TLS_CA_FILE')
        if ca and Path(ca).is_file():
            self.context.load_verify_locations(ca)

    def request(self, method, path, data=None, content_type='application/json', missing_ok=False):
        request = Request(self.base + path, data=data, method=method,
                          headers={'JOB-TOKEN': self.token, 'Content-Type': content_type})
        try:
            # origin comes from trusted CI_API_V4_URL; paths are constructed internally.
            with urlopen(request, context=self.context, timeout=120) as response:  # nosec B310
                return response.read()
        except HTTPError as error:
            if error.code == 404 and missing_ok:
                return None
            raise RuntimeError(f'GitLab {method} {path}: HTTP {error.code}') from None

    def json(self, method, path, payload=None, missing_ok=False):
        result = self.request(method, path, json.dumps(payload).encode() if payload is not None else None,
                              missing_ok=missing_ok)
        return json.loads(result) if result else None

    def upload(self, path, content):
        existing = self.request('GET', path, missing_ok=True)
        if existing is not None:
            if existing != content:
                raise RuntimeError(f'Refusing to overwrite a different package file: {path}')
            return
        self.request('PUT', path, content, 'application/octet-stream')


def publish(environment, root=Path('.'), client=None):
    tag = environment['CI_COMMIT_TAG']
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', tag) or environment.get('CI_COMMIT_REF_PROTECTED') != 'true':
        raise ValueError('Releases require a protected vX.Y.Z tag')
    version = tag[1:]
    version_code = subprocess.check_output(
        ['bash', str(Path(__file__).with_name('android-version-code.sh')), tag], text=True).strip()
    pipeline = environment['CI_PIPELINE_IID']
    if not pipeline.isdigit():
        raise ValueError('CI_PIPELINE_IID must be numeric')
    image_ref = environment['SUULESS_IMAGE_REF']
    image_name = environment['SUULESS_IMAGE_NAME']
    digest = environment['SUULESS_IMAGE_DIGEST']
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest) or not image_ref.endswith('@' + digest):
        raise ValueError('Invalid image digest or reference')
    android = root / 'dist' / 'android'
    names = [f'suuless-{version}-debug.apk', f'suuless-{version}-release-unsigned.apk']
    files = {name: (android / name).read_bytes() for name in names}
    checksums = (android / 'SHA256SUMS').read_text()
    for name, content in files.items():
        expected = hashlib.sha256(content).hexdigest()
        if f'{expected}  ./{name}' not in checksums.splitlines():
            raise ValueError(f'Checksum mismatch: {name}')
    files['cosign.pub'] = (root / 'cosign.pub').read_bytes()
    files['signature-verification.json'] = (root / 'signature-verification.json').read_bytes()
    verified = json.loads(files['signature-verification.json'])
    if not verified or not all(item['critical']['image']['docker-manifest-digest'] == digest for item in verified):
        raise ValueError('Signature verification does not match the published image')
    files['image-reference.txt'] = f'{image_name}\n{image_ref}\n'.encode()
    # One manifest for every downloadable file, including signature evidence.
    files['SHA256SUMS'] = ''.join(f'{hashlib.sha256(content).hexdigest()}  {name}\n' for name, content in sorted(files.items())).encode()
    client = client or GitLab(environment)
    # Separate pipeline reruns of the same tag; preserve old releases' package files.
    package = f'/packages/generic/suuless/{version}-{pipeline}'
    links = []
    for name, content in files.items():
        path = package + '/' + quote(name, safe='')
        client.upload(path, content)
        links.append(dict(name=name, url=client.base + path,
                          direct_asset_path='/' + name, link_type='package' if name.endswith('.apk') else 'other'))
    description = (
        f'SuuLess {version}\n\n'
        f'- Commit: `{environment["CI_COMMIT_SHA"]}`\n'
        f'- Pipeline: {environment["CI_PIPELINE_URL"]}\n'
        f'- Android versionName: `{version}`; versionCode: `{version_code}`.\n\n'
        f'Image Docker publiée et vérifiée avec Cosign :\n\n```text\n{image_name}\n{image_ref}\n```\n\n'
        'APK debug : installable pour les tests, HTTP local autorisé. Les releases utilisent une clé debug stable ; '
        'les mises à jour conservent la session. Une désinstallation préalable reste nécessaire pour les anciennes versions signées avec une autre clé.\n\n'
        'APK release non signé : HTTPS obligatoire, à signer avec votre clé Android avant installation. '
        'Cosign signe uniquement l’image Docker.\n\n'
        'Les fichiers et SHA256SUMS sont conservés dans le registre de paquets GitLab. '
        'La clé publique Cosign est fournie ; comparez son empreinte à votre clé de confiance avant vérification.'
    )
    path = '/releases/' + quote(tag, safe='')
    payload = dict(name=f'SuuLess {tag}', description=description)
    if client.json('GET', path, missing_ok=True) is None:
        client.json('POST', '/releases', dict(payload, tag_name=tag, assets={'links': links}))
    else:
        client.json('PUT', path, payload)
        current = client.json('GET', path + '/assets/links') or []
        by_name = {link['name']: link['id'] for link in current}
        for link in links:
            link_path = path + '/assets/links'
            if link['name'] in by_name:
                client.json('PUT', link_path + '/' + str(by_name[link['name']]), link)
            else:
                client.json('POST', link_path, link)
    print(f'Release {tag}: {len(files)} durable assets, signed Docker image {image_ref}')


if __name__ == '__main__':
    publish(os.environ)
