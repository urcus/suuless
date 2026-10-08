#!/usr/bin/env bash
set -euo pipefail
export CI_WEB_PORT="${CI_WEB_PORT:-8080}"
export BASE_URL="http://127.0.0.1:${CI_WEB_PORT}"
.venv/bin/python - <<'CHECK'
import os, socket
with socket.socket() as probe:
    probe.bind(('127.0.0.1', int(os.environ['CI_WEB_PORT'])))
CHECK
mkdir -p test-results
.venv/bin/gunicorn --bind "127.0.0.1:${CI_WEB_PORT}" 'server.app:create_app()' >test-results/server.log 2>&1 &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true; wait "$server_pid" 2>/dev/null || true' EXIT
.venv/bin/python - <<'PY'
import os
import time
import urllib.request
for attempt in range(60):
    try:
        with urllib.request.urlopen(os.environ['BASE_URL'] + '/healthz', timeout=1) as response:
            if response.status == 200:
                break
    except OSError:
        time.sleep(0.5)
else:
    raise SystemExit('Server did not become healthy; see test-results/server.log')
PY
npm run test:web
