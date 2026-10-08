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
