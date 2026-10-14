from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from server.app import create_app


class InitialAccountTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config = dict(TESTING=True, DATABASE=tmp.name+'/db', ALLOW_REGISTRATION=False,
                           ADMIN_USERNAME='Owner', ADMIN_PASSWORD='initial-long-password')

    def login(self, app, password='initial-long-password', username='owner'):
        return app.test_client().post('/api/auth/login', json=dict(username=username, password=password))

    def test_environment_and_closed_registration(self):
        config = {k: v for k, v in self.config.items() if not k.startswith('ADMIN_')}
        with patch.dict('os.environ', ADMIN_USERNAME='Owner', ADMIN_PASSWORD='initial-long-password'):
            app = create_app(config)
        self.assertEqual(self.login(app).status_code, 200)
        self.assertEqual(app.test_client().post('/api/auth/register', json={}).status_code, 403)
        with closing(sqlite3.connect(self.config['DATABASE'])) as db:
            row = db.execute('SELECT username,password_hash,language FROM users').fetchone()
            self.assertEqual(row[0], 'owner')
            self.assertNotEqual(row[1], self.config['ADMIN_PASSWORD'])
            self.assertEqual(row[2], 'en')

    def test_restarts_do_not_change_credentials(self):
        create_app(self.config)
        app = create_app(dict(self.config, ADMIN_USERNAME='another', ADMIN_PASSWORD='changed-long-password'))
        self.assertEqual(self.login(app).status_code, 200)
        self.assertEqual(self.login(app, 'changed-long-password', 'another').status_code, 401)

    def test_initial_administrator_cannot_delete_itself(self):
        app = create_app(self.config)
        token = self.login(app).json['token']
        response = app.test_client().delete('/api/me', headers={'Authorization':'Bearer '+token},
                                           json={'password':'initial-long-password', 'confirm':True})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.login(create_app(self.config)).status_code, 200)

    def test_deleted_user_does_not_prevent_dedicated_admin_creation(self):
        app = create_app(dict(self.config, ADMIN_USERNAME='', ADMIN_PASSWORD='', ALLOW_REGISTRATION=True))
        client = app.test_client()
        result = client.post('/api/auth/register', json={'username':'existing','password':'existing-long-password'})
        self.assertEqual(result.status_code, 201)
        client.delete('/api/me', headers={'Authorization':'Bearer '+result.json['token']},
                      json={'password':'existing-long-password','confirm':True})
        self.assertEqual(self.login(create_app(self.config)).status_code, 200)

    def test_existing_users_and_legacy_initialization_marker_are_preserved(self):
        app = create_app(dict(self.config, ADMIN_USERNAME='', ADMIN_PASSWORD='', ALLOW_REGISTRATION=True))
        client = app.test_client()
        registered = client.post('/api/auth/register', json={'username':'existing','password':'existing-long-password'}).json
        headers = {'Authorization':'Bearer '+registered['token']}
        client.post('/api/cigarettes', headers=headers, json={'quantity':3})
        with closing(sqlite3.connect(self.config['DATABASE'])) as db, db:
            db.execute('INSERT INTO installation_state(id,initial_account_handled) VALUES(1,1)')
        with ThreadPoolExecutor(max_workers=3) as pool:
            apps = list(pool.map(lambda _: create_app(self.config), range(3)))
        client = apps[0].test_client()
        self.assertEqual(self.login(apps[0]).status_code,200)
        self.assertEqual(client.get('/api/me',headers=headers).json['role'],'user')
        self.assertEqual(client.get('/api/stats',headers=headers).json['today']['quantity'],3)
        with closing(sqlite3.connect(self.config['DATABASE'])) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0],1)

    def test_username_collision_does_not_promote_or_reset_user(self):
        app = create_app(dict(self.config, ADMIN_USERNAME='', ADMIN_PASSWORD='', ALLOW_REGISTRATION=True))
        app.test_client().post('/api/auth/register',json={'username':'owner','password':'user-original-password'})
        with self.assertRaisesRegex(ValueError,'dedicated administrator'):
            create_app(self.config)
        self.assertEqual(self.login(app, 'user-original-password').status_code,200)
        with closing(sqlite3.connect(self.config['DATABASE'])) as db:
            self.assertEqual(db.execute('SELECT role FROM users').fetchone()[0],'user')
        self.assertEqual(self.login(create_app(dict(self.config,ADMIN_USERNAME='operator')),username='operator').status_code,200)

    def test_initialized_admin_is_not_recreated_after_operator_deletion(self):
        create_app(self.config)
        with closing(sqlite3.connect(self.config['DATABASE'])) as db, db:
            db.execute('DELETE FROM users')
        self.assertEqual(self.login(create_app(self.config)).status_code,401)

    def test_invalid_configuration_is_atomic_and_does_not_expose_password(self):
        for overrides in [dict(ADMIN_USERNAME=''), dict(ADMIN_PASSWORD=''),
                          dict(ADMIN_USERNAME='bad username'), dict(ADMIN_PASSWORD='short'),
                          dict(ADMIN_PASSWORD='x'*257)]:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError) as error:
                    create_app(dict(self.config, **overrides))
                self.assertNotIn('initial-long-password', str(error.exception))
                with closing(sqlite3.connect(self.config['DATABASE'])) as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM users').fetchone()[0], 0)
        self.assertEqual(self.login(create_app(self.config)).status_code, 200)

    def test_parallel_workers_create_exactly_one_account(self):
        # Set up schema first, then race workers on first account provisioning.
        create_app(dict(self.config, ADMIN_USERNAME='', ADMIN_PASSWORD=''))
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda _: create_app(self.config), range(3)))
        with closing(sqlite3.connect(self.config['DATABASE'])) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM users').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT last_id FROM account_sequence').fetchone()[0], 1)
