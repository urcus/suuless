"""Offline SQLite -> empty PostgreSQL migration; source is never modified."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from .app import initialize_database
from .database import connect, columns, is_postgres, DatabaseError

# Parent-before-child order, including private configuration and legacy outbox.
TABLES = ('users', 'account_sequence', 'installation_state', 'tokens', 'cigarettes',
          'auth_attempts', 'sync_revisions', 'journeys', 'checkins', 'cravings',
          'mail_settings', 'account_links', 'push_subscriptions', 'push_outbox')
NO_ADMIN = {'ADMIN_USERNAME': '', 'ADMIN_PASSWORD': ''}


class MigrationError(ValueError):
    """Safe operator-facing error, never containing row data or credentials."""


def fingerprint(conn, table, names):
    projection = ','.join('"'+name+'"' for name in names)
    # Both identifiers come from our fixed tables and validated schema columns.
    rows = conn.execute(f'SELECT {projection} FROM "{table}"')  # nosec B608
    hashes = []
    for row in rows:
        encoded = json.dumps([row[name] for name in names], ensure_ascii=True,
                             separators=(',', ':'), allow_nan=False).encode()
        hashes.append(hashlib.sha256(encoded).digest())
    # Order-independent and duplicate-sensitive, unlike a count-only comparison.
    return len(hashes), hashlib.sha256(b''.join(sorted(hashes))).digest()


def migrate(source, destination, dry_run=False):
    if not is_postgres(destination):
        raise MigrationError('DATABASE_URL must specify PostgreSQL')
    source = Path(source).resolve(strict=True)
    if not source.is_file():
        raise MigrationError('Source must be an existing SQLite database file')
    with tempfile.TemporaryDirectory(prefix='suuless-migration-') as directory:
        snapshot = str(Path(directory) / 'snapshot.sqlite')
        # backup() incorporates committed WAL data; never migrate a raw live-file copy.
        try:
            with closing(sqlite3.connect(source.as_uri()+'?mode=ro', uri=True)) as original:
                with closing(sqlite3.connect(snapshot)) as backup:
                    original.backup(backup)
        except sqlite3.OperationalError:
            raise MigrationError(
                'Cannot read the SQLite source; check permissions and use a consistent '
                'backup with journal_mode=DELETE when mounting a single read-only file'
            ) from None
        with closing(connect(snapshot)) as src:
            if src.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise MigrationError('SQLite integrity check failed')
            existing = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if not {'users', 'tokens', 'cigarettes'} <= existing or existing - set(TABLES):
                raise MigrationError('Unsupported source schema; expected a SuuLess SQLite database')
            # Apply supported additive migrations only to the private snapshot.
            initialize_database(src, NO_ADMIN)
            if src.execute('PRAGMA foreign_key_check').fetchone():
                raise MigrationError('SQLite foreign-key check failed')
            with closing(connect(destination)) as dst, dst:
                occupied = dst.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='public' LIMIT 1").fetchone()
                if occupied:
                    raise MigrationError('Destination public schema must be empty; no merge or overwrite is allowed')
                initialize_database(dst, NO_ADMIN, commit=False)
                # Remove only bootstrap rows just created in this transaction.
                dst.execute('DELETE FROM account_sequence')
                counts = {}
                from psycopg import sql
                for table in TABLES:
                    names = columns(src, table)
                    if set(names) != set(columns(dst, table)):
                        raise MigrationError('Source and destination schema differ')
                    identifiers = sql.SQL(',').join(map(sql.Identifier, names))
                    statement = sql.SQL('COPY {} ({}) FROM STDIN').format(sql.Identifier(table), identifiers)
                    with dst.connection.cursor().copy(statement) as copy:
                        for row in src.execute(f'SELECT * FROM "{table}"'):  # nosec B608
                            copy.write_row(tuple(row[name] for name in names))
                    before = fingerprint(src, table, names)
                    if before != fingerprint(dst, table, names):
                        raise MigrationError('Migration content verification failed')
                    counts[table] = before[0]
                    if 'id' in names:
                        maximum = dst.execute(f'SELECT MAX(id) FROM "{table}"').fetchone()[0]  # nosec B608
                        dst.execute("SELECT setval(pg_get_serial_sequence(?, 'id'), ?, ?)",
                                    (table, max(1, maximum or 1), maximum is not None and maximum > 0))
                if dry_run:
                    dst.rollback()
                return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sqlite', required=True, help='SQLite backup file (read only)')
    parser.add_argument('--dry-run', action='store_true', help='Copy and verify, then roll back the target')
    parser.add_argument('--source-stopped', action='store_true', help='Confirm all writers are stopped for the final copy')
    args = parser.parse_args()
    if not args.dry_run and not args.source_stopped:
        parser.error('Stop all source writers, then pass --source-stopped for the final migration')
    try:
        counts = migrate(args.sqlite, os.environ.get('DATABASE_URL', ''), args.dry_run)
    except MigrationError as error:
        parser.exit(1, f'Migration refused: {error}. No target changes were committed.\n')
    except (ValueError, OSError, DatabaseError):
        parser.exit(1, 'Migration failed: check source integrity/schema, an empty target, permissions and connection settings. No target changes were committed.\n')
    except Exception:
        # Driver COPY failures may contain private row data; never print them.
        parser.exit(1, 'Migration failed; no target changes were committed. Check database compatibility and constraints.\n')
    print('Dry run verified; target rolled back.' if args.dry_run else 'Migration committed and verified.')
    for table, count in counts.items():
        print(f'{table}: {count} rows')
    print('Source file unchanged. Keep the SQLite backup until the PostgreSQL cutover is validated.')


if __name__ == '__main__':
    main()
