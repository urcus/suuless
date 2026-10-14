#!/usr/bin/env bash
# Shared by GitLab, GitHub and release notes. Never use a CI counter for releases.
set -euo pipefail
tag="${1:-}"
if [[ ! "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo 1
  exit 0
fi
if [[ ! "$tag" =~ ^v(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})$ ]]; then
  echo 'Android release tags require canonical vMAJOR.MINOR.PATCH (no leading zeroes).' >&2
  exit 1
fi
major="${BASH_REMATCH[1]}"
minor="${BASH_REMATCH[2]}"
patch="${BASH_REMATCH[3]}"
if ((major > 1099)); then
  echo 'Android version range exceeded: major <= 1099, minor and patch <= 999.' >&2
  exit 1
fi
echo "$((1000000000 + major * 1000000 + minor * 1000 + patch))"
