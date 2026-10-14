import unittest
from server.analysis import analyze


class AnalysisMathTest(unittest.TestCase):
    def test_average_zero_days_and_fractional_price(self):
        result=analyze([dict(date='2025-01-01',quantity=1,amounts={'EUR':333333}),dict(date='2025-01-02',quantity=0,amounts={})],
                       [dict(quantity=0,amounts={})]*2,'EUR','2024-12-30','2024-12-31',False)
        self.assertEqual(result['average_cost_per_day'],{'EUR':.17})
        self.assertEqual(result['average_quantity_per_day'],.5)
        self.assertEqual(result['daily'][0]['quantity_percent'],100)
        self.assertEqual(result['daily'][1]['quantity_percent'],-100)
        self.assertEqual(result['daily'][1]['cost_deltas'],{'EUR':-.17})
        self.assertIsNone(result['comparison']['quantity_percent'])
        self.assertEqual(result['comparison']['quantity_delta'],1)

    def test_mixed_currencies_never_combined(self):
        result=analyze([dict(date='2025-01-01',quantity=2,amounts={'JPY':60000000}),dict(date='2025-01-02',quantity=1,amounts={'KWD':1234000})],
                       [dict(quantity=4,amounts={'EUR':2400000}),dict(quantity=0,amounts={})],'JPY','2024-12-30','2024-12-31',True)
        self.assertEqual(result['average_cost_per_day'],{'EUR':0,'JPY':30,'KWD':.617})
        self.assertEqual(result['comparison']['cost_deltas'],{'EUR':-2.4,'JPY':60,'KWD':1.234})
        self.assertEqual(result['comparison']['quantity_percent'],-25)
        self.assertTrue(result['includes_today'])

    def test_empty_and_unavailable_comparison(self):
        result=analyze([dict(date='2000-01-01',quantity=0,amounts={})],[],'EUR',None,None,False)
        self.assertEqual(result['average_cost_per_day'],{'EUR':0})
        self.assertIsNone(result['daily'][0]['quantity_percent'])
        self.assertIsNone(result['comparison']['quantity_delta'])
        self.assertEqual(result['previous_period']['days'],0)


class HabitsTest(unittest.TestCase):
    def habits(self, dates, rows=(), zone='UTC', today=False):
        from zoneinfo import ZoneInfo
        from server.analysis import habits
        return habits(dates, rows, ZoneInfo(zone), today, 'EUR')

    def test_fractional_zone_and_quantity_weights(self):
        result = self.habits([dict(date='2025-01-02', quantity=5, amounts={})],
                             [dict(occurred_at='2025-01-01T18:30:00+00:00', quantity=5)], 'Asia/Kathmandu')
        self.assertEqual(result['hourly'][0]['quantity'], 5)
        self.assertEqual(result['hourly'][0]['share_percent'], 100)
        self.assertEqual(result['weekdays'][3]['average'], 5)
        self.assertIsNone(result['weekdays'][2]['average'])

    def test_repeated_dst_hour_is_combined_and_spring_hour_empty(self):
        result = self.habits([dict(date='2025-10-26', quantity=5, amounts={})],
                             [dict(occurred_at='2025-10-26T00:30:00+00:00', quantity=2),
                              dict(occurred_at='2025-10-26T01:30:00+00:00', quantity=3)], 'Europe/Paris')
        self.assertEqual(result['hourly'][2]['quantity'], 5)
        result = self.habits([dict(date='2025-03-30', quantity=2, amounts={})],
                             [dict(occurred_at='2025-03-30T00:30:00+00:00', quantity=1),
                              dict(occurred_at='2025-03-30T01:30:00+00:00', quantity=1)], 'Europe/Paris')
        self.assertEqual([result['hourly'][h]['quantity'] for h in (1, 2, 3)], [1, 0, 1])

    def test_weekdays_normalized_by_calendar_occurrences(self):
        from datetime import date, timedelta
        days = [dict(date=(date(2025, 1, 6)+timedelta(days=i)).isoformat(), quantity=8 if i == 0 else 0, amounts={}) for i in range(8)]
        result = self.habits(days)
        self.assertEqual(result['weekdays'][0]['days'], 2)
        self.assertEqual(result['weekdays'][0]['average'], 4)
        self.assertEqual(result['weekdays'][1]['average'], 0)

    def test_projection_excludes_today_and_keeps_currencies(self):
        result = self.habits([dict(date='2025-01-01', quantity=2, amounts={'EUR':1000000,'JPY':60000000}),
                             dict(date='2025-01-02', quantity=0, amounts={}),
                             dict(date='2025-01-03', quantity=100, amounts={'EUR':999000000})], today=True)
        self.assertEqual(result['projection'], dict(days=30, sample_days=2, quantity=30, costs={'EUR':15,'JPY':900}))
        empty = self.habits([dict(date='2025-01-03', quantity=0, amounts={})], today=True)
        self.assertIsNone(empty['projection']['quantity'])
        self.assertEqual(empty['projection']['costs'], {})
        self.assertEqual(sum(hour['share_percent'] for hour in empty['hourly']), 0)

    def test_trailing_average_window_and_historical_cost(self):
        daily = [dict(date=f'2025-01-{i+1:02}', quantity=7 if i == 0 else 0, amounts={'KWD':1234000} if i == 0 else {}) for i in range(8)]
        result = analyze(daily, [], 'EUR', None, None, False)
        self.assertEqual(result['trend'][0]['window_days'], 1)
        self.assertEqual(result['trend'][0]['quantity'], 7)
        self.assertEqual(result['trend'][0]['costs']['KWD'], 1.234)
        self.assertEqual(result['trend'][6]['quantity'], 1)
        self.assertEqual(result['trend'][7]['quantity'], 0)
        self.assertEqual(result['trend'][7]['costs']['KWD'], 0)
