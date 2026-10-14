#!/usr/bin/env bash
set -euo pipefail
: "${RELEASE_TAG:?}"
: "${VERSION_CODE:?}"
: "${GITHUB_SHA:?}"
: "${GITHUB_SERVER_URL:?}"
: "${GITHUB_REPOSITORY:?}"
: "${GITHUB_RUN_ID:?}"
[[ "$RELEASE_TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]
version="${RELEASE_TAG#v}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
latest=false
title="SuuLess $RELEASE_TAG"
if [[ "$RELEASE_TAG" == v1.0.0 ]]; then
  latest=true
  title="SuuLess v1.0.0 — First stable release"
fi
cd dist/release
for asset in "suuless-${version}-debug.apk" "suuless-${version}-release-unsigned.apk" image-reference.txt cosign-identity.txt signature-verification.json; do
  test -s "$asset"
done
sha256sum --check SHA256SUMS
sha256sum ./*.apk image-reference.txt cosign-identity.txt signature-verification.json > SHA256SUMS
notes=$(mktemp)
trap 'rm -f "$notes"' EXIT
if [[ -f "$repo_root/docs/releases/$RELEASE_TAG.md" ]]; then
  cat "$repo_root/docs/releases/$RELEASE_TAG.md" > "$notes"
  printf "\n\n" >> "$notes"
fi
cat >> "$notes" <<EOF
SuuLess ${version}

- Commit: \`${GITHUB_SHA}\`
- Build: ${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}
- Android versionName: \`${version}\`; versionCode: \`${VERSION_CODE}\`.

The debug APK is installable and permits local HTTP. Release builds use a stable debug signing key.
The release-unsigned APK requires Android signing before installation and permits HTTPS only.

Docker image (linux/amd64 and linux/arm64), with its multi-platform index signed using Cosign and GitHub OIDC:

\`\`\`text
$(cat image-reference.txt)
\`\`\`

Verify the image using the exact workflow identity in cosign-identity.txt and issuer
https://token.actions.githubusercontent.com. Cosign signs the multi-platform image index, not the APKs.
SHA256SUMS covers every attached asset except the checksum file itself.
EOF
# Reuse a draft after an interrupted upload; never replace an already published release.
if ! gh release view "$RELEASE_TAG" --json isDraft > release-state.json; then
  gh release create "$RELEASE_TAG" --verify-tag --draft --title "$title" --notes-file "$notes"
else
  python3 -c 'import json; assert json.load(open("release-state.json"))["isDraft"], "Release already published; refusing to replace assets"'
fi
gh release upload "$RELEASE_TAG" ./*.apk SHA256SUMS image-reference.txt cosign-identity.txt signature-verification.json --clobber
gh release edit "$RELEASE_TAG" --notes-file "$notes" --draft=false --latest="$latest"
