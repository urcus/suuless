# External PostgreSQL and migration from SQLite

[Documentation](../README.md) · [Docker](docker.md) · [Kubernetes](kubernetes.md)

SuuLess uses SQLite by default. Set `DATABASE_URL` to use an external PostgreSQL server instead. The same API, web interface, Android app and iPhone shortcuts work with either database; no client-side configuration change is needed if the application URL stays the same.

This guide describes the current source implementation. Use an image built from a version containing this feature; older releases such as v1.0.1 do not support it. PostgreSQL 17 is covered by the integration tests. The PostgreSQL service itself is operated and backed up separately from SuuLess.

## Configuration

| Setting | Behavior |
|---|---|
| `DATABASE_URL` empty/unset | SQLite, using `DATABASE`; the container defaults to `/data/stopclop.db`. |
| `DATABASE_URL=postgresql://…` | PostgreSQL takes precedence over the SQLite path. `postgres://…` is also accepted. |
| Invalid or unreachable PostgreSQL configuration | Startup fails; there is no automatic fallback to SQLite. |

Example connection URL, with placeholders only:

```dotenv
DATABASE_URL=postgresql://suuless:URL_ENCODED_PASSWORD@db.example.com:5432/suuless?sslmode=verify-full
```

Use a dedicated database and role that owns its `public` schema and can create/alter tables, indexes and sequences. The database must already exist. The application applies additive schema migrations at startup; the runtime role does not need superuser or `CREATEDB`. Only the `public` schema is supported.

URL-encode reserved characters in the username/password. Supply the real URL through an ignored `.env` file or a deployment Secret. Do not commit it, paste it into logs or pass it as a CLI argument. For a remote database, use certificate-verified TLS (`sslmode=verify-full`), a matching hostname and a trusted CA; `sslrootcert=/path/to/ca.pem` can point to a mounted CA file. See [PostgreSQL connection parameters](https://www.postgresql.org/docs/17/libpq-connect.html#LIBPQ-PARAMKEYWORDS).

With Docker Compose, add `DATABASE_URL` to `.env`; `compose.yaml` passes it to the application. For a **new installation**, run `docker compose up -d --build`. For an **existing SQLite installation**, complete the migration below before starting the app with this URL. Changing the variable alone does not transfer data.

The pinned `psycopg[binary]` dependency supplies the driver and its native libraries, including `libpq`. The image uses binary wheels, available for its Python 3.13 Alpine AMD64/ARM64 targets, without a compiler or a separately installed PostgreSQL client. A non-container installation uses the same `requirements.txt`. SQLite-only execution does not load the PostgreSQL driver.

## Storage and operational behavior

Passwords, roles, preferences, entries, historical currencies/prices, personal keys, sessions, invitations/recovery links, SMTP settings, journeys, check-ins, cravings and synchronization revisions live in the selected database. PostgreSQL timestamps remain the same UTC ISO strings as SQLite, and monetary values remain integer millionths; migration does not reinterpret time zones or convert currencies.

PostgreSQL writes are serialized with a transaction advisory lock, preserving the existing SQLite transaction behavior for account creation, single-use links, idempotent requests and coaching conflicts. This initial implementation is not a high-throughput redesign. Reads, including SSE checks, do not leave idle transactions open. Connections are opened per request/stream and closed afterward; there is no connection pool. Budget database connections for the configured workers/threads, SSE clients and maintenance tools.

Keep the current single application replica during the initial migration. PostgreSQL removes SQLite's shared-file constraint, but does not by itself establish an HA deployment. Do not delete the SQLite volume/PVC during the transition.

## Migration workflow

![Offline migration from SQLite backup to an empty PostgreSQL target, with verification before commit and cutover](../assets/diagrams/postgresql-migration.svg)

[Open the migration diagram](../assets/diagrams/postgresql-migration.html).

The supplied tool, `python -m server.migrate`, reads SQLite through its backup API into a private temporary snapshot. It applies supported additive migrations to that snapshot, checks integrity and foreign keys, then copies all application tables into PostgreSQL in one transaction. It compares row counts and order-independent SHA-256 fingerprints of every row, and resets generated ID sequences before committing. The account ID high-water mark is preserved, including IDs of deleted accounts.

The original source file is never modified. The target `public` schema must contain **no tables or views**, even an empty SuuLess installation: the tool refuses to merge into or overwrite an existing destination. A failed copy or verification rolls back the newly created schema/data. A dry run performs the same copy and verification, then rolls it back. Sequence operations only touch newly created sequences, which are removed with the rolled-back schema.

The tool uses temporary disk space for a full SQLite snapshot and memory for row fingerprints. Run it from a trusted environment with enough disk/RAM. Backups and temporary snapshots include authentication digests and stored SMTP credentials; protect them like the live database. Unsupported extra tables or source columns are rejected rather than silently omitted.

### 1. Prepare and rehearse

1. Build the application version containing PostgreSQL support: `docker compose build stop-clop`. This does not replace the running container.
2. Provision the empty PostgreSQL database and its role. Confirm connectivity and TLS from the application network.
3. Create a consistent SQLite backup using the [Docker backup procedure](docker.md#backups-and-restoration) or [Kubernetes procedure](kubernetes.md#back-up-sqlite), and store a copy outside the application volume/PVC.
4. Set the target `DATABASE_URL` in `.env`, but **do not recreate the application container yet**. The existing container keeps its SQLite configuration until recreated.
5. Run a rehearsal against the backup. On a Linux host, `--user` below lets the one-off container read a backup owned by your current user without making it world-readable:

```sh
docker compose run --rm --no-deps \
  --user "$(id -u):$(id -g)" \
  --volume "$PWD/stop-clop-backup.db:/migration/source.db:ro" \
  stop-clop python -m server.migrate \
  --sqlite /migration/source.db --dry-run
```

Success prints table counts and `Dry run verified; target rolled back.` No credentials or row contents are printed. On other hosts, arrange read access to the mounted backup for the container user. If using the Python virtual environment instead, set `DATABASE_URL` securely in that process's environment and run `.venv/bin/python -m server.migrate --sqlite /path/to/backup.db --dry-run`.

Use the backup commands above, which set `journal_mode=DELETE` on the backup only, making it readable as a standalone read-only mount. Do not mount a raw WAL-mode database file alone or omit its committed WAL data. The live database remains in WAL mode.

A rehearsal backup can become stale while SQLite remains in use. Do not treat it as the final migration copy.

### 2. Stop writes and make the final backup

Schedule a maintenance window. Stop **every** application instance and any legacy push worker using the source SQLite database, and stop any other process that writes to it. For the standard Compose installation:

```sh
docker compose stop stop-clop
```

With the application stopped, create a fresh, consistently named final backup in the preserved volume using a one-off container. This command uses SQLite directly; it does not start Flask or initialize PostgreSQL:

```sh
docker compose run --rm --no-deps stop-clop python -c "import sqlite3; source=sqlite3.connect('file:/data/stopclop.db?mode=ro', uri=True); target=sqlite3.connect('/data/stop-clop-final.db'); source.backup(target); target.execute('PRAGMA journal_mode=DELETE'); target.close(); source.close()"
docker compose cp stop-clop:/data/stop-clop-final.db ./stop-clop-final.db
```

Retain this final backup securely outside the source volume. The stopped container must still exist for `compose cp`; do not run `down` or remove its volume. For Kubernetes, make the final backup through an authorized maintenance pod mounting the existing PVC after scaling the application to zero; do not delete/recreate the PVC or use a stale pre-maintenance backup.

### 3. Copy and verify

Run the final migration using that fresh backup and the same target URL:

```sh
docker compose run --rm --no-deps \
  --user "$(id -u):$(id -g)" \
  --volume "$PWD/stop-clop-final.db:/migration/source.db:ro" \
  stop-clop python -m server.migrate \
  --sqlite /migration/source.db --source-stopped
```

`--source-stopped` is your confirmation that all writers were stopped; the tool cannot detect remote writers. Without it, a non-dry-run migration is refused. Wait for **`Migration committed and verified.`** and review the table counts before restarting the application. A second run against this populated target is refused.

### 4. Switch the application and validate

Recreate the application with `DATABASE_URL` set:

```sh
docker compose up -d --no-deps stop-clop
docker compose exec stop-clop python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/healthz').status)"
```

Check existing-user and administrator login, history totals and mixed-currency costs, settings, exports, a new entry and its removal, API-key access and Android/widget synchronization. Existing tokens remain usable until their original expiry/revocation; no passwords are reset. Stored SMTP configuration and account links are copied, so avoid inadvertently sending real test mail from a rehearsal deployment. Environment-controlled SMTP remains an application deployment setting, not part of the copied tables.

The SQLite file remains in its volume but is no longer the active database. Establish PostgreSQL backups before ending the maintenance window.

### Rollback boundaries

Before any new PostgreSQL writes, stop the application, clear `DATABASE_URL`, and recreate it against the preserved SQLite database. If PostgreSQL has accepted new entries, configuration changes or logins, switching back to SQLite would lose those changes. Stop writes and reconcile/export the differences first. The migration tool does not implement reverse migration or continuous replication. Keep both databases and the final backup until the transition has been accepted.

## Kubernetes configuration

Keep the generic manifests' existing storage during migration. Add the connection URL through a Secret in the application's namespace; this fragment belongs under the application's container `env` list:

```yaml
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: suuless-database
      key: url
```

Create the Secret using your secret-management process, with the full URL in its `url` key. Mount a CA certificate separately if required by `sslrootcert`. Allow network traffic from the pod to PostgreSQL, keep credentials out of public manifests and use the actual namespace/resource names of your installation. The public manifests continue to default to SQLite and do not provision a PostgreSQL cluster. Run the migration as an explicit one-off maintenance action before restarting the deployment with the Secret configured.

## PostgreSQL backups

SQLite backup commands no longer back up the active database after switching. Use your database provider's backups/PITR or PostgreSQL tools such as `pg_dump` and `pg_restore`, with client tools compatible with the server version. Supply credentials through a protected password/service file or your secret-management tooling, and protect dump files. Test restores into a separate database before relying on them. See [PostgreSQL backup documentation](https://www.postgresql.org/docs/17/backup.html).
