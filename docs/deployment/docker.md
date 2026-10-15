# Installation and operations

[Documentation](../README.md) · [Project home](../../README.md)

Run commands from the repository root. Docker Compose builds the image from local sources.

## Start with Docker

```sh
cp .env.example .env
docker compose up -d --build
```

Open <http://localhost:8080>, create accounts and adjust price, currency, language and time zone in **Settings & integrations**. Language can also be selected before login. The default EUR 12 per 20-cigarette pack is an example to customize.

The port is accessible only from the host by default. For LAN testing with the Android debug APK, set `BIND_ADDRESS=0.0.0.0` in `.env`, recreate the container with `docker compose up -d`, then use `http://SERVER_IP:8080`. The Android emulator normally reaches its host at `http://10.0.2.2:8080`. The phone needs network access to the server.

For remote use, provide an HTTPS reverse proxy. Release APKs reject HTTP. No proxy or certificate is bundled. The service listens on port 8080 and exposes `/healthz`.

To create the first administrator, including on an existing installation with public registration disabled, configure `.env`:

```dotenv
ALLOW_REGISTRATION=false
ADMIN_USERNAME=owner
ADMIN_PASSWORD='replace-with-a-long-unique-password'
```

Both `ADMIN_` variables are optional together. When configured, the username must contain 3–40 letters, digits, underscores, dots or hyphens; the password must contain 12–256 characters. The password is passed directly as an environment variable and stored only as a scrypt hash in the selected database. Invalid initial credentials prevent startup without printing their values.

Creation is transactional and happens once, including with multiple server workers. An existing installation without an initialized administrator receives a dedicated admin account; existing users remain unchanged. Once administrator initialization has completed, changing these variables does not reset a password or create another account. A username already held by an ordinary user is rejected. Deleting the initial account does not recreate it on restart. You can remove the variables after initialization. The initial account has the `admin` role and uses a separate administration interface. See [administration, invitations and SMTP](administration.md).

After creating the required accounts, set `ALLOW_REGISTRATION=false` in `.env` and run `docker compose up -d` to close registration. Existing accounts continue to work.

```sh
docker compose logs -f
docker compose down
```

`down` preserves the volume; **`down -v` deletes the data**. The image runs as UID 10001. A bind mount replacing the named volume must be writable by this UID.

## Image base and Raspberry Pi

The runtime uses Python 3.13 on Alpine 3.24, pinned to a multi-platform image-index digest in the Dockerfile. Dependencies must have binary wheels; builds fail rather than silently installing a compiler. After installation, the image removes `pip` and `ensurepip`, including their bundled installer dependencies. UID/GID 10001, `/data/stopclop.db`, port 8080 and the health check remain the runtime contract.

| Platform | Current status |
|---|---|
| `linux/amd64` | Built and scanned by GitHub and GitLab |
| `linux/arm64` | Native build, smoke test and scan configured on GitHub; first CI execution pending |
| `linux/arm/v7` | Not validated; no 32-bit Raspberry Pi support claim |

For the Raspberry Pi target, use an ARM64-capable Pi with a 64-bit OS and Docker. A native `docker compose build` selects the host architecture automatically. Cross-building on an x86 machine requires an ARM64 builder or configured emulation:

```sh
docker buildx build --platform linux/arm64 --load -t suuless:arm64-test .
```

GitHub builds AMD64 and ARM64 in parallel on native runners after the shared API/browser tests. Each image must pass its native smoke test and security scan. Release publication uses the exact scanned archives to create a common GHCR version tag with both platforms, then signs the image-index digest. Docker selects the matching architecture when pulling that tag. This configuration has not yet been executed on GitHub; no ARM64 release is claimed until it succeeds. GitLab publication remains AMD64.

A locally successful AMD64 scan does not certify ARM64: each platform must pass independently. The command above is a local validation build and does not publish an image.

To update the base, resolve a new **multi-platform index** digest, rebuild, run application tests and scan the final image. Do not substitute an AMD64-only child digest. The Alpine migration removed all HIGH/CRITICAL findings detected in the local AMD64 scan on 2026-10-14; advisory updates can change that result. The same blocking security policy remains enabled.

References: [official Python images](https://hub.docker.com/_/python), [Docker multi-platform builds](https://docs.docker.com/build/building/multi-platform/).

## Kubernetes deployment

See the [Kubernetes guide](kubernetes.md) for generic manifests, a deployment diagram, storage requirements, optional HTTPS and backup commands. Private deployment configuration stays in `local/`.

## Authentication and proxy behavior

Passwords use scrypt; only SHA-256 hashes of random bearer tokens are stored. The web session is stored in per-tab `sessionStorage`. There are no authentication cookies or open CORS policy. Registration and login share a limit of 30 attempts per network address per 15 minutes. Behind a proxy, this address is the proxy's address: configure per-client limits at the proxy. The server does not trust `X-Forwarded-*` headers.

See [synchronization](../development/synchronization.md) for SSE buffering and timeout requirements.

## External PostgreSQL

SQLite remains the default. To use an external PostgreSQL database, set `DATABASE_URL` through `.env` and follow the [PostgreSQL configuration and migration guide](postgresql.md). An existing SQLite installation must be migrated before starting with the new URL; setting it alone does not copy data. Preserve the existing SQLite volume through the cutover. PostgreSQL backups are managed separately.

## Backups and restoration

SQLite is intended for a single self-hosted instance. Do not scale independent database replicas or place the WAL database on a network filesystem. Use SQLite's backup API while the service is running:

```sh
docker compose exec stop-clop python -c "import sqlite3; source=sqlite3.connect('/data/stopclop.db'); target=sqlite3.connect('/data/backup.db'); source.backup(target); target.execute('PRAGMA journal_mode=DELETE'); target.close(); source.close()"
docker compose cp stop-clop:/data/backup.db ./stop-clop-backup.db
```

The backup includes all users' data and authentication hashes. To restore, stop the service, replace the database in the volume and preserve ownership for UID 10001. Remove old WAL/SHM files belonging to the replaced database before restarting. Never replace an open database. A persistent volume is not a backup.

## Upgrades

Back up first, then rebuild with `docker compose up -d --build`. Startup applies additive migrations and retains existing data. Update Android clients alongside server features. Historical currency migration keeps older costs in EUR; later upgrades preserve existing account preferences.

SuuLess retains the Compose service/project and volume identifiers `stop-clop` for upgrades from the previous name. Keep any existing custom Compose project name when updating; the SQLite filename remains `stopclop.db`.

SMTP can also be supplied through `SMTP_ENABLED`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` and `SMTP_PUBLIC_URL`. See [environment configuration and precedence](administration.md#configure-smtp-with-environment-variables).
