"""Privacy and accounting boundaries for user-shared consumption reports."""
import tempfile
import unittest
from server.app import create_app


class ConsumptionReportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = create_app({'TESTING': True, 'DATABASE': self.temp.name + '/db'})
        self.client = self.app.test_client()
        self.auth = self.register('private-alice')

    def register(self, name):
        result = self.client.post('/api/auth/register', json={'username': name, 'password': 'long-test-password'})
        return {'Authorization': 'Bearer ' + result.json['token']}

    def add(self, when, quantity=2, auth=None):
        result = self.client.post('/api/cigarettes', headers=auth or self.auth,
                                  json={'occurred_at': when, 'quantity': quantity})
        self.assertEqual(result.status_code, 201)

    def report(self, query='start=2025-01-01&end=2025-01-03'):
        return self.client.get('/api/report.html?' + query, headers=self.auth)

    def test_private_localized_report_and_historical_currencies(self):
        self.add('2025-01-01T12:00:00Z')
        self.client.put('/api/settings', headers=self.auth, json={'currency': 'JPY', 'pack_price': '600', 'language': 'fr'})
        self.add('2025-01-03T12:00:00Z')
        other = self.register('private-bob')
        self.add('2025-01-02T12:00:00Z', 199, other)
        result = self.report()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.mimetype, 'text/html')
        self.assertEqual(result.headers['Cache-Control'], 'no-store')
        self.assertIn('attachment;', result.headers['Content-Disposition'])
        for text in ('Rapport de consommation', '1.20 EUR + 60 JPY', 'Aucune saisie', '<td>4</td>', 'Europe/Paris'):
            self.assertIn(text, result.text)
        for text in ('private-alice', 'private-bob', self.auth['Authorization'], '<td>199</td>', '<script', 'src='):
            self.assertNotIn(text, result.text)

    def test_timezone_boundaries_and_empty_days(self):
        self.client.put('/api/settings', headers=self.auth, json={'timezone': 'Asia/Tokyo'})
        self.add('2024-12-31T14:59:59Z', 99)
        self.add('2024-12-31T15:00:00Z', 3)
        self.add('2025-01-01T15:00:00Z', 88)
        result = self.report('start=2025-01-01&end=2025-01-01')
        self.assertIn('<td>3</td>', result.text)
        self.assertNotIn('<td>99</td>', result.text)
        self.assertNotIn('<td>88</td>', result.text)
        empty = self.report('start=2024-01-01&end=2024-01-02').text
        self.assertIn('No entries', empty)
        self.assertNotIn('NaN', empty)

    def test_auth_dates_and_all_languages(self):
        self.assertEqual(self.client.get('/api/report.html').status_code, 401)
        for query in ('start=invalid', 'start=2025-01-02&end=2025-01-01', 'start=2020-01-01&end=2025-01-01'):
            self.assertEqual(self.report(query).status_code, 400)
        for language, title in [('en', 'Consumption report'), ('fr', 'Rapport de consommation'), ('ja', '喫煙記録レポート')]:
            self.client.put('/api/settings', headers=self.auth, json={'language': language})
            self.assertIn(title, self.report().text)
