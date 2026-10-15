# Development and verification

[Documentation](../README.md) · [Project home](../../README.md)

Run commands from the repository root unless noted. Python 3.13 is recommended. The web interface needs no JavaScript build.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/flask --app server.app:create_app run --port 8080
```

The Flask development server is for local testing. Docker uses Gunicorn. Runtime-only installations use `requirements.txt`; development dependencies add OpenAPI validation and response-schema checks.

## PostgreSQL integration tests

Install `requirements-dev.txt`; the pinned binary Psycopg wheel includes its native libraries. Supply `TEST_POSTGRES_URL` for a disposable PostgreSQL 17 service, then run the normal Python suite. The test role needs `CREATEDB`; each test creates/drops a randomly named database and never clears an existing database. Do not point this at production. Without the variable, PostgreSQL integration cases are explicitly skipped; SQLite tests still run. GitHub and GitLab API jobs provide an isolated PostgreSQL service and run both backends.

Coverage includes migration dry-run/commit, table-content verification, identity sequences, preserved sessions/keys/costs, concurrent idempotency and startup, rollback, SSE, coaching and reports. The browser test server can also use `DATABASE_URL`; use an empty disposable target. The ordinary temporary SQLite path remains the default.

## Browser tests

Use a test database and allow registration: tests create accounts and entries.

```sh
npm ci
npx playwright install chromium
BASE_URL=http://127.0.0.1:8080 npm run test:web
```

For a temporary server managed by the CI script:

```sh
CI_WEB_PORT=18080 DATABASE=/tmp/stop-clop-tests.sqlite ALLOW_REGISTRATION=true bash scripts/ci/test-web.sh
```

Screenshots and logs go to ignored `test-results/`. API tests use temporary databases. Coverage includes isolation, migration, historical prices, mixed currencies, date boundaries/DST, pagination, export, tokens, concurrent idempotent writes, coaching and release publication. The administration browser suite starts its own temporary server and captures mail locally; it never sends external email. It covers role routing, SMTP forms, invitations, activation, password reset and revocation.

Browser suites include multilingual settings, time-zone detection, unsaved edits, charts, mobile layouts and coaching.

## Android tests

With JDK 17 installed, `bash scripts/ci/test-reminders.sh` checks reminder timing without an emulator. See [Android](../user-guide/android.md) for SDK builds and lint. CI calls this policy check before building both APK variants.

## API contract

[`openapi.yaml`](../api/openapi.yaml) documents the current HTTP API. Update it whenever route methods, fields, status codes or validation change. Unit tests compare Flask route coverage, validate the specification and check representative responses against its schemas. HTML and static-asset routes are intentionally outside the contract.

## Continuous integration

GitLab and GitHub run independent checks using the shared test and build scripts. Checks cover Python and OpenAPI, browser journeys, Android builds and lint. Both platforms build and scan Docker images. GitHub builds AMD64 and ARM64 on native runners, with a smoke test and scan for each; GitLab targets AMD64. Repository security checks run first in parallel. Once they all pass, API and browser tests run in parallel. Both tests must pass before Android and container builds start in parallel. The image scan follows its build; publication requires every scanned image and the successful Android build. GitHub assembles and signs a multi-platform index from the two scanned images. A failed prerequisite skips its dependent jobs. Security checks cover Python/npm dependencies, Python source (Bandit), public working-tree secrets (Gitleaks), Docker/Kubernetes configuration and image vulnerabilities (Trivy). A security failure blocks publication. Maintainer instructions for signing, publication and repository configuration are kept in the ignored `local/` directory.

## Contributions

GitLab is the primary repository; GitHub receives the public mirror. Integrate GitHub proposals into GitLab before synchronization. Both CI configurations are versioned together, but secrets are configured separately. Avoid concurrent edits to the same file when working in multiple sessions.

## Documentation

Keep guides in English and organize them by audience under `user-guide/`, `deployment/`, `development/` or `api/`. Update relative links when moving files. Use real demonstration accounts for screenshots; keep diagram HTML and SVG exports together in `assets/diagrams/`. See [visual assets](../assets/README.md). Public Kubernetes templates belong in `deploy/kubernetes/`; private working copies belong in ignored `local/`.
