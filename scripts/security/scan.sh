#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export PATH="$PWD/.cache/security-bin:$PATH"
export TRIVY_CACHE_DIR="${TRIVY_CACHE_DIR:-$PWD/.cache/trivy}"
mkdir -p test-results/security
case "${1:-}" in
  python)
    pip-audit -r requirements-dev.txt --progress-spinner off --format json --output test-results/security/python.json
    ;;
  npm)
    npm audit --package-lock-only --audit-level=high --json > test-results/security/npm.json
    ;;
  code)
    bandit -r server scripts/ci scripts/security --severity-level medium --confidence-level medium --format json --output test-results/security/bandit.json
    ;;
  secrets)
    # Scan only public working files (including untracked changes locally), never private local/ data.
    snapshot=$(mktemp -d)
    trap 'rm -rf "$snapshot"' EXIT
    git ls-files -z --cached --others --exclude-standard | while IFS= read -r -d '' file; do
      case "$file" in local/*|old/*) continue ;; esac
      if [[ -f "$file" && ! -L "$file" ]]; then
        mkdir -p "$snapshot/$(dirname "$file")"
        cp "$file" "$snapshot/$file"
      fi
    done
    gitleaks dir "$snapshot" --no-banner --redact --exit-code 1 --report-format json --report-path "$PWD/test-results/security/gitleaks.json"
    ;;
  config)
    trivy config --severity HIGH,CRITICAL --exit-code 1 --format json --output test-results/security/config.json --skip-dirs local --skip-dirs old --skip-dirs .git --skip-dirs .venv --skip-dirs node_modules --skip-dirs .cache --skip-dirs .gradle --skip-dirs .android-sdk --skip-dirs android/app/build --skip-dirs test-results --skip-dirs dist .
    ;;
  image)
    : "${2:?Path to the built Docker archive is required}"
    trivy image --input "$2" --scanners vuln --severity HIGH,CRITICAL --exit-code 1 --format json --output test-results/security/image.json
    ;;
  *) echo 'Usage: scan.sh python|npm|code|secrets|config|image [archive]' >&2; exit 2 ;;
esac
