"""Real PostgreSQL integration tests, enabled only by TEST_POSTGRES_URL.

The supplied role needs CREATEDB. Each test creates/drops its own random database;
no existing database schema is cleared. SQLite tests remain independent.
"""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from server.app import create_app
from server.database import connect, configured_database, parameters, IntegrityError
from server.migrate import migrate, fingerprint
from server.sync import events
from server.push import dispatch
import test_admin_accounts
import test_coaching
import test_consumption_report
import test_session_expiry

URL = os.environ.get('TEST_POSTGRES_URL', '')


class DatabaseSelectionTest(unittest.TestCase):
    def test_selection_is_explicit(self):
        self.assertEqual(configured_database({'DATABASE': '/tmp/example.db'}), '/tmp/example.db')
        self.assertEqual(configured_database({'DATABASE': 'ignored', 'DATABASE_URL': 'postgresql://localhost/test'}), 'postgresql://localhost/test')
        with self.assertRaises(ValueError):
            configured_database({'DATABASE': 'ignored', 'DATABASE_URL': 'mysql://localhost/test'})

    def test_placeholder_conversion_preserves_literals(self):
        self.assertEqual(parameters("SELECT '?' AS literal, ? AS value, '100%' AS percent"),
                         "SELECT '?' AS literal, %s AS value, '100%%' AS percent")


class IsolatedPostgres:
    def setUp(self):
        import psycopg
        from psycopg import sql
        self.pg_admin = psycopg.connect(URL, autocommit=True)
        self.addCleanup(self.pg_admin.close)
        name = 'suuless_test_' + uuid.uuid4().hex
        self.pg_admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        self.addCleanup(lambda: self.pg_admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name))))
        # Public app config accepts URLs, not arbitrary libpq strings.
        from urllib.parse import urlsplit, urlunsplit
        parts = urlsplit(URL)
        self.pg_url = urlunsplit((parts.scheme, parts.netloc, '/'+name, parts.query, ''))
        if hasattr(self, 'fixture_module'):
            def application(config):
                return create_app({'ADMIN_USERNAME': '', 'ADMIN_PASSWORD': '', **config, 'DATABASE_URL': self.pg_url})
            replacement = patch.object(self.fixture_module, 'create_app', application)
            replacement.start(); self.addCleanup(replacement.stop)
        super().setUp()


@unittest.skipUnless(URL, 'TEST_POSTGRES_URL is not configured')
class PostgresCoachingTest(IsolatedPostgres, test_coaching.CoachingTest):
    fixture_module = test_coaching


@unittest.skipUnless(URL, 'TEST_POSTGRES_URL is not configured')
class PostgresReportTest(IsolatedPostgres, test_consumption_report.ConsumptionReportTest):
    fixture_module = test_consumption_report


@unittest.skipUnless(URL, 'TEST_POSTGRES_URL is not configured')
class PostgresSessionExpiryTest(IsolatedPostgres, test_session_expiry.SessionExpiryTest):
    fixture_module = test_session_expiry


@unittest.skipUnless(URL, 'TEST_POSTGRES_URL is not configured')
class PostgresIntegrationTest(IsolatedPostgres, unittest.TestCase):
    def app(self, **config):
        return create_app({'TESTING': True, 'DATABASE_URL': self.pg_url,
                           'ADMIN_USERNAME': '', 'ADMIN_PASSWORD': '', **config})

    def register(self, client, name='alice'):
        r = client.post('/api/auth/register', json={'username': name, 'password': 'synthetic-postgres-password'})
        self.assertEqual(r.status_code, 201)
        return {'Authorization': 'Bearer '+r.json['token']}

    def test_concurrent_idempotency_sse_and_account_deletion(self):
        app = self.app(); client = app.test_client(); headers = self.register(client)
        other = self.register(client, 'bob')
        def add(_):
            return app.test_client().post('/api/cigarettes', headers={**headers, 'Idempotency-Key': 'one-press'}, json={'quantity': 3})
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(add, range(4)))
        self.assertEqual(sorted(r.status_code for r in results), [200, 200, 200, 201])
        self.assertEqual(len({r.json['id'] for r in results}), 1)
        self.assertEqual(client.get('/api/stats', headers=headers).json['today']['quantity'], 3)
        self.assertEqual(client.get('/api/stats', headers=other).json['today']['quantity'], 0)
        with closing(connect(self.pg_url)) as conn:
            row = conn.execute('SELECT id,user_id,digest FROM tokens ORDER BY id').fetchone()
        stream = events(self.pg_url, row['id'], row['user_id'], row['digest'], interval=0, sleep=lambda _: None)
        self.assertIn('event: refresh', next(stream))
        self.assertEqual(client.delete('/api/me', headers=headers, json={'confirm': True, 'password': 'synthetic-postgres-password'}).status_code, 204)
        self.assertIn('event: revoked', next(stream)); stream.close()
        headers = self.register(client, 'alice-new')
        self.assertGreater(client.get('/api/me', headers=headers).json['id'], row['user_id'])

    def test_startup_admin_creation_and_money_precision(self):
        client = self.app().test_client(); h = self.register(client)
        self.assertEqual(client.put('/api/settings', headers=h, json={'currency': 'JPY', 'pack_price': '1000000', 'pack_size': 1}).status_code, 200)
        self.assertEqual(client.post('/api/cigarettes', headers=h, json={'quantity': 200}).status_code, 201)
        self.assertEqual(client.get('/api/stats', headers=h).json['today']['costs']['JPY'], 200000000)
        def boot(_):
            return self.app(ADMIN_USERNAME='operator', ADMIN_PASSWORD='synthetic-admin-password')
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(boot, range(3)))
        with closing(connect(self.pg_url)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0], 1)
        admin = client.post('/api/auth/login', json={'username': 'operator', 'password': 'synthetic-admin-password'})
        ah = {'Authorization': 'Bearer '+admin.json['token']}
        self.assertEqual(client.get('/api/admin/users', headers=ah).status_code, 200)
        self.assertEqual(client.get('/api/stats', headers=ah).status_code, 403)

    def test_read_connections_do_not_hold_transactions(self):
        self.app()
        with closing(connect(self.pg_url)) as conn:
            conn.execute('SELECT COUNT(*) FROM users').fetchone()
            self.assertEqual(conn.connection.info.transaction_status.name, 'IDLE')

    def test_migration_failure_rolls_back_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = str(Path(tmp)/'source.db')
            app = create_app({'TESTING': True, 'DATABASE': source, 'ADMIN_USERNAME': '', 'ADMIN_PASSWORD': ''})
            self.register(app.test_client())
            before = hashlib.sha256(Path(source).read_bytes()).digest()
            def mismatch(conn, table, names):
                count, digest = fingerprint(conn, table, names)
                return (count, b'forced-mismatch') if hasattr(conn, 'connection') else (count, digest)
            with patch('server.migrate.fingerprint', side_effect=mismatch), self.assertRaises(ValueError):
                migrate(source, self.pg_url)
            with closing(connect(self.pg_url)) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'").fetchone()[0], 0)
            self.assertEqual(hashlib.sha256(Path(source).read_bytes()).digest(), before)

    def test_migration_includes_committed_wal_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = str(Path(tmp)/'source.db')
            app = create_app({'TESTING': True, 'DATABASE': source,
                              'ADMIN_USERNAME': '', 'ADMIN_PASSWORD': ''})
            client = app.test_client()
            headers = self.register(client)
            # Keep a connection open so the committed WAL cannot be checkpointed
            # by closing the last connection before the migration snapshot.
            with closing(connect(source)) as held:
                held.execute('PRAGMA wal_autocheckpoint=0')
                held.execute('SELECT COUNT(*) FROM users').fetchone()
                response = client.post('/api/cigarettes', headers=headers, json={'quantity': 7})
                self.assertEqual(response.status_code, 201)
                wal = Path(source+'-wal')
                self.assertGreater(wal.stat().st_size, 0)
                before = hashlib.sha256(wal.read_bytes()).digest()
                counts = migrate(source, self.pg_url)
                self.assertEqual(counts['cigarettes'], 1)
                self.assertEqual(hashlib.sha256(wal.read_bytes()).digest(), before)
            with closing(connect(self.pg_url)) as target:
                self.assertEqual(target.execute('SELECT quantity FROM cigarettes').fetchone()[0], 7)

    def test_legacy_source_upgrades_only_the_snapshot(self):
        import sqlite3
        from server.app import SCHEMA
        with tempfile.TemporaryDirectory() as tmp:
            source = str(Path(tmp)/'legacy.db')
            with closing(sqlite3.connect(source)) as conn, conn:
                conn.executescript(SCHEMA)
                # Historical releases added language before the administrator fields.
                conn.execute("ALTER TABLE users ADD COLUMN language TEXT NOT NULL DEFAULT 'en'")
                conn.execute("INSERT INTO users(id,username,password_hash,pack_price_cents) VALUES(1,'legacy','synthetic-hash',1299)")
                conn.execute("INSERT INTO cigarettes(id,user_id,occurred_at,quantity,unit_cost_micros,source) VALUES(8,1,'2025-01-01T00:00:00+00:00',1,649500,'api')")
            before = hashlib.sha256(Path(source).read_bytes()).digest()
            migrate(source, self.pg_url)
            with closing(connect(self.pg_url)) as conn:
                self.assertEqual(conn.execute('SELECT currency,pack_price_micros FROM users').fetchone()['pack_price_micros'], 12990000)
                self.assertEqual(conn.execute('SELECT currency FROM cigarettes').fetchone()[0], 'EUR')
            self.assertEqual(hashlib.sha256(Path(source).read_bytes()).digest(), before)

    def test_rollback_and_foreign_keys(self):
        self.app()
        with closing(connect(self.pg_url)) as conn:
            with self.assertRaises(IntegrityError):
                with conn:
                    conn.execute("INSERT INTO mail_settings VALUES(1,'{}')")
                    conn.execute("INSERT INTO journeys VALUES(999,'{}')")
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM mail_settings').fetchone()[0], 0)

    def test_migration_roundtrip_dry_run_and_nonempty_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp)/'source.db')
            source = create_app({'TESTING': True, 'DATABASE': path, 'DATABASE_URL': '',
                                 'ADMIN_USERNAME': 'operator', 'ADMIN_PASSWORD': 'synthetic-admin-password'})
            c = source.test_client(); h = self.register(c)
            uid = c.get('/api/me', headers=h).json['id']
            c.post('/api/cigarettes', headers={**h, 'Idempotency-Key': 'kept-key'}, json={'quantity': 2})
            c.put('/api/settings', headers=h, json={'currency': 'JPY', 'pack_price': '600', 'language': 'ja'})
            c.post('/api/cigarettes', headers=h, json={'quantity': 3})
            key = c.post('/api/tokens', headers=h, json={'name': 'Migrated API key'}).json
            c.post('/api/cravings', headers={**h, 'Idempotency-Key': 'craving-kept'}, json={'strategy': 'water'})
            with closing(connect(path)) as conn, conn:
                conn.execute('UPDATE account_sequence SET last_id=500 WHERE id=1')
                conn.execute("INSERT INTO mail_settings VALUES(1,?)", ('{"enabled":false,"password":"synthetic-smtp"}',))
                conn.execute("INSERT INTO account_links(digest,purpose,email,user_id,language,expires_at) VALUES('digest','reset','test@example.com',?,'en','2099-01-01')", (uid,))
                conn.execute('INSERT INTO push_subscriptions VALUES(?,?)', (key['id'], 'https://push.example/up123456789012'))
                conn.execute('INSERT INTO push_outbox(token_id) VALUES(?)', (key['id'],))
            before = hashlib.sha256(Path(path).read_bytes()).digest()
            counts = migrate(path, self.pg_url, dry_run=True)
            self.assertEqual(counts['cigarettes'], 2)
            with closing(connect(self.pg_url)) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'").fetchone()[0], 0)
            self.assertEqual(counts, migrate(path, self.pg_url))
            self.assertEqual(hashlib.sha256(Path(path).read_bytes()).digest(), before)
            target = self.app().test_client()
            self.assertEqual(target.get('/api/stats', headers=h).json, c.get('/api/stats', headers=h).json)
            self.assertEqual(target.get('/api/export.csv', headers=h).data, c.get('/api/export.csv', headers=h).data)
            kh = {'Authorization': 'Bearer '+key['token']}
            replay = target.post('/api/cigarettes', headers={**kh, 'Idempotency-Key': 'kept-key'}, json={})
            self.assertEqual(replay.status_code, 200)
            fresh = target.post('/api/cigarettes', headers=kh, json={})
            self.assertEqual(fresh.status_code, 201); self.assertGreater(fresh.json['id'], 2)
            new = self.register(target, 'after-migration')
            self.assertGreater(target.get('/api/me', headers=new).json['id'], 500)
            with self.assertRaises(ValueError):
                migrate(path, self.pg_url)
            with closing(connect(self.pg_url)) as conn:
                sent = []
                dispatch(conn, 'https://push.example', 'http://relay', sender=lambda *args: sent.append(args))
                self.assertTrue(sent)


@unittest.skipUnless(URL, 'TEST_POSTGRES_URL is not configured')
class PostgresAccountsTest(IsolatedPostgres, unittest.TestCase):
    fixture_module = test_admin_accounts

    def setUp(self):
        super().setUp()
        test_admin_accounts.AdminAccountsTest.setUp(self)

    login = test_admin_accounts.AdminAccountsTest.login
    secret = test_admin_accounts.AdminAccountsTest.secret
    invite = test_admin_accounts.AdminAccountsTest.invite
    complete = test_admin_accounts.AdminAccountsTest.complete
    test_roles = test_admin_accounts.AdminAccountsTest.test_role_enforcement_and_language
    test_activation = test_admin_accounts.AdminAccountsTest.test_activation_no_session_until_email_verified
    test_reset = test_admin_accounts.AdminAccountsTest.test_reset_revokes_all_access_and_hides_existence
    test_mail_failure_rollback = test_admin_accounts.AdminAccountsTest.test_existing_account_email_and_failure_rollback
    test_smtp_redaction = test_admin_accounts.AdminAccountsTest.test_smtp_password_redaction_and_validation
    test_suspension = test_admin_accounts.AdminAccountsTest.test_disable_revokes_sessions_and_enable_preserves_data

    def test_concurrent_invitation_is_consumed_once(self):
        self.app.config['ALLOW_REGISTRATION'] = False
        secret = self.invite()
        def accept(i):
            return self.app.test_client().post('/api/auth/complete', json={
                'token': secret, 'username': 'invited'+str(i), 'password': 'synthetic-invite-password'}).status_code
        with ThreadPoolExecutor(max_workers=3) as pool:
            self.assertEqual(sorted(pool.map(accept, range(3))), [200, 400, 400])
