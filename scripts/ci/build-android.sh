#!/usr/bin/env bash
set -euo pipefail
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
