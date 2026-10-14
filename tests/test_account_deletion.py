from contextlib import closing
from datetime import datetime, timedelta, timezone
import sqlite3
import tempfile
import unittest
from server.app import create_app
from server.sync import events


class AccountDeletionTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.config={'TESTING':True,'DATABASE':self.tmp.name+'/db'}
        self.app=create_app(self.config);self.client=self.app.test_client()
        self.first=self.register('alice');self.second=self.register('bob')
        self.headers={'Authorization':'Bearer '+self.first['token']}
        self.other={'Authorization':'Bearer '+self.second['token']}
        self.uid=self.client.get('/api/me',headers=self.headers).json['id']

    def register(self,name):
        response=self.client.post('/api/auth/register',json={'username':name,'password':'account-test-password'})
        self.assertEqual(response.status_code,201,response.text)
        return response.json

    def delete(self,**overrides):
        return self.client.delete('/api/me',headers=self.headers,json={'password':'account-test-password','confirm':True,**overrides})

    def populate(self):
        day=(datetime.now(timezone.utc)-timedelta(days=2)).date().isoformat()
        for headers in [self.headers,self.other]:
            self.client.post('/api/cigarettes',headers=headers,json={'quantity':4})
            self.client.put('/api/coaching/plan',headers=headers,json={'version':0,'reason':'Private reason'})
            self.client.put('/api/check-ins/'+day,headers=headers,json={'quantity':0})
            self.client.post('/api/cravings',headers={**headers,'Idempotency-Key':'urge'},json={'strategy':'water'})
            key=self.client.post('/api/tokens',headers=headers,json={'name':'Integration'}).json
            with closing(sqlite3.connect(self.config['DATABASE'])) as db,db:
                db.execute('INSERT INTO push_subscriptions VALUES(?,?)',(key['id'],'https://example.invalid/up'+str(key['id'])*12))
                db.execute('INSERT INTO push_outbox(token_id) VALUES(?)',(key['id'],))

    def test_delete_all_related_data_and_preserve_other_account(self):
        self.populate()
        extra=self.client.post('/api/auth/login',json={'username':'alice','password':'account-test-password','client':'android'}).json
        with closing(sqlite3.connect(self.config['DATABASE'])) as db:
            digest=db.execute('SELECT digest FROM tokens WHERE id=?',(self.first['id'],)).fetchone()[0]
        stream=events(self.config['DATABASE'],self.first['id'],self.uid,digest,interval=0,sleep=lambda _:None)
        self.assertIn('event: refresh',next(stream))
        self.assertEqual(self.delete().status_code,204)
        self.assertIn('event: revoked',next(stream));stream.close()
        for token in [self.first,extra]:
            self.assertEqual(self.client.get('/api/me',headers={'Authorization':'Bearer '+token['token']}).status_code,401)
        with closing(sqlite3.connect(self.config['DATABASE'])) as db:
            self.assertIsNone(db.execute('SELECT id FROM users WHERE id=?',(self.uid,)).fetchone())
            for table in ['tokens','cigarettes','journeys','checkins','cravings','sync_revisions']:
                self.assertEqual(db.execute(f'SELECT COUNT(*) FROM {table} WHERE user_id=?',(self.uid,)).fetchone()[0],0,table)
                self.assertGreater(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0],0,table)
            for table in ['push_subscriptions','push_outbox']:
                self.assertEqual(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0],1,table)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertEqual(self.client.get('/api/me',headers=self.other).status_code,200)
        self.assertEqual(self.client.post('/api/auth/login',json={'username':'alice','password':'account-test-password'}).status_code,401)

    def test_password_confirmation_and_authentication_required(self):
        for payload in [{'password':'wrong'},{'confirm':False},{'password':None},{'confirm':1}]:
            self.assertEqual(self.delete(**payload).status_code,400)
            self.assertEqual(self.client.get('/api/me',headers=self.headers).status_code,200)
        self.assertEqual(self.client.delete('/api/me',json={'confirm':True,'password':'account-test-password'}).status_code,401)

    def test_failure_rolls_back_all_deletions(self):
        self.populate()
        with closing(sqlite3.connect(self.config['DATABASE'])) as db,db:
            db.execute("CREATE TRIGGER fail_deletion BEFORE DELETE ON users BEGIN SELECT RAISE(ABORT,'test rollback'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.delete()
        self.assertEqual(self.client.get('/api/me',headers=self.headers).status_code,200)
        with closing(sqlite3.connect(self.config['DATABASE'])) as db:
            for table in ['tokens','cigarettes','journeys','checkins','cravings','sync_revisions']:
                self.assertGreater(db.execute(f'SELECT COUNT(*) FROM {table} WHERE user_id=?',(self.uid,)).fetchone()[0],0,table)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM push_outbox').fetchone()[0],2)

    def test_deleted_ids_are_not_reused_after_restart(self):
        self.assertEqual(self.delete().status_code,204)
        self.client.delete('/api/me',headers=self.other,json={'password':'account-test-password','confirm':True})
        self.app=create_app(self.config);self.client=self.app.test_client()
        replacement=self.register('alice')
        uid=self.client.get('/api/me',headers={'Authorization':'Bearer '+replacement['token']}).json['id']
        self.assertGreater(uid,self.uid+1)
        with closing(sqlite3.connect(self.config['DATABASE'])) as db,db:
            db.execute('PRAGMA foreign_keys=ON')
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO journeys VALUES(?, '{}')",(self.uid,))
