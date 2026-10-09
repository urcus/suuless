"""Live streams across sessions, commits, reconnects and revocations."""
import hashlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from server.app import create_app
from server.sync import events


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=self.tmp.name+'/sync.db'
        self.app=create_app({'TESTING':True,'DATABASE':self.path})
        self.client=self.app.test_client()
        self.alice=self.register('alice'); self.bob=self.register('bob')
        self.conn=sqlite3.connect(self.path); self.addCleanup(self.conn.close)
        self.tick=0

    def register(self,name):
        result=self.client.post('/api/auth/register',json={'username':name,'password':'long-test-password'}).json
        return {'Authorization':'Bearer '+result['token']}

    def stream(self,headers,cursor=''):
        digest=hashlib.sha256(headers['Authorization'][7:].encode()).hexdigest()
        token,user=self.conn.execute('SELECT id,user_id FROM tokens WHERE digest=?',(digest,)).fetchone()
        def sleep(seconds): self.tick+=seconds
        stream=events(self.path,token,user,digest,cursor,duration=25,clock=lambda:self.tick,sleep=sleep)
        self.addCleanup(stream.close)
        return stream

    def revision(self,stream):
        event=next(stream)
        self.assertIn('event: refresh',event)
        self.assertIn('data: {}',event)
        return event.splitlines()[0][4:]

    def test_auth_headers_capacity_and_release(self):
        self.assertEqual(self.client.get('/api/sync/events').status_code,401)
        self.assertEqual(self.client.get('/api/sync/config',headers=self.alice).json['transport'],'sse')
        self.assertEqual(self.client.get('/api/sync/events',headers=dict(self.alice,**{'Last-Event-ID':'bad'})).status_code,400)
        streams=[]
        try:
            for _ in range(16):
                r=self.client.get('/api/sync/events',headers=self.alice,buffered=False);streams.append(r)
                self.assertEqual(r.status_code,200)
                self.assertEqual(r.headers['Cache-Control'],'no-store')
                self.assertEqual(r.headers['X-Accel-Buffering'],'no')
            self.assertEqual(self.client.get('/api/sync/events',headers=self.alice).status_code,503)
            self.assertEqual(self.client.get('/api/settings',headers=self.alice).status_code,200)
            streams.pop().close()
            r=self.client.get('/api/sync/events',headers=self.alice,buffered=False);streams.append(r)
            self.assertEqual(r.status_code,200)
        finally:
            for r in streams:r.close()

    def test_isolation_idempotence_and_reconnect(self):
        alice=self.stream(self.alice); bob=self.stream(self.bob)
        old=self.revision(alice); self.revision(bob)
        headers=dict(self.alice,**{'Idempotency-Key':'sync-test'})
        self.client.post('/api/cigarettes',headers=headers,json={'source':'streamdeck'})
        new=self.revision(alice); self.assertNotEqual(old,new)
        self.assertEqual(next(bob),': keepalive\n\n')
        self.client.post('/api/cigarettes',headers=headers,json={'source':'streamdeck'})
        self.assertEqual(next(alice),': keepalive\n\n')
        self.assertEqual(self.revision(self.stream(self.alice,old)),new)
        self.assertEqual(next(self.stream(self.alice,new)),': keepalive\n\n')
        # Reopening the app/database preserves the cursor.
        create_app({'TESTING':True,'DATABASE':self.path})
        self.assertEqual(self.revision(self.stream(self.alice)),new)

    def test_settings_delete_and_rollback(self):
        stream=self.stream(self.alice); old=self.revision(stream)
        self.client.put('/api/settings',headers=self.alice,json={'language':'fr'})
        new=self.revision(stream); self.assertNotEqual(old,new)
        self.client.put('/api/settings',headers=self.alice,json={'pack_size':-1})
        self.assertEqual(next(stream),': keepalive\n\n')
        entry=self.client.post('/api/cigarettes',headers=self.alice).json
        added=self.revision(stream)
        self.client.delete('/api/cigarettes/'+str(entry['id']),headers=self.alice)
        self.assertNotEqual(self.revision(stream),added)

    def test_logout_revokes_open_stream_even_if_token_id_reused(self):
        stream=self.stream(self.bob);self.revision(stream)
        self.client.post('/api/auth/logout',headers=self.bob)
        self.client.post('/api/auth/login',json={'username':'bob','password':'long-test-password'})
        self.assertIn('event: revoked',next(stream))
        with self.assertRaises(StopIteration):next(stream)

    def test_expiry_and_explicit_revocation(self):
        stream=self.stream(self.alice);self.revision(stream)
        with self.conn:self.conn.execute('UPDATE tokens SET expires_at=?',((datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),))
        self.assertIn('event: revoked',next(stream))

    def test_heartbeat_and_bounded_lifetime(self):
        stream=self.stream(self.alice);self.revision(stream)
        frames=list(stream)
        self.assertTrue(frames)
        self.assertTrue(all(frame==': keepalive\n\n' for frame in frames))
        self.assertEqual(self.tick,25)
