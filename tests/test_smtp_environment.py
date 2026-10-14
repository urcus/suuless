from contextlib import closing
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from server.app import create_app


class SMTPEnvironmentTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.config = dict(TESTING=True, DATABASE=tmp.name+'/db', ADMIN_USERNAME='admin', ADMIN_PASSWORD='admin-test-password')
        self.env = dict(SMTP_ENABLED='true',SMTP_HOST='smtp.example.com',SMTP_PORT='465',SMTP_SECURITY='tls',
                        SMTP_USERNAME='mailer',SMTP_PASSWORD='environment-mail-secret',SMTP_FROM='suuless@example.com',
                        SMTP_PUBLIC_URL='https://suuless.example.com/')
        clean = {k:v for k,v in os.environ.items() if not k.startswith('SMTP_')}
        self.environment = patch.dict(os.environ, clean, clear=True);self.environment.start();self.addCleanup(self.environment.stop)

    def start(self, env):
        with patch.dict(os.environ, env):
            app = create_app(self.config)
        client = app.test_client()
        response = client.post('/api/auth/login',json={'username':'admin','password':'admin-test-password'})
        headers = {'Authorization':'Bearer '+response.json['token']}
        return app,client,headers

    def test_environment_config_drives_mail_and_is_not_persisted(self):
        app,client,headers = self.start(self.env)
        config = client.get('/api/admin/smtp',headers=headers)
        self.assertTrue(config.json['managed_by_environment']);self.assertTrue(config.json['password_set'])
        self.assertEqual(config.json['public_url'],'https://suuless.example.com')
        self.assertNotIn('environment-mail-secret',config.text)
        self.assertTrue(client.get('/api/config').json['email_required'])
        with patch('server.accounts.send_mail') as send:
            response = client.post('/api/admin/invitations',headers=headers,json={'email':'invite@example.com'})
            self.assertEqual(response.status_code,204,response.text)
            sent = send.call_args.args
            self.assertEqual(sent[0]['password'],self.env['SMTP_PASSWORD'])
            self.assertEqual((sent[0]['port'],sent[0]['security']),(465,'tls'))
            self.assertIn('https://suuless.example.com/account#',sent[3])
        with closing(sqlite3.connect(self.config['DATABASE'])) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM mail_settings').fetchone()[0],0)
        self.assertEqual(client.put('/api/admin/smtp',headers=headers,json={'enabled':False}).status_code,409)

    def test_database_preserved_and_restored_when_environment_removed(self):
        _,client,headers = self.start({})
        saved = dict(enabled=True,host='stored.example.com',port=587,security='starttls',username='',password='stored-secret',sender='stored@example.com',public_url='https://stored.example.com')
        self.assertEqual(client.put('/api/admin/smtp',headers=headers,json=saved).status_code,200)
        _,client,headers = self.start(self.env)
        self.assertEqual(client.get('/api/admin/smtp',headers=headers).json['host'],'smtp.example.com')
        _,client,headers = self.start({'SMTP_ENABLED':'false'})
        self.assertFalse(client.get('/api/config').json['email_required'])
        self.assertTrue(client.get('/api/admin/smtp',headers=headers).json['managed_by_environment'])
        with closing(sqlite3.connect(self.config['DATABASE'])) as db:
            self.assertEqual(json.loads(db.execute('SELECT config FROM mail_settings').fetchone()[0]),saved)
        _,client,headers = self.start({'SMTP_ENABLED':''})
        config = client.get('/api/admin/smtp',headers=headers).json
        self.assertFalse(config['managed_by_environment']);self.assertEqual(config['host'],'stored.example.com')

    def test_defaults_and_explicit_mode_selection(self):
        env = {k:v for k,v in self.env.items() if k not in ('SMTP_PORT','SMTP_SECURITY','SMTP_USERNAME','SMTP_PASSWORD')}
        app,client,headers = self.start(env)
        config = client.get('/api/admin/smtp',headers=headers).json
        self.assertEqual((config['port'],config['security'],config['username']),(587,'starttls',''))
        self.assertFalse(config['password_set'])
        _,client,headers = self.start({'SMTP_HOST':'ignored.example.com'})
        self.assertFalse(client.get('/api/admin/smtp',headers=headers).json['managed_by_environment'])
        self.assertFalse(client.get('/api/config').json['email_required'])

    def test_invalid_settings_fail_startup_without_disclosing_secrets(self):
        for override in [{'SMTP_ENABLED':'yes'},{'SMTP_PORT':'invalid'},{'SMTP_PORT':'0'},
                         {'SMTP_HOST':''},{'SMTP_FROM':'bad'},{'SMTP_PUBLIC_URL':'https://bad.example:invalid'},
                         {'SMTP_PUBLIC_URL':'https://user:private@bad.example'}, {'SMTP_SECURITY':'invalid'}]:
            with self.subTest(override=override),patch.dict(os.environ,{**self.env,**override}):
                with self.assertRaises(ValueError) as error:
                    create_app(self.config)
                self.assertNotIn('environment-mail-secret',str(error.exception))
                self.assertNotIn('private@',str(error.exception))
