"""Check the documented HTTP contract against Flask routes and real responses."""
import copy
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import yaml
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate
from server.app import create_app

SPEC = yaml.safe_load((Path(__file__).resolve().parents[1] / 'docs/api/openapi.yaml').read_text())


def expanded(schema):
    """Resolve this contract's local, nonrecursive references for JSON Schema."""
    if isinstance(schema, list):
        return [expanded(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    if '$ref' in schema:
        target = SPEC
        for part in schema['$ref'].removeprefix('#/').split('/'):
            target = target[part]
        return expanded({**target, **{k: v for k, v in schema.items() if k != '$ref'}})
    return {key: expanded(value) for key, value in schema.items()}


class OpenAPIContractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = create_app({'TESTING': True, 'DATABASE': self.tmp.name + '/db'})
        self.client = self.app.test_client()
        clock = patch('server.app.now', return_value=datetime(2026, 10, 14, 12, tzinfo=timezone.utc))
        clock.start()
        self.addCleanup(clock.stop)
        response = self.client.post('/api/auth/register', json={
            'username': 'contract-user', 'password': 'contract-test-password', 'timezone': 'UTC'})
        self.check(response, '/api/auth/register', 'post', 201)
        self.headers = {'Authorization': 'Bearer ' + response.json['token']}

    def check(self, response, path, method='get', status=200):
        self.assertEqual(response.status_code, status, response.get_data(as_text=True))
        documented = expanded(SPEC['paths'][path][method]['responses'][str(status)])
        content = documented.get('content', {})
        if status == 204:
            self.assertEqual(response.data, b'')
        elif content:
            self.assertIn(response.mimetype, content)
            value = response.json if response.is_json else response.get_data(as_text=True)
            Draft202012Validator(content[response.mimetype]['schema'],
                                 format_checker=Draft202012Validator.FORMAT_CHECKER).validate(value)
        return response.json if response.is_json else None

    def request(self, method, url, path=None, status=200, **kwargs):
        return self.check(self.client.open(url, method=method, headers=self.headers, **kwargs),
                          path or url.split('?')[0], method.lower(), status)

    def test_specification_and_route_coverage(self):
        validate(copy.deepcopy(SPEC))
        actual = set()
        for rule in self.app.url_map.iter_rules():
            if rule.rule.startswith('/api/') or rule.rule == '/healthz':
                path = re.sub(r'<(?:[^:>]+:)?([^>]+)>', r'{\1}', rule.rule)
                actual.update((path, method.lower()) for method in rule.methods - {'HEAD', 'OPTIONS'})
        documented = {(path, method) for path, item in SPEC['paths'].items()
                      for method in item if method in {'get', 'put', 'post', 'delete', 'patch'}}
        self.assertEqual(actual, documented)
        public = {'/healthz', '/api/config', '/api/auth/login', '/api/auth/register', '/api/auth/forgot-password', '/api/auth/resend-activation', '/api/auth/complete'}
        for path, method in documented:
            security = SPEC['paths'][path][method].get('security', SPEC['security'])
            self.assertEqual(security, [] if path in public else [{'bearerAuth': []}])

    def test_account_entries_statistics_and_errors(self):
        for path in ('/healthz', '/api/config', '/api/me', '/api/settings', '/api/tokens',
                     '/api/cigarettes', '/api/stats', '/api/sync/config', '/api/push'):
            self.request('GET', path)
        self.request('POST', '/api/auth/login', json={'username': 'contract-user', 'password': 'contract-test-password'})
        token = self.request('POST', '/api/tokens', status=201, json={'name': 'Test client'})
        self.request('DELETE', '/api/tokens/' + str(token['id']), '/api/tokens/{token_id}', status=204)
        entry = self.request('POST', '/api/cigarettes', status=201, json={'occurred_at': '2026-10-13T12:00:00Z', 'quantity': 2})
        self.request('PUT', '/api/settings', json={'currency': 'JPY', 'pack_price': '600'})
        self.request('POST', '/api/cigarettes', status=201, json={})
        for path in ('/api/stats', '/api/cigarettes', '/api/export.csv', '/api/report.html'):
            self.request('GET', path)
        self.request('GET', '/api/stats?start=2000-01-01&end=2000-01-01')
        self.request('PATCH', f"/api/cigarettes/{entry['id']}/context", '/api/cigarettes/{entry_id}/context', json={'trigger': 'coffee'})
        self.request('DELETE', f"/api/cigarettes/{entry['id']}", '/api/cigarettes/{entry_id}', status=204)
        self.request('DELETE', '/api/cigarettes/99999', '/api/cigarettes/{entry_id}', status=404)
        self.request('PUT', '/api/settings', status=400, json={'pack_size': 0})
        self.check(self.client.get('/api/me'), '/api/me', status=401)
        self.request('DELETE', '/api/push', status=204)
        self.request('POST', '/api/auth/logout', status=204)

    def test_coaching_null_and_populated_variants(self):
        self.request('GET', '/api/coaching')
        self.request('PUT', '/api/coaching/plan', json={'version': 0, 'mode': 'quit', 'quit_date': '2026-10-14'})
        self.request('PUT', '/api/coaching/plan', status=409, json={'version': 0})
        self.request('POST', '/api/cigarettes', status=201, json={'occurred_at': '2026-10-12T12:00:00Z'})
        self.request('POST', '/api/coaching/baseline', status=201, json={'start': '2026-10-12', 'end': '2026-10-12'})
        self.request('GET', '/api/coaching')
        self.request('PUT', '/api/check-ins/2026-10-13', '/api/check-ins/{day}', json={'quantity': 0})
        self.headers['Idempotency-Key'] = 'contract-craving'
        craving = self.request('POST', '/api/cravings', status=201, json={'trigger': 'stress'})
        self.request('POST', '/api/cravings', json={})
        self.request('GET', '/api/coaching')
        self.request('PUT', f"/api/cravings/{craving['id']}", '/api/cravings/{craving_id}', json={'outcome': 'smoked'})
        self.request('GET', '/api/coaching')
        self.request('GET', '/api/coaching/export.csv')
        self.request('DELETE', '/api/check-ins/2026-10-13', '/api/check-ins/{day}', status=204)

    def test_contract_rejects_missing_fields_and_invalid_inputs(self):
        entry_schema = expanded({'$ref': '#/components/schemas/Entry'})
        self.assertFalse(Draft202012Validator(entry_schema).is_valid({'id': 1}))
        create_schema = expanded({'$ref': '#/components/schemas/EntryCreate'})
        for payload in ({'quantity': 0}, {'quantity': True},
                        {'occurred_at': '2026-10-13T12:00:00Z', 'occurred_at_local': '2026-10-13T12:00:00'}):
            self.assertFalse(Draft202012Validator(create_schema).is_valid(payload))
