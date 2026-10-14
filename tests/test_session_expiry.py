"""Fixed web expiry, explicit Android compatibility and unchanged API keys."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from server.app import create_app


class SessionExpiryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = create_app({'TESTING': True, 'DATABASE': self.tmp.name+'/db'})
        self.client = self.app.test_client()
        # Cross a DST transition: expiry is 24 elapsed hours, not local midnight.
        self.start = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
        self.clock = patch('server.app.now', return_value=self.start).start()
        self.addCleanup(patch.stopall)

    def issue(self, username, client=None, register=True):
        payload = {'username': username, 'password': 'session-test-password'}
        if client is not None:
            payload['client'] = client
        response = self.client.post('/api/auth/'+('register' if register else 'login'), json=payload)
        self.assertEqual(response.status_code, 201 if register else 200)
        return response.json

    def me(self, issued):
        return self.client.get('/api/me', headers={'Authorization':'Bearer '+issued['token']})

    def test_web_registration_and_login_expire_at_24_hours(self):
        for index, kind in enumerate([None, 'web']):
            registered = self.issue('web-'+str(index), kind)
            logged = self.issue('web-'+str(index), kind, register=False)
            for issued in [registered, logged]:
                self.assertEqual(datetime.fromisoformat(issued['expires_at']), self.start+timedelta(days=1))
                self.clock.return_value = self.start+timedelta(hours=23, minutes=59, seconds=59)
                self.assertEqual(self.me(issued).status_code, 200)
                self.clock.return_value = self.start+timedelta(days=1)
                self.assertEqual(self.me(issued).status_code, 401)
            self.clock.return_value = self.start

    def test_android_and_personal_key_lifetimes_unchanged(self):
        registered = self.issue('android-user', 'android')
        logged = self.issue('android-user', 'android', register=False)
        headers = {'Authorization':'Bearer '+logged['token']}
        key = self.client.post('/api/tokens', headers=headers, json={'name':'Stream Deck'}).json
        for issued in [registered, logged]:
            self.assertEqual(datetime.fromisoformat(issued['expires_at']), self.start+timedelta(days=30))
        self.assertEqual(datetime.fromisoformat(key['expires_at']), self.start+timedelta(days=365))
        self.clock.return_value = self.start+timedelta(days=1)
        self.assertEqual(self.me(logged).status_code, 200)
        self.clock.return_value = self.start+timedelta(days=30)
        self.assertEqual(self.me(logged).status_code, 401)
        self.assertEqual(self.me(key).status_code, 200)

    def test_invalid_client_is_rejected(self):
        self.issue('valid-user')
        for endpoint in ['login', 'register']:
            for kind in ['ios', 30, [], None]:
                response = self.client.post('/api/auth/'+endpoint, json={
                    'username':'valid-user','password':'session-test-password','client':kind})
                self.assertEqual(response.status_code, 400)
