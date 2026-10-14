import csv
import io
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from server.app import create_app


class CoachingTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=create_app({'TESTING':True,'DATABASE':self.tmp.name+'/db'})
        self.client=self.app.test_client()
        self.auth=self.register('alice')
        self.client.put('/api/settings',headers=self.auth,json={'timezone':'UTC'})
        self.clock=patch('server.app.now',return_value=datetime(2025,4,10,12,tzinfo=timezone.utc));self.clock.start()

    def tearDown(self):
        self.clock.stop();self.tmp.cleanup()

    def register(self,name):
        result=self.client.post('/api/auth/register',json={'username':name,'password':'coaching-test-password'})
        return {'Authorization':'Bearer '+result.json['token']}

    def get(self):
        response=self.client.get('/api/coaching',headers=self.auth)
        self.assertEqual(response.status_code,200)
        return response.json

    def add(self,at='2025-04-09T12:00:00Z',quantity=1,**fields):
        response=self.client.post('/api/cigarettes',headers=self.auth,json={'occurred_at':at,'quantity':quantity,**fields})
        self.assertEqual(response.status_code,201)
        return response.json

    def plan(self,**changes):
        return self.client.put('/api/coaching/plan',headers=self.auth,json={'version':self.get()['plan']['version'],**changes})

    def confirm(self,day,quantity):
        return self.client.put('/api/check-ins/'+day,headers=self.auth,json={'quantity':quantity})

    def craving(self,key='first',**payload):
        return self.client.post('/api/cravings',headers={**self.auth,'Idempotency-Key':key},json=payload)

    def resolve(self,identifier,outcome):
        return self.client.put('/api/cravings/'+str(identifier),headers=self.auth,json={'outcome':outcome})

    def test_default_plan_and_authentication(self):
        result=self.get()
        self.assertEqual(result['plan']['mode'],'observe');self.assertIsNone(result['progress'])
        self.assertFalse(result['plan']['daily_enabled'])
        for path in ('/api/coaching','/api/coaching/export.csv'):
            self.assertEqual(self.client.get(path).status_code,401)

    def test_plan_conflict_partial_update_and_steps(self):
        self.assertEqual(self.plan(mode='reduce',daily_goal=8,reason='For myself',steps=[{'date':'2025-04-10','goal':5}]).status_code,200)
        self.assertEqual(self.get()['current_goal'],5)
        response=self.client.put('/api/coaching/plan',headers=self.auth,json={'version':0,'reason':'stale'})
        self.assertEqual(response.status_code,409)
        self.plan(country='JP')
        self.assertEqual(self.get()['plan']['reason'],'For myself')
        self.plan(mode='quit',quit_date='2025-04-10')
        self.assertEqual(self.get()['current_goal'],0)
        self.assertIsNotNone(self.get()['quit_since'])

    def test_invalid_plan_and_quiet_hours(self):
        for data in ({'mode':'bad'},{'weekly_day':7},{'daily_time':'24:00'},{'daily_enabled':1},
                     {'reason':[]},{'steps':[{'date':'2025-04-10','goal':-1}]},
                     {'steps':[{'date':'2025-04-10','goal':1}]*2},
                     {'daily_enabled':True,'daily_time':'23:00'}):
            self.assertEqual(self.plan(**data).status_code,400,data)
        self.assertEqual(self.plan(daily_enabled=True,daily_time='08:00').status_code,200)
        self.assertTrue(self.client.get('/api/settings',headers=self.auth).json['reminders']['daily_enabled'])

    def test_confirm_zero_requires_explicit_completed_day(self):
        self.assertEqual(self.get()['confirmed_smoke_free_days'],0)
        self.assertEqual(self.confirm('2025-04-09',0).status_code,200)
        self.confirm('2025-04-10',0)
        self.assertEqual(self.get()['confirmed_smoke_free_days'],1)
        self.assertEqual(self.confirm('2025-04-11',0).status_code,400)
        self.client.delete('/api/check-ins/2025-04-09',headers=self.auth)
        self.assertEqual(self.get()['confirmed_smoke_free_days'],0)

    def test_add_delete_reopens_confirmation_and_retry_does_not(self):
        self.confirm('2025-04-09',0)
        entry=self.add()
        self.assertEqual(self.get()['confirmed_smoke_free_days'],0)
        self.assertEqual(self.confirm('2025-04-09',0).status_code,409)
        self.confirm('2025-04-09',1)
        self.client.delete('/api/cigarettes/'+str(entry['id']),headers=self.auth)
        self.assertFalse(next(d for d in self.get()['days'] if d['date']=='2025-04-09')['confirmed'])
        headers={**self.auth,'Idempotency-Key':'same-add'}
        payload={'occurred_at':'2025-04-09T12:00:00Z'}
        self.client.post('/api/cigarettes',headers=headers,json=payload)
        self.confirm('2025-04-09',1)
        self.client.post('/api/cigarettes',headers=headers,json=payload)
        self.assertTrue(next(d for d in self.get()['days'] if d['date']=='2025-04-09')['confirmed'])

    def test_timezone_specific_confirmation_and_invalidation(self):
        self.client.put('/api/settings',headers=self.auth,json={'timezone':'Asia/Kathmandu'})
        self.confirm('2025-04-09',0)
        self.client.put('/api/settings',headers=self.auth,json={'timezone':'UTC'})
        self.assertEqual(self.get()['confirmed_smoke_free_days'],0)
        self.add('2025-04-08T20:00:00Z')
        self.client.put('/api/settings',headers=self.auth,json={'timezone':'Asia/Kathmandu'})
        self.assertFalse(next(d for d in self.get()['days'] if d['date']=='2025-04-09')['confirmed'])

    def test_dst_repeated_hour_confirmed_once(self):
        self.client.put('/api/settings',headers=self.auth,json={'timezone':'Europe/Paris'})
        with patch('server.app.now',return_value=datetime(2025,10,27,12,tzinfo=timezone.utc)):
            self.add('2025-10-26T00:30:00Z');self.add('2025-10-26T01:30:00Z')
            self.assertEqual(self.confirm('2025-10-26',2).status_code,200)
            day=next(d for d in self.get()['days'] if d['date']=='2025-10-26')
            self.assertEqual(day['quantity'],2);self.assertTrue(day['confirmed'])

    def test_fixed_reference_uses_only_confirmed_days_and_historical_cost(self):
        initial=self.add('2025-04-01T12:00:00Z',10)
        r=self.client.post('/api/coaching/baseline',headers=self.auth,json={'start':'2025-04-01','end':'2025-04-02'})
        self.assertEqual(r.status_code,201)
        self.assertEqual(self.get()['progress']['reference_average'],5)
        self.add('2025-04-09T12:00:00Z',2)
        self.assertIsNone(self.get()['progress']['quantity_difference'])
        self.confirm('2025-04-09',2)
        progress=self.get()['progress']
        self.assertEqual(progress['quantity_difference'],3)
        self.assertEqual(progress['reduction_percent'],60)
        self.assertEqual(progress['estimated_cost_difference'],{'EUR':1.8})
        self.client.delete('/api/cigarettes/'+str(initial['id']),headers=self.auth)
        self.assertEqual(self.get()['progress']['reference_average'],5)
        self.assertEqual(self.client.post('/api/coaching/baseline',headers=self.auth,json={'start':'2025-04-01','end':'2025-04-02'}).status_code,409)
        self.client.put('/api/settings',headers=self.auth,json={'currency':'JPY','pack_price':'600'})
        self.add('2025-04-08T12:00:00Z');self.confirm('2025-04-08',1)
        self.assertEqual(self.get()['progress']['estimated_cost_difference'],{})

    def test_reference_rejects_empty_current_and_oversized_period(self):
        for start,end in [('2025-04-09','2025-04-10'),('2025-01-01','2025-04-09'),('2025-04-09','2025-04-09')]:
            self.assertEqual(self.client.post('/api/coaching/baseline',headers=self.auth,json={'start':start,'end':end}).status_code,400)

    def test_cravings_idempotency_single_active_and_atomic_smoked(self):
        first=self.craving(trigger='coffee',strategy='water').json
        self.assertEqual(self.craving(key='other').json['id'],first['id'])
        path='/api/cravings/'+str(first['id'])
        def finish(_):return self.app.test_client().put(path,headers=self.auth,json={'outcome':'smoked'}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(list(pool.map(finish,range(2))),[200,200])
        self.assertEqual(self.client.get('/api/stats',headers=self.auth).json['today']['quantity'],1)
        self.assertEqual(self.resolve(first['id'],'passed').status_code,409)
        second=self.craving(key='new').json
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(self.craving().json['id'],first['id'])
        self.resolve(second['id'],'passed')
        self.confirm('2025-04-09',0)
        third=self.craving(key='third').json;self.resolve(third['id'],'smoked')
        self.assertEqual(self.get()['cravings_passed'],1)
        self.assertEqual(self.get()['confirmed_smoke_free_days'],1)

    def test_private_resources_and_trigger_tags(self):
        entry=self.add(trigger='stress');craving=self.craving(trigger='stress').json
        other=self.register('bob')
        self.assertEqual(self.client.put('/api/cravings/'+str(craving['id']),headers=other,json={'outcome':'smoked'}).status_code,404)
        self.assertEqual(self.client.patch('/api/cigarettes/'+str(entry['id'])+'/context',headers=other,json={'trigger':'coffee'}).status_code,404)
        data=self.client.get('/api/coaching',headers=other).json
        self.assertIsNone(data['pending_craving']);self.assertEqual(sum(r['cigarettes'] for r in data['triggers']),0)
        self.client.patch('/api/cigarettes/'+str(entry['id'])+'/context',headers=self.auth,json={'trigger':'coffee'})
        coffee=next(r for r in self.get()['triggers'] if r['trigger']=='coffee')
        self.assertEqual(coffee['cigarettes'],1)

    def test_export_does_not_duplicate_daily_quantities_for_multiple_currencies(self):
        self.add()
        self.client.put('/api/settings',headers=self.auth,json={'currency':'JPY','pack_price':'600'})
        self.add();self.confirm('2025-04-09',2)
        response=self.client.get('/api/coaching/export.csv',headers=self.auth)
        rows=list(csv.DictReader(io.StringIO(response.data.decode('utf-8-sig'))))
        day=next(r for r in rows if r['date']=='2025-04-09')
        self.assertEqual(day['quantity'],'2');self.assertEqual(day['confirmed'],'true')
        self.assertIn('EUR',day['historical_costs']);self.assertIn('JPY',day['historical_costs'])
        self.assertEqual(len(rows),30)
