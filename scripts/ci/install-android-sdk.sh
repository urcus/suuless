#!/usr/bin/env bash
set -euo pipefail
: "${ANDROID_HOME:?ANDROID_HOME is required}"
tools_version=13114758
# Official Google repository2-1.xml checksum for cmdline-tools;19.0 (Linux).
tools_sha1=5fdcc763663eefb86a5b8879697aa6088b041e70
sdkmanager="$ANDROID_HOME/cmdline-tools/19.0/bin/sdkmanager"
if [ ! -x "$sdkmanager" ]; then
  work=$(mktemp -d)
  trap 'rm -rf "$work"' EXIT
  curl --fail --location --retry 3 "https://dl.google.com/android/repository/commandlinetools-linux-${tools_version}_latest.zip" -o "$work/tools.zip"
  printf '%s  %s\n' "$tools_sha1" "$work/tools.zip" | sha1sum -c -
  unzip -q "$work/tools.zip" -d "$work"
  mkdir -p "$ANDROID_HOME/cmdline-tools"
  mv "$work/cmdline-tools" "$ANDROID_HOME/cmdline-tools/19.0"
fi
# Capture sdkmanager's status, not yes's expected SIGPIPE status.
set +o pipefail
yes | "$sdkmanager" --sdk_root="$ANDROID_HOME" --licenses >/dev/null
set -o pipefail
"$sdkmanager" --sdk_root="$ANDROID_HOME" 'platforms;android-36' 'build-tools;35.0.0' 'platform-tools'
