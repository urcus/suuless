"""Install a reviewed Linux tool archive with its pinned SHA-256."""
import hashlib
import io
from pathlib import Path
import platform
import sys
import tarfile
from urllib.request import urlopen

TOOLS = {
    'trivy': ('https://github.com/aquasecurity/trivy/releases/download/v0.75.0/trivy_0.75.0_Linux-64bit.tar.gz', 'c6e65abddb348e25f10549df887045629cf28cc72453cd1c63acb717316b3f3f'),
    'gitleaks': ('https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz', '551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb'),
    'crane': ('https://github.com/google/go-containerregistry/releases/download/v0.22.1/go-containerregistry_Linux_x86_64.tar.gz', '0ab7a1d6932a213aed964ce97666c3077fe691c8606413674a8b3e0b9ec4cda0'),
}


ARM64_TOOLS = {
    'trivy': ('https://github.com/aquasecurity/trivy/releases/download/v0.75.0/trivy_0.75.0_Linux-ARM64.tar.gz', 'a1ee9f6ffb7d112b64ff726a2a0717c21175c1114361391f4a132956751a13b3'),
}


def install(name, destination):
    machine = platform.machine()
    if platform.system() != 'Linux' or machine not in ('x86_64', 'amd64', 'aarch64', 'arm64'):
        raise SystemExit('These pinned archives require Linux amd64 or arm64.')
    available = ARM64_TOOLS if machine in ('aarch64', 'arm64') else TOOLS
    if name not in available:
        raise SystemExit(f'{name}: no pinned archive for {machine}')
    url, digest = available[name]
    # URLs are fixed HTTPS constants above.
    with urlopen(url, timeout=120) as response:  # nosec B310
        archive = response.read()
    if hashlib.sha256(archive).hexdigest() != digest:
        raise SystemExit(f'{name}: archive SHA-256 mismatch')
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as source:
        member = source.getmember(name)
        if not member.isfile():
            raise SystemExit('Expected a regular executable')
        data = source.extractfile(member).read()
    destination.mkdir(parents=True, exist_ok=True)
    binary = destination / name
    binary.write_bytes(data)
    binary.chmod(0o755)
    print(f'Installed verified {name} at {binary}')


if __name__ == '__main__':
    install(sys.argv[1], Path(sys.argv[2] if len(sys.argv) > 2 else '.cache/security-bin'))
