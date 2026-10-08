from contextlib import closing
from datetime import datetime, timezone
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from server.app import create_app
from server.timezones import TIMEZONES, ALIASES, get_zone, timezone_catalog, timezone_info, search_key


class TimezoneTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = self.tmp.name + '/test.sqlite'
        self.app = create_app({'TESTING':True,'DATABASE':self.path})
        self.client = self.app.test_client()
        self.auth = self.register('alice', timezone='Asia/Tokyo')

    def register(self, username, **extra):
        response = self.client.post('/api/auth/register',json=dict(username=username,password='long-test-password',**extra))
        self.assertEqual(response.status_code,201)
        return {'Authorization':'Bearer '+response.json['token']}

    def settings(self, **data):
        response=self.client.put('/api/settings',headers=self.auth,json=data)
        self.assertEqual(response.status_code,200,response.json)
        return response.json

    def add(self, **data):
        return self.client.post('/api/cigarettes',headers=self.auth,json=data)

    def test_curated_catalog_does_not_merge_by_current_offset(self):
        for excluded in ['US/Eastern','Asia/Calcutta','Asia/Katmandu','Europe/Kiev','Etc/GMT+9','Factory','CET','GMT','Zulu']:
            self.assertNotIn(excluded,TIMEZONES)
        self.assertEqual(len(TIMEZONES),len(set(TIMEZONES)))
        for identifier in ['UTC','Asia/Tokyo','Europe/Paris','America/New_York','America/Phoenix','America/Denver']:
            self.assertIn(identifier,TIMEZONES)
        winter=datetime(2025,1,1,tzinfo=timezone.utc)
        summer=datetime(2025,7,1,tzinfo=timezone.utc)
        self.assertEqual(timezone_info('America/Denver','en',winter)['offset_seconds'],timezone_info('America/Phoenix','en',winter)['offset_seconds'])
        self.assertNotEqual(timezone_info('America/Denver','en',summer)['offset_seconds'],timezone_info('America/Phoenix','en',summer)['offset_seconds'])

    def test_localized_city_country_alias_search(self):
        catalog={entry['id']:entry for entry in timezone_catalog('ja',datetime(2025,1,1,tzinfo=timezone.utc))}
        tokyo=catalog['Asia/Tokyo']
        for term in ['Tokyo','東京','Japan','Japon','日本','Asia/Tokyo']:
            self.assertIn(search_key(term),tokyo['search'])
        self.assertIn('UTC+09:00',tokyo['label'])
        for term in ['Calcutta','India','Inde','Asia/Calcutta']:
            self.assertIn(search_key(term),catalog['Asia/Kolkata']['search'])
        self.assertEqual(ALIASES['US/Eastern'],'America/New_York')
        self.assertEqual(ALIASES['Asia/Calcutta'],'Asia/Kolkata')

    def test_offsets_follow_actual_instant_in_both_hemispheres(self):
        january=datetime(2025,1,15,tzinfo=timezone.utc)
        july=datetime(2025,7,15,tzinfo=timezone.utc)
        for zone,winter,summer in [('Europe/Paris','UTC+01:00','UTC+02:00'),
                                    ('Asia/Kathmandu','UTC+05:45','UTC+05:45'),
                                    ('America/St_Johns','UTC-03:30','UTC-02:30'),
                                    ('Pacific/Chatham','UTC+13:45','UTC+12:45'),
                                    ('Australia/Lord_Howe','UTC+11:00','UTC+10:30')]:
            with self.subTest(zone=zone):
                self.assertEqual(timezone_info(zone,'en',january)['utc_offset'],winter)
                self.assertEqual(timezone_info(zone,'en',july)['utc_offset'],summer)
        with patch('server.app.now',return_value=january):
            a=self.client.get('/api/config').json
        with patch('server.app.now',return_value=july):
            b=self.client.get('/api/config').json
        self.assertNotEqual(next(z for z in a['timezone_options'] if z['id']=='Europe/Paris')['utc_offset'],next(z for z in b['timezone_options'] if z['id']=='Europe/Paris')['utc_offset'])

    def test_new_account_detection_alias_and_existing_account_not_overwritten(self):
        auth=self.register('detected',timezone='Asia/Calcutta')
        prefs=self.client.get('/api/settings',headers=auth).json
        self.assertEqual(prefs['timezone'],'Asia/Kolkata')
        self.settings(timezone='Pacific/Chatham')
        login=self.client.post('/api/auth/login',json={'username':'alice','password':'long-test-password','timezone':'Europe/Paris'})
        self.assertEqual(login.status_code,200)
        self.assertEqual(self.settings(language='fr')['timezone'],'Pacific/Chatham')
        other=self.register('bob',timezone='America/New_York')
        self.assertEqual(self.client.get('/api/settings',headers=other).json['timezone'],'America/New_York')

    def test_legacy_ids_preserved_through_restart_and_unrelated_updates(self):
        for old in ['US/Eastern','Asia/Calcutta','Etc/GMT+9']:
            with closing(sqlite3.connect(self.path)) as conn,conn:
                conn.execute('UPDATE users SET timezone=? WHERE username=?',(old,'alice'))
            restarted=create_app({'TESTING':True,'DATABASE':self.path}).test_client()
            prefs=restarted.get('/api/settings',headers=self.auth).json
            self.assertEqual(prefs['timezone'],old)
            self.assertEqual(prefs['timezone_info']['id'],old)
            self.assertTrue(prefs['timezone_info']['legacy'])
            self.assertEqual(self.settings(language='ja')['timezone'],old)
            self.assertEqual(self.add(occurred_at='2025-01-01T12:00:00Z').status_code,201)

    def test_fractional_zone_round_trip_preserves_utc(self):
        for zone,local,utc in [('Asia/Kathmandu','2025-01-02T00:30:00','2025-01-01T18:45:00.000000+00:00'),
                               ('Pacific/Chatham','2025-01-02T00:30:00','2025-01-01T10:45:00.000000+00:00'),
                               ('America/St_Johns','2025-01-02T00:30:00','2025-01-02T04:00:00.000000+00:00')]:
            self.settings(timezone=zone)
            added=self.add(occurred_at_local=local)
            self.assertEqual(added.json['occurred_at'],utc)
            self.assertTrue(added.json['local_datetime'].startswith(local))
            with closing(sqlite3.connect(self.path)) as conn:
                self.assertEqual(conn.execute('SELECT occurred_at FROM cigarettes WHERE id=?',(added.json['id'],)).fetchone()[0],utc)

    def test_dst_day_lengths_and_both_folds(self):
        self.settings(timezone='Europe/Paris')
        for stamp in ['2025-10-25T22:00:00Z','2025-10-26T00:30:00Z','2025-10-26T01:30:00Z','2025-10-26T22:59:59Z','2025-10-26T23:00:00Z']:
            self.assertEqual(self.add(occurred_at=stamp).status_code,201)
        stats=self.client.get('/api/stats?start=2025-10-26&end=2025-10-26',headers=self.auth).json
        self.assertEqual(stats['period']['quantity'],4)
        rows=self.client.get('/api/cigarettes?start=2025-10-26&end=2025-10-26',headers=self.auth).json['items']
        folds=[row['local_datetime'] for row in rows if 'T02:30' in row['local_datetime']]
        self.assertEqual(set(folds),{'2025-10-26T02:30:00+01:00','2025-10-26T02:30:00+02:00'})
        # Local input keeps the documented first occurrence; an explicit offset can select the second.
        self.assertEqual(self.add(occurred_at_local='2025-10-26T02:30:00').json['occurred_at'],'2025-10-26T00:30:00.000000+00:00')
        self.assertEqual(self.add(occurred_at_local='2025-03-30T02:30:00').status_code,400)
        self.settings(timezone='Australia/Lord_Howe')
        self.assertEqual(self.add(occurred_at_local='2025-10-05T02:15:00').status_code,400)
        self.assertEqual(self.add(occurred_at_local='2025-10-05T02:30:00').status_code,201)
