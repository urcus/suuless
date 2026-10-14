#!/usr/bin/env bash
set -euo pipefail
archive=${1:?Image archive required}
image=${2:?Destination image required}
export PATH="$PWD/.cache/security-bin:$PATH"
# The archive is the same artifact checked by the image scan job. Never rebuild here.
mkdir -p dist/image
# crane expects an uncompressed Docker tar; transport artifacts are gzip-compressed.
upload_dir=$(mktemp -d)
trap 'rm -rf "$upload_dir"' EXIT
gzip -dc "$archive" > "$upload_dir/image.tar"
crane push "$upload_dir/image.tar" "$image" --image-refs dist/image/pushed-reference.txt
ref=$(cat dist/image/pushed-reference.txt)
digest=${ref##*@}
[[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]]
[[ "$ref" == "${image%:*}@$digest" || "$ref" == "$image@$digest" ]]
printf 'SUULESS_IMAGE_NAME=%s\nSUULESS_IMAGE_DIGEST=%s\nSUULESS_IMAGE_REF=%s\n' "$image" "$digest" "${image%:*}@$digest" > image.env
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then printf 'digest=%s\n' "$digest" >> "$GITHUB_OUTPUT"; fi
