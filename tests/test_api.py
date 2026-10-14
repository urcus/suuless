from contextlib import closing
import csv
import io
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from server.app import create_app


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATABASE': self.tmp.name + '/test.db'})
        self.client = self.app.test_client()
        self.auth = self.register('alice')

    def tearDown(self):
        self.tmp.cleanup()

    def register(self, username):
        result = self.client.post('/api/auth/register', json={'username': username, 'password': 'long-test-password'})
        self.assertEqual(result.status_code, 201)
        return {'Authorization': 'Bearer ' + result.json['token']}

    def add(self, data=None, headers=None):
        return self.client.post('/api/cigarettes', json=data or {}, headers=headers or self.auth)

    def stats(self, query='', headers=None):
        response = self.client.get('/api/stats' + query, headers=headers or self.auth)
        self.assertEqual(response.status_code, 200)
        return response.json

    def settings(self, **overrides):
        data = {'pack_price_cents': 1200, 'pack_size': 20, 'daily_target': 10, 'timezone': 'Europe/Paris'}
        data.update(overrides)
        return self.client.put('/api/settings', json=data, headers=self.auth)

    def test_habits_use_account_zone_range_and_isolation(self):
        self.settings(timezone='Asia/Kathmandu')
        self.add({'quantity': 5, 'occurred_at': '2025-01-01T18:30:00Z'})
        self.add({'quantity': 20, 'occurred_at': '2025-01-02T18:30:00Z'})
        other = self.register('other-habits')
        self.add({'quantity': 100, 'occurred_at': '2025-01-01T18:30:00Z'}, headers=other)
        result = self.stats('?start=2025-01-02&end=2025-01-02')['analysis']
        self.assertEqual(sum(hour['quantity'] for hour in result['hourly']), 5)
        self.assertEqual(result['hourly'][0]['quantity'], 5)
        self.assertEqual(result['weekdays'][3]['average'], 5)
        self.assertEqual(result['projection']['quantity'], 150)
        self.assertEqual(result['trend'][0]['quantity'], 5)

    def test_history_age_thresholds_and_account_isolation(self):
        self.settings(timezone='UTC')
        other = self.register('older-history')
        self.add({'occurred_at': '2024-01-01T12:00:00Z'}, headers=other)
        instant = datetime(2025, 4, 1, 12, tzinfo=timezone.utc)
        with patch('server.app.now', return_value=instant):
            self.assertEqual(self.stats()['history_days'], 0)
            self.assertIsNone(self.stats()['history_start'])
            for days in (1, 29, 30, 89, 90):
                first = instant - timedelta(days=days-1)
                entry = self.add({'occurred_at': first.isoformat()}).json
                result = self.stats('?start=2025-04-01&end=2025-04-01')
                self.assertEqual(result['history_days'], days)
                self.assertEqual(result['history_start'], first.date().isoformat())
                self.client.delete('/api/cigarettes/'+str(entry['id']), headers=self.auth)
            self.assertEqual(self.stats()['history_days'], 0)

    def test_history_age_uses_profile_calendar_not_24_hour_intervals(self):
        self.settings(timezone='Asia/Kathmandu')
        self.add({'occurred_at': '2025-03-03T12:00:00Z'})
        with patch('server.app.now', return_value=datetime(2025,4,1,20,tzinfo=timezone.utc)):
            self.assertEqual(self.stats()['history_days'], 31)
            self.settings(timezone='UTC')
            self.assertEqual(self.stats()['history_days'], 30)

    def test_auth_required_for_all_private_routes(self):
        for path in ['/api/me', '/api/stats', '/api/cigarettes', '/api/settings', '/api/tokens', '/api/export.csv']:
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.post('/api/cigarettes', json={}).status_code, 401)

    def test_register_validation_and_login(self):
        self.assertEqual(self.client.post('/api/auth/register', json={'username':'bob','password':'short'}).status_code, 400)
        self.assertEqual(self.client.post('/api/auth/register', json={'username':'ALICE','password':'long-test-password'}).status_code, 409)
        self.assertEqual(self.client.post('/api/auth/login', json={'username':'ALICE','password':'long-test-password'}).status_code, 200)
        self.assertEqual(self.client.post('/api/auth/login', json={'username':'alice','password':'wrong'}).status_code, 401)

    def test_user_isolation(self):
        entry = self.add().json
        bob = self.register('bob')
        self.assertEqual(self.stats(headers=bob)['total']['quantity'], 0)
        self.assertEqual(self.client.get('/api/cigarettes', headers=bob).json['total'], 0)
        self.assertEqual(self.client.delete('/api/cigarettes/' + str(entry['id']), headers=bob).status_code, 404)
        self.settings(pack_price_cents=1500)
        self.assertEqual(self.client.get('/api/settings', headers=bob).json['pack_price_cents'], 1200)
        self.assertNotIn(str(entry['occurred_at']), self.client.get('/api/export.csv', headers=bob).text)
        key = self.client.post('/api/tokens', json={'name':'Stream Deck'}, headers=self.auth).json
        self.assertEqual(self.client.delete('/api/tokens/' + str(key['id']), headers=bob).status_code, 404)
        self.assertNotIn(key['id'], [r['id'] for r in self.client.get('/api/tokens', headers=bob).json])

    def test_plus_one_without_body(self):
        self.assertEqual(self.client.post('/api/cigarettes', headers=self.auth).status_code, 201)
        stats = self.stats()
        self.assertEqual(stats['today'], {'quantity':1,'cost':.6,'currency':'EUR','costs':{'EUR':.6}})
        self.assertEqual(stats['total'], stats['today'])

    def test_historical_price_preserved(self):
        self.add({'quantity':20})
        self.settings(pack_price_cents=1500)
        self.add({'quantity':20})
        self.assertEqual(self.stats()['total'], {'quantity':40,'cost':27.0,'currency':'EUR','costs':{'EUR':27.0}})

    def test_fractional_unit_price_aggregate(self):
        self.settings(pack_price_cents=1000, pack_size=30)
        for _ in range(30): self.add()
        self.assertEqual(self.stats()['total']['cost'], 10.0)

    def test_timezone_and_empty_days(self):
        self.settings(timezone='Asia/Tokyo')
        self.add({'occurred_at':'2025-01-01T15:00:00Z'})
        data = self.stats('?start=2025-01-01&end=2025-01-03')
        self.assertEqual([d['quantity'] for d in data['daily']], [0,1,0])
        self.assertEqual(data['period']['average_per_day'], .33)
        self.assertEqual(data['period']['days_without_entries'], 2)

    def test_dst_day_boundaries(self):
        for at in ['2025-03-29T23:00:00Z','2025-03-30T21:59:59Z','2025-03-30T22:00:00Z']:
            self.assertEqual(self.add({'occurred_at':at}).status_code, 201)
        self.assertEqual(self.stats('?start=2025-03-30&end=2025-03-30')['period']['quantity'], 2)

    def test_today_uses_profile_timezone(self):
        self.settings(timezone='Asia/Tokyo')
        self.add({'occurred_at':'2025-01-02T00:00:00+09:00'})
        with patch('server.app.now', return_value=datetime(2025,1,1,16,tzinfo=timezone.utc)):
            # Token expiry is in the future relative to this test clock.
            self.assertEqual(self.stats()['today']['quantity'], 1)

    def test_idempotency_and_concurrent_requests(self):
        headers = dict(self.auth, **{'Idempotency-Key':'same-click'})
        def send(_):
            with self.app.test_client() as client:
                response = client.post('/api/cigarettes', json={}, headers=headers)
                return response.status_code, response.json['id']
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(send, range(6)))
        self.assertEqual(sum(code == 201 for code, _ in results), 1)
        self.assertEqual(len({identifier for _, identifier in results}), 1)
        self.assertEqual(self.stats()['total']['quantity'], 1)
        bob=self.register('bob')
        self.assertEqual(self.add(headers=dict(bob, **{'Idempotency-Key':'same-click'})).status_code,201)

    def test_validation(self):
        for data in [{'quantity':0},{'quantity':True},{'quantity':1.5},{'quantity':201},{'source':'invalid'},
                     {'occurred_at':'2025-01-01'},{'occurred_at':'tomorrow'},{'occurred_at':'2999-01-01T00:00:00Z'}, {'occurred_at':12}]:
            with self.subTest(data=data): self.assertEqual(self.add(data).status_code, 400)
        self.assertEqual(self.settings(timezone='invalid').status_code, 400)
        self.assertEqual(self.settings(pack_size=0).status_code, 400)
        for query in ['start=x','end=0001-01-01','start=2020-01-01&end=2025-01-01','start=2025-02-02&end=2025-01-01']:
            self.assertEqual(self.client.get('/api/stats?'+query,headers=self.auth).status_code,400)
        self.assertEqual(self.client.post('/api/cigarettes',json=[],headers=self.auth).status_code,400)

    def test_client_clock_skew_is_clamped_but_future_dates_are_rejected(self):
        received = datetime(2025, 1, 1, 12, tzinfo=timezone.utc)
        with patch('server.app.now', return_value=received):
            for seconds in [.7, 5]:
                response = self.add({'occurred_at': (received + timedelta(seconds=seconds)).isoformat(), 'source': 'android'})
                self.assertEqual(response.status_code, 201)
                self.assertEqual(datetime.fromisoformat(response.json['occurred_at']), received)
            for seconds in [5.001, 60, 86400]:
                response = self.add({'occurred_at': (received + timedelta(seconds=seconds)).isoformat()})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json['code'], 'invalid_entry_date')
            # Manually entered local dates remain strict, including sub-second futures.
            self.assertEqual(self.add({'occurred_at_local': '2025-01-01T13:00:00.700000'}).status_code, 400)
            past = received - timedelta(seconds=.7)
            response = self.add({'occurred_at': past.isoformat()})
            self.assertEqual(datetime.fromisoformat(response.json['occurred_at']), past)

    def test_widget_clock_skew_at_midnight_keeps_today_and_retry_idempotent(self):
        self.settings(timezone='Asia/Tokyo')
        received = datetime(2025, 1, 1, 14, 59, 59, 800000, tzinfo=timezone.utc)
        payload = {'occurred_at': '2025-01-01T15:00:00.500000Z', 'source': 'android'}
        headers = dict(self.auth, **{'Idempotency-Key': 'widget-clock-skew'})
        with patch('server.app.now', return_value=received):
            first, retry = self.add(payload, headers), self.add(payload, headers)
            self.assertEqual((first.status_code, retry.status_code), (201, 200))
            self.assertEqual(first.json['id'], retry.json['id'])
            self.assertEqual(first.json['local_datetime'][:10], '2025-01-01')
            self.assertEqual(self.stats()['today']['quantity'], 1)

    def test_analysis_previous_period_and_user_isolation(self):
        self.settings(timezone='Asia/Tokyo')
        self.add({'quantity':4,'occurred_at':'2025-01-01T00:00:00+09:00'})
        self.add({'quantity':2,'occurred_at':'2025-01-03T00:00:00+09:00'})
        result=self.stats('?start=2025-01-03&end=2025-01-04')['analysis']
        self.assertEqual(result['average_quantity_per_day'],1)
        self.assertEqual(result['average_cost_per_day'],{'EUR':.6})
        self.assertEqual(result['previous_period']['quantity'],4)
        self.assertEqual(result['previous_period']['start'],'2025-01-01')
        self.assertEqual(result['comparison']['quantity_percent'],-50)
        self.assertEqual(result['daily'][1]['quantity_delta'],-1)
        other=self.register('analysis-other')
        self.assertEqual(self.stats('?start=2025-01-03&end=2025-01-04',headers=other)['analysis']['previous_period']['quantity'],0)
        self.assertIsNone(self.stats('?start=2000-01-01&end=2000-01-02')['analysis']['comparison']['quantity_delta'])

    def test_delete_pagination_csv(self):
        for _ in range(3): self.add()
        page=self.client.get('/api/cigarettes?limit=2&offset=1', headers=self.auth).json
        self.assertEqual(page['total'], 3);self.assertEqual(len(page['items']), 2)
        data=self.client.get('/api/export.csv',headers=self.auth)
        self.assertEqual(data.headers['Cache-Control'],'no-store')
        rows=list(csv.reader(io.StringIO(data.text.lstrip('\ufeff'))))
        self.assertEqual(len(rows),4)
        identifier=page['items'][0]['id']
        self.assertEqual(self.client.delete('/api/cigarettes/'+str(identifier),headers=self.auth).status_code,204)
        self.assertEqual(self.stats()['total']['quantity'],2)

    def test_token_revocation_and_expiry(self):
        key=self.client.post('/api/tokens',json={'name':'streamdeck'},headers=self.auth).json
        bearer={'Authorization':'Bearer '+key['token']}
        self.assertEqual(self.add(headers=bearer).status_code,201)
        listing=self.client.get('/api/tokens',headers=self.auth).json
        self.assertFalse(any('digest' in entry or 'token' in entry for entry in listing))
        with closing(sqlite3.connect(self.app.config['DATABASE'])) as conn, conn:
            conn.execute("UPDATE tokens SET expires_at='2000-01-01' WHERE id=?",(key['id'],))
        self.assertEqual(self.add(headers=bearer).status_code,401)
        self.client.delete('/api/tokens/'+str(key['id']),headers=self.auth)
        self.assertEqual(self.add(headers=bearer).status_code,401)
        self.client.post('/api/auth/logout',headers=self.auth)
        self.assertEqual(self.add().status_code,401)

    def test_persistence_on_restart(self):
        self.add()
        app=create_app({'TESTING':True,'DATABASE':self.app.config['DATABASE']})
        self.assertEqual(app.test_client().get('/api/stats',headers=self.auth).json['total']['quantity'],1)

    def test_close_registration_and_rate_limit(self):
        self.app.config['ALLOW_REGISTRATION']=False
        self.assertFalse(self.client.get('/api/config').json['registration_enabled'])
        self.assertEqual(self.client.post('/api/auth/register',json={}).status_code,403)
        with closing(sqlite3.connect(self.app.config['DATABASE'])) as conn, conn:
            conn.executemany('INSERT INTO auth_attempts VALUES(?,?)',[('127.0.0.1',datetime.now(timezone.utc).isoformat())]*30)
        self.assertEqual(self.client.post('/api/auth/login',json={}).status_code,429)


if __name__ == '__main__':
    unittest.main()
