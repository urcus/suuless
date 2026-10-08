from contextlib import closing
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from server.app import create_app
from server.push import dispatch, topic_for, send_refresh


class PushTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=self.tmp.name+'/test.db'
        self.app=create_app({'TESTING':True,'DATABASE':self.path,'PUSH_PUBLIC_URL':'https://push.example', 'PUSH_INTERNAL_URL':'http://ntfy:8080'})
        self.client=self.app.test_client()
        self.alice=self.register('alice');self.bob=self.register('bob')
        self.conn=sqlite3.connect(self.path);self.conn.execute('PRAGMA foreign_keys=ON');self.addCleanup(self.conn.close)

    def register(self,name):
        r=self.client.post('/api/auth/register',json={'username':name,'password':'long-test-password'})
        return {'Authorization':'Bearer '+r.json['token']}

    def subscribe(self,headers,topic='upabcdefghijklmnop'):
        return self.client.put('/api/push',headers=headers,json={'endpoint':'https://push.example/'+topic+'?up=1'})

    def flush(self,sender):
        return dispatch(self.conn,'https://push.example','http://ntfy:8080',sender=sender)

    def test_private_and_fixed_origin_endpoints(self):
        self.assertEqual(self.client.get('/api/push').status_code,401)
        for endpoint in ['http://push.example/upabcdefghijklmnop','https://evil.example/upabcdefghijklmnop',
                         'https://push.example@127.0.0.1/upabcdefghijklmnop','https://push.example/admin',
                         'https://push.example/upabcdefghijklmnop/../health','https://push.example/upabcdefghijklmnop?x=1',
                         'https://push.example/upabcdefghijklmnop#fragment',None]:
            self.assertEqual(self.client.put('/api/push',headers=self.alice,json={'endpoint':endpoint}).status_code,400)
        self.assertEqual(topic_for('https://push.example/upabcdefghijklmnop?up=1','https://push.example'),'upabcdefghijklmnop')

    def test_account_isolation_coalescing_and_idempotent_add(self):
        self.assertEqual(self.subscribe(self.alice).status_code,200)
        self.subscribe(self.bob,'upbobabcdefghijklmnop')
        self.flush(lambda *_:None)
        headers=dict(self.alice,**{'Idempotency-Key':'external-click'})
        self.assertEqual(self.client.post('/api/cigarettes',headers=headers,json={'source':'streamdeck'}).status_code,201)
        self.assertEqual(self.client.post('/api/cigarettes',headers=headers,json={'source':'streamdeck'}).status_code,200)
        self.client.post('/api/cigarettes',headers=self.alice)
        sent=[];self.flush(lambda base,topic:sent.append((base,topic)))
        self.assertEqual(sent,[('http://ntfy:8080','upabcdefghijklmnop')])
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM push_outbox').fetchone()[0],0)

    def test_failures_retry_and_do_not_lose_new_changes(self):
        self.subscribe(self.alice)
        def offline(*_):raise OSError('offline')
        self.flush(offline)
        row=self.conn.execute('SELECT attempts,next_attempt FROM push_outbox').fetchone()
        self.assertEqual(row[0],1);self.assertGreater(row[1],0)
        self.assertEqual(self.flush(lambda *_:self.fail('Retry must wait')),0)
        with self.conn:self.conn.execute('UPDATE push_outbox SET next_attempt=0')
        def concurrent(*_):self.client.post('/api/cigarettes',headers=self.alice)
        self.flush(concurrent)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM push_outbox').fetchone()[0],1)
        self.flush(lambda *_:None)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM push_outbox').fetchone()[0],0)

    def test_settings_delete_disable_and_logout(self):
        self.subscribe(self.alice);self.flush(lambda *_:None)
        self.client.put('/api/settings',headers=self.alice,json={'language':'fr'})
        self.assertEqual(self.flush(lambda *_:None),1)
        entry=self.client.post('/api/cigarettes',headers=self.alice).json
        self.flush(lambda *_:None)
        self.client.delete('/api/cigarettes/'+str(entry['id']),headers=self.alice)
        self.assertEqual(self.flush(lambda *_:None),1)
        self.client.delete('/api/push',headers=self.bob)
        self.assertTrue(self.client.get('/api/push',headers=self.alice).json['registered'])
        self.client.delete('/api/push',headers=self.alice)
        self.assertFalse(self.client.get('/api/push',headers=self.alice).json['registered'])
        self.subscribe(self.alice)
        self.client.post('/api/auth/logout',headers=self.alice)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM push_outbox').fetchone()[0],0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM push_subscriptions').fetchone()[0],0)

    def test_queue_survives_restart_and_expired_sessions_are_removed(self):
        self.subscribe(self.alice)
        with closing(sqlite3.connect(self.path)) as reopened:
            self.assertEqual(reopened.execute('SELECT COUNT(*) FROM push_outbox').fetchone()[0],1)
        with self.conn:self.conn.execute('UPDATE tokens SET expires_at=?',((datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),))
        self.assertEqual(self.flush(lambda *_:self.fail('Expired session')),0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM push_subscriptions').fetchone()[0],0)

    def test_payload_contains_only_refresh_and_uses_internal_origin(self):
        with patch('server.push.build_opener') as build:
            send_refresh('http://ntfy:8080','upabcdefghijklmnop')
            request=build.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,'http://ntfy:8080/upabcdefghijklmnop?up=1')
            self.assertEqual(request.data,b'refresh')
            self.assertNotIn('Authorization',request.headers)
