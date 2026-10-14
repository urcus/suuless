from contextlib import closing
import hashlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from server.app import create_app


class SessionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = {'TESTING': True, 'DATABASE': self.tmp.name+'/db'}
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.now = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
        clock = patch('server.app.now', return_value=self.now)
        clock.start(); self.addCleanup(clock.stop)
        self.current = self.issue('alice')
        self.headers = self.headers_for(self.current)

    def headers_for(self, token):
        return {'Authorization':'Bearer '+token['token']}

    def issue(self, name, login=False, client='web'):
        return self.client.post('/api/auth/'+('login' if login else 'register'), json={
            'username':name,'password':'sessions-test-password','client':client}).json

    def test_bulk_revocation_is_scoped_and_preserves_keys_and_current(self):
        web = self.issue('alice', login=True)
        android = self.issue('alice', login=True, client='android')
        other = self.issue('bob')
        key = self.client.post('/api/tokens', headers=self.headers, json={'name':'Session'}).json
        rows = self.client.get('/api/tokens', headers=self.headers).json
        self.assertEqual({r['kind'] for r in rows}, {'session','api'})
        self.assertEqual(next(r for r in rows if r['id']==android['id'])['client'], 'android')
        self.assertEqual(self.client.delete('/api/sessions/others', headers=self.headers).status_code,204)
        for token in [web, android]:
            self.assertEqual(self.client.get('/api/me', headers=self.headers_for(token)).status_code,401)
        for token in [self.current, other, key]:
            self.assertEqual(self.client.get('/api/me', headers=self.headers_for(token)).status_code,200)
        self.assertEqual(self.client.delete('/api/sessions/others', headers=self.headers).status_code,204)
        self.assertEqual(self.client.delete('/api/sessions/others').status_code,401)

    def test_only_valid_tokens_listed_and_legacy_not_bulk_revoked(self):
        old = self.issue('alice', login=True)
        expired = self.issue('alice', login=True)
        with closing(sqlite3.connect(self.config['DATABASE'])) as db, db:
            db.execute("UPDATE tokens SET kind='legacy',client=NULL,created_at=NULL WHERE id=?",(old['id'],))
            db.execute('UPDATE tokens SET expires_at=? WHERE id=?',(self.now.isoformat(),expired['id']))
        rows=self.client.get('/api/tokens', headers=self.headers).json
        self.assertNotIn(expired['id'],[r['id'] for r in rows])
        self.client.delete('/api/sessions/others',headers=self.headers)
        self.assertEqual(self.client.get('/api/me',headers=self.headers_for(old)).status_code,200)

    def test_legacy_schema_migration_is_additive_and_repeatable(self):
        path=self.tmp.name+'/legacy'
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE tokens(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,digest TEXT UNIQUE NOT NULL,name TEXT NOT NULL,expires_at TEXT NOT NULL)')
            for index,name in enumerate(['Session','Stream Deck'],1):
                db.execute('INSERT INTO tokens VALUES(?,?,?,?,?)',(index,1,hashlib.sha256(str(index).encode()).hexdigest(),name,(self.now+timedelta(days=10)).isoformat()))
        for _ in range(2):create_app({'TESTING':True,'DATABASE':path})
        with closing(sqlite3.connect(path)) as db, db:
            self.assertEqual(db.execute('SELECT name,kind,client,created_at FROM tokens ORDER BY id').fetchall(),
                             [('Session','legacy',None,None),('Stream Deck','api',None,None)])
