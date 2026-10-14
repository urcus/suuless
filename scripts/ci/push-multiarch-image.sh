#!/usr/bin/env bash
set -euo pipefail
archive_dir=${1:?Directory containing image-amd64.tar.gz and image-arm64.tar.gz required}
image=${2:?Destination image tag required}
export PATH="$PWD/.cache/security-bin:$PATH"
script_dir=$(cd "$(dirname "$0")" && pwd)
# Reject missing, duplicate or mislabeled platforms before the first upload.
python - "$archive_dir" <<'PY'
import json
from pathlib import Path
import sys
import tarfile

for arch in ('amd64', 'arm64'):
    with tarfile.open(Path(sys.argv[1]) / f'image-{arch}.tar.gz', 'r:gz') as archive:
        manifests = json.load(archive.extractfile('manifest.json'))
        if len(manifests) != 1:
            raise SystemExit(f'{arch}: expected one image per archive')
        config = json.load(archive.extractfile(manifests[0]['Config']))
        if (config.get('os'), config.get('architecture')) != ('linux', arch):
            raise SystemExit(f'{arch}: archive platform mismatch')
PY
refs=()
for arch in amd64 arm64; do
  # Preserve the common helper's contract for GitLab's single-platform publication.
  GITHUB_OUTPUT='' bash "$script_dir/push-scanned-image.sh" "$archive_dir/image-$arch.tar.gz" "$image-$arch"
  refs+=("$(cat dist/image/pushed-reference.txt)")
done
# Use immutable child references, never rebuild or resolve the temporary tags again.
crane index append -m "${refs[0]}" -m "${refs[1]}" -t "$image"
digest=$(crane digest "$image")
[[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]]
ref="${image%:*}@$digest"
crane manifest "$ref" > dist/image/published-index.json
python - dist/image/published-index.json "${refs[0]##*@}" "${refs[1]##*@}" <<'PY'
import json
import sys

with open(sys.argv[1]) as source:
    manifests = json.load(source).get('manifests', [])
actual = {(m.get('platform', {}).get('os'), m.get('platform', {}).get('architecture'), m['digest']) for m in manifests}
expected = {('linux', 'amd64', sys.argv[2]), ('linux', 'arm64', sys.argv[3])}
if len(manifests) != 2 or actual != expected:
    raise SystemExit('Published index does not match both scanned images')
PY
printf 'SUULESS_IMAGE_NAME=%s\nSUULESS_IMAGE_DIGEST=%s\nSUULESS_IMAGE_REF=%s\n' "$image" "$digest" "$ref" > image.env
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then printf 'digest=%s\n' "$digest" >> "$GITHUB_OUTPUT"; fi
