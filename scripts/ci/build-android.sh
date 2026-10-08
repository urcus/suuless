#!/usr/bin/env bash
set -euo pipefail
# Published debug APKs must keep their signing identity across disposable runners.
# Local and unprotected builds can still use the SDK's local debug key.
if [[ -n "${ANDROID_DEBUG_KEYSTORE_BASE64:-}" ]]; then
  signing_dir="$(mktemp -d)"
  trap 'rm -rf -- "$signing_dir"' EXIT
  export ANDROID_DEBUG_KEYSTORE_PATH="$signing_dir/debug.keystore"
  (umask 077; printf '%s' "$ANDROID_DEBUG_KEYSTORE_BASE64" | base64 --decode > "$ANDROID_DEBUG_KEYSTORE_PATH")
  unset ANDROID_DEBUG_KEYSTORE_BASE64
elif [[ "${CI_COMMIT_TAG:-}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ && "${CI_COMMIT_REF_PROTECTED:-}" == true ]]; then
  echo 'ANDROID_DEBUG_KEYSTORE_BASE64 is required for protected release tags.' >&2
  exit 1
fi
version="${CI_COMMIT_TAG:-0.1.0-dev.${CI_PIPELINE_IID:-local}}"
version="${version#v}"
version_code="${CI_PIPELINE_IID:-1}"
./android/gradlew -p android --no-daemon \
  -PappVersionName="$version" -PappVersionCode="$version_code" \
  assembleDebug assembleRelease lintDebug lintRelease
mkdir -p dist/android
cp android/app/build/outputs/apk/debug/app-debug.apk "dist/android/stop-clop-${version}-debug.apk"
cp android/app/build/outputs/apk/release/app-release-unsigned.apk "dist/android/stop-clop-${version}-release-unsigned.apk"
(
  cd dist/android
  sha256sum ./*.apk > SHA256SUMS
)
