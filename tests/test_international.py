from contextlib import closing
import csv
import io
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from werkzeug.security import generate_password_hash

from server.app import SCHEMA, create_app
from server.international import CURRENCIES, TIMEZONES, TRANSLATIONS


class InternationalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = self.tmp.name + '/db.sqlite'
        self.app = create_app({'TESTING': True, 'DATABASE': self.path})
        self.client = self.app.test_client()
        result = self.client.post('/api/auth/register', json={'username':'alice', 'password':'very-long-password'})
        self.auth = {'Authorization': 'Bearer ' + result.json['token']}

    def settings(self, **data):
        return self.client.put('/api/settings', headers=self.auth, json=data)

    def add(self, **data):
        result = self.client.post('/api/cigarettes', headers=self.auth, json=data)
        self.assertEqual(result.status_code, 201, result.json)
        return result.json

    def stats(self):
        return self.client.get('/api/stats', headers=self.auth).json

    def test_default_english_and_full_catalogs(self):
        prefs = self.client.get('/api/settings', headers=self.auth).json
        self.assertEqual((prefs['language'],prefs['currency'],prefs['pack_price']), ('en','EUR','12.00'))
        config = self.client.get('/api/config').json
        self.assertEqual({r['code'] for r in config['languages']}, {'en','fr','ja'})
        self.assertEqual(set(config['timezones']),set(TIMEZONES))
        self.assertGreater(len(config['timezones']),300)
        self.assertLess(len(config['timezones']),400)
        currencies = {c['code']: c for c in config['currencies']}
        self.assertGreater(len(currencies),140)
        self.assertEqual(currencies['JPY']['digits'],0)
        self.assertEqual(currencies['KWD']['digits'],3)
        for code in ['USD','EUR','CAD','AUD','GBP','CHF','CNY','JPY']:
            self.assertIn(code,currencies)
        for zone in ['Asia/Kathmandu','Pacific/Chatham','America/New_York','UTC','Europe/Paris']:
            self.assertIn(zone, config['timezones'])

    def test_each_timezone_can_be_saved(self):
        for zone in TIMEZONES:
            result = self.settings(timezone=zone)
            self.assertEqual(result.status_code,200,zone)
            self.assertEqual(result.json['timezone'],zone)

    def test_currency_changes_preserve_original_costs(self):
        eur = self.add(quantity=2)
        self.assertEqual(self.settings(currency='USD',pack_price='10.00').status_code,200)
        usd = self.add(quantity=2)
        self.assertEqual(self.settings(currency='JPY',pack_price='600').status_code,200)
        jpy = self.add(quantity=2)
        self.assertEqual((eur['currency'],usd['currency'],jpy['currency']),('EUR','USD','JPY'))
        for scope in ['today','total','period']:
            summary=self.stats()[scope]
            self.assertEqual(summary['costs'], {'EUR':1.2,'USD':1.0,'JPY':60.0})
            self.assertEqual(summary['quantity'],6)
            self.assertIsNone(summary['cost'])
            self.assertIsNone(summary['currency'])
        rows = list(csv.DictReader(io.StringIO(self.client.get('/api/export.csv',headers=self.auth).text.lstrip('\ufeff'))))
        self.assertEqual({row['currency']:row['cost'] for row in rows}, {'EUR':'1.20','USD':'1.00','JPY':'60'})
        self.assertEqual(self.stats()['daily'][-1]['costs'], {'EUR':1.2,'USD':1.0,'JPY':60.0})

    def test_currency_precision_and_no_float_drift(self):
        self.assertEqual(self.settings(currency='JPY',pack_price='600.01').status_code,400)
        self.assertEqual(self.settings(currency='JPY',pack_price='601',pack_size=2).status_code,200)
        row=self.add()
        self.assertEqual(row['cost'],301)
        csv_text=self.client.get('/api/export.csv',headers=self.auth).text
        self.assertIn(',301,JPY,',csv_text)
        self.assertEqual(self.settings(currency='KWD',pack_price='1.234',pack_size=1).status_code,200)
        self.assertEqual(self.add()['cost'],1.234)
        self.assertEqual(self.settings(currency='KWD',pack_price='1.2345').status_code,400)
        self.assertEqual(self.settings(currency='USD',pack_price='0.10',pack_size=3).status_code,200)
        self.add(quantity=3)
        self.assertEqual(self.stats()['total']['costs']['USD'],0.10)

    def test_currency_requires_price_and_valid_input(self):
        self.assertEqual(self.settings(currency='JPY').json['code'],'price_required')
        for price in ['NaN','Infinity','-1','1000001',True,[],{},'','1e9999']:
            with self.subTest(price=price):
                self.assertEqual(self.settings(pack_price=price).status_code,400)
        for currency in ['BAD','usd',[],None]:
            self.assertEqual(self.settings(currency=currency,pack_price='12').status_code,400)
        for locale in ['xx',[],None]:
            self.assertEqual(self.settings(language=locale).status_code,400)
        self.assertEqual(self.settings(timezone='/etc/passwd').status_code,400)
        self.assertEqual(self.settings(timezone='localtime').status_code,400)

    def test_account_preferences_isolation_and_persistence(self):
        self.settings(language='ja',currency='JPY',pack_price='600',timezone='Asia/Tokyo')
        bob = self.client.post('/api/auth/register',json={'username':'bob','password':'long-bob-password'}).json['token']
        other=self.client.get('/api/settings',headers={'Authorization':'Bearer '+bob}).json
        self.assertEqual((other['language'],other['currency'],other['timezone']),('en','EUR','Europe/Paris'))
        restarted=create_app({'TESTING':True,'DATABASE':self.path}).test_client()
        prefs=restarted.get('/api/settings',headers=self.auth).json
        self.assertEqual((prefs['language'],prefs['currency'],prefs['pack_price']),('ja','JPY','600'))

    def test_localized_errors_and_currency_names(self):
        for code in ['en','fr','ja']:
            self.settings(language=code)
            error=self.settings(timezone='not-valid')
            self.assertEqual(error.json['error'],TRANSLATIONS[code]['invalid_timezone'])
            public=self.client.get('/api/stats',headers={'Accept-Language':code})
            self.assertEqual(public.json['error'],TRANSLATIONS[code]['auth_required'])
        en=self.client.get('/api/config',headers={'Accept-Language':'en'}).json['currencies']
        ja=self.client.get('/api/config',headers={'Accept-Language':'ja'}).json['currencies']
        self.assertNotEqual(en,ja)
        malformed=self.client.post('/api/auth/register',data='{',content_type='application/json',headers={'Accept-Language':'ja'})
        self.assertEqual(malformed.json['error'],TRANSLATIONS['ja']['request_error'])

    def test_registration_language(self):
        result=self.client.post('/api/auth/register',json={'username':'japanese','password':'very-long-password','language':'ja'})
        prefs=self.client.get('/api/settings',headers={'Authorization':'Bearer '+result.json['token']}).json
        self.assertEqual(prefs['language'],'ja')
        self.assertEqual(self.client.post('/api/auth/register',json={'username':'badlang','password':'very-long-password','language':[]}).status_code,400)

    def test_android_wall_time_uses_server_timezone(self):
        self.settings(timezone='Asia/Kathmandu')
        row=self.add(occurred_at_local='2025-01-02T00:30:00')
        self.assertEqual(row['occurred_at'],'2025-01-01T18:45:00.000000+00:00')
        self.assertEqual(row['local_datetime'],'2025-01-02T00:30:00+05:45')
        self.settings(timezone='Europe/Paris')
        invalid=self.client.post('/api/cigarettes',headers=self.auth,json={'occurred_at_local':'2025-03-30T02:30:00'})
        self.assertEqual(invalid.status_code,400)

    def test_additive_legacy_migration_is_idempotent(self):
        legacy=self.tmp.name+'/legacy.sqlite'
        with closing(sqlite3.connect(legacy)) as conn, conn:
            conn.executescript(SCHEMA)
            conn.execute('INSERT INTO users(username,password_hash,pack_price_cents) VALUES(?,?,?)',('legacy',generate_password_hash('long-legacy-password'),1350))
            conn.execute("INSERT INTO cigarettes(user_id,occurred_at,quantity,unit_cost_micros,source) VALUES(1,'2025-01-01T00:00:00.000000+00:00',2,675000,'web')")
        def boot(_): return create_app({'TESTING':True,'DATABASE':legacy})
        with ThreadPoolExecutor(max_workers=3) as pool:
            apps=list(pool.map(boot,range(3)))
        client=apps[0].test_client()
        auth=client.post('/api/auth/login',json={'username':'legacy','password':'long-legacy-password'}).json['token']
        prefs=client.get('/api/settings',headers={'Authorization':'Bearer '+auth}).json
        self.assertEqual((prefs['pack_price'],prefs['currency'],prefs['language']),('13.50','EUR','en'))
        self.assertEqual(client.get('/api/stats',headers={'Authorization':'Bearer '+auth}).json['total']['costs'],{'EUR':1.35})

    def test_shared_translation_completeness(self):
        keys=set(TRANSLATIONS['en'])
        for code, messages in TRANSLATIONS.items():
            self.assertEqual(set(messages),keys)
            for key, value in messages.items():
                self.assertTrue(value.strip(),key)
                self.assertEqual(set(re.findall(r'\{\d+\}',value)),set(re.findall(r'\{\d+\}',TRANSLATIONS['en'][key])),(code,key))
        html=Path('server/static/index.html').read_text()
        for key in re.findall(r'data-i18n(?:-aria)?="([^"]+)"',html):
            self.assertIn(key,keys)
        for source in ['server/static/app.js','android/app/src/main/java/eu/cormerais/stopclop/MainActivity.java']:
            for key in re.findall(r"\bt\(['\"]([^'\"]+)['\"]",Path(source).read_text()):
                self.assertIn(key,keys,source)


if __name__ == '__main__': unittest.main()
