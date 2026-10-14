from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import re
import smtplib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs

from server.app import create_app
from server.accounts import send_mail


class AdminAccountsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.config = dict(TESTING=True, DATABASE=self.tmp.name+'/db', ADMIN_USERNAME='admin', ADMIN_PASSWORD='admin-test-password')
        self.app = create_app(self.config); self.client = self.app.test_client()
        self.admin = self.login('admin','admin-test-password')
        self.client.post('/api/auth/register', json={'username':'alice','password':'alice-test-password'})
        self.user = self.login('alice','alice-test-password')
        self.sender = patch('server.accounts.send_mail').start();self.addCleanup(patch.stopall)
        self.smtp = dict(enabled=True,host='mail.example.com',port=587,security='starttls',username='mailer',password='mail-secret',sender='suuless@example.com',public_url='https://suuless.example.com')
        self.assertEqual(self.client.put('/api/admin/smtp', headers=self.admin, json=self.smtp).status_code,200)

    def login(self, username, password):
        r = self.client.post('/api/auth/login',json=dict(username=username,password=password))
        self.assertEqual(r.status_code,200,r.text)
        return {'Authorization':'Bearer '+r.json['token']}

    def secret(self):
        content = self.sender.call_args.args[3]
        url = re.search(r'https://\S+', content)[0]
        self.assertTrue(url.startswith('https://suuless.example.com/account#'))
        return parse_qs(urlsplit(url).fragment)['token'][0]

    def invite(self, email='invite@example.com'):
        r = self.client.post('/api/admin/invitations',headers=self.admin,json={'email':email,'language':'fr'})
        self.assertEqual(r.status_code,204,r.text)
        return self.secret()

    def complete(self, token, **data):
        return self.client.post('/api/auth/complete',json=dict(token=token,**data))

    def test_role_enforcement_and_language(self):
        for method,path in [('GET','/api/admin/users'),('PUT','/api/admin/smtp'),('POST','/api/admin/invitations'),('PUT','/api/admin/profile')]:
            self.assertEqual(self.client.open(path,method=method,headers=self.user,json={}).status_code,403)
        for path in ['/api/stats','/api/settings','/api/cigarettes','/api/tokens','/api/coaching/plan']:
            self.assertEqual(self.client.get(path,headers=self.admin).status_code,403)
        self.assertEqual(self.client.delete('/api/me',headers=self.admin,json={}).status_code,403)
        self.assertEqual(self.client.put('/api/admin/profile',headers=self.admin,json={'language':'ja'}).status_code,204)
        self.assertEqual(self.client.get('/api/me',headers=self.admin).json['language'],'ja')
        self.assertEqual(self.client.put('/api/admin/profile',headers=self.admin,json={'language':[]}).status_code,400)
        me=self.client.get('/api/me',headers=self.user).json
        self.assertEqual(me['role'],'user')
        self.assertNotIn('password_hash',self.client.get('/api/admin/users',headers=self.admin).text)

    def test_invitation_with_closed_registration_single_use_and_no_secret_storage(self):
        self.app.config['ALLOW_REGISTRATION']=False
        token=self.invite()
        with closing(sqlite3.connect(self.config['DATABASE'])) as db:
            self.assertEqual(db.execute('SELECT digest FROM account_links').fetchone()[0],hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(token,self.client.get('/api/admin/invitations',headers=self.admin).text)
        self.assertEqual(self.complete(token,username='invited',password='invited-test-password').status_code,200)
        self.assertEqual(self.complete(token,username='again',password='invited-test-password').status_code,400)
        auth=self.login('invited','invited-test-password')
        me=self.client.get('/api/me',headers=auth).json
        self.assertEqual((me['role'],me['email_verified'],me['language']),('user',True,'fr'))
        self.assertEqual(self.client.post('/api/auth/register',json={}).status_code,403)

    def test_invitation_revocation_reissue_expiration_and_concurrent_consumption(self):
        old=self.invite();new=self.invite()
        self.assertEqual(self.complete(old).status_code,400)
        invitation=self.client.get('/api/admin/invitations',headers=self.admin).json[0]
        self.client.delete('/api/admin/invitations/'+str(invitation['id']),headers=self.admin)
        self.assertEqual(self.complete(new).status_code,400)
        token=self.invite()
        with closing(sqlite3.connect(self.config['DATABASE'])) as db,db:
            db.execute("UPDATE account_links SET expires_at='2000-01-01'")
        self.assertEqual(self.complete(token).status_code,400)
        token=self.invite()
        def consume(_):
            return self.app.test_client().post('/api/auth/complete',json={'token':token,'username':'race','password':'race-long-password'}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(consume,range(2))),[200,400])

    def test_activation_no_session_until_email_verified(self):
        r=self.client.post('/api/auth/register',json={'username':'pending','password':'pending-test-password','email':'pending@example.com'})
        self.assertEqual(r.status_code,201);self.assertTrue(r.json['activation_required']);self.assertNotIn('token',r.json)
        secret=self.secret()
        self.assertEqual(self.client.post('/api/auth/login',json={'username':'pending','password':'pending-test-password'}).status_code,401)
        self.assertEqual(self.complete(secret).status_code,200)
        self.login('pending','pending-test-password')
        self.assertEqual(self.complete(secret).status_code,400)

    def test_reset_revokes_all_access_and_hides_existence(self):
        secret=self.invite();self.complete(secret,username='recover',password='recover-test-password')
        auth=self.login('recover','recover-test-password')
        key=self.client.post('/api/tokens',headers=auth,json={'name':'device'}).json['token']
        known=self.client.post('/api/auth/forgot-password',json={'email':'invite@example.com'})
        secret=self.secret()
        absent=self.client.post('/api/auth/forgot-password',json={'email':'absent@example.com'})
        self.assertEqual((known.status_code,known.json),(absent.status_code,absent.json))
        self.assertEqual(self.complete(secret,password='new-recovery-password').status_code,200)
        for headers in [auth,{'Authorization':'Bearer '+key}]:
            self.assertEqual(self.client.get('/api/me',headers=headers).status_code,401)
        self.login('recover','new-recovery-password')
        self.assertEqual(self.complete(secret,password='another-long-password').status_code,400)

    def test_disabled_pending_account_cannot_reactivate(self):
        self.client.post('/api/auth/register',json={'username':'pending','password':'pending-test-password','email':'pending@example.com'})
        secret=self.secret()
        uid=next(u['id'] for u in self.client.get('/api/admin/users',headers=self.admin).json if u['username']=='pending')
        self.client.patch('/api/admin/users/'+str(uid),headers=self.admin,json={'active':False})
        self.sender.reset_mock()
        self.client.post('/api/auth/resend-activation',json={'email':'pending@example.com'})
        self.sender.assert_not_called()
        self.assertEqual(self.complete(secret).status_code,400)
        self.assertEqual(self.client.patch('/api/admin/users/'+str(uid),headers=self.admin,json={'active':True}).status_code,204)
        self.assertEqual(self.complete(self.secret()).status_code,200)
        self.login('pending','pending-test-password')

    def test_disable_revokes_sessions_and_enable_preserves_data(self):
        uid=self.client.get('/api/me',headers=self.user).json['id']
        self.client.post('/api/cigarettes',headers=self.user,json={'quantity':3})
        self.assertEqual(self.client.patch('/api/admin/users/'+str(uid),headers=self.admin,json={'active':False}).status_code,204)
        self.assertEqual(self.client.get('/api/me',headers=self.user).status_code,401)
        self.assertEqual(self.client.patch('/api/admin/users/'+str(uid),headers=self.admin,json={'active':True}).status_code,204)
        auth=self.login('alice','alice-test-password')
        self.assertEqual(self.client.get('/api/stats',headers=auth).json['today']['quantity'],3)
        self.assertEqual(self.client.patch('/api/admin/users/1',headers=self.admin,json={'active':False}).status_code,403)

    def test_existing_account_email_and_failure_rollback(self):
        self.assertEqual(self.client.post('/api/account/email',headers=self.user,json={'email':'alice@example.com','password':'wrong'}).status_code,400)
        r=self.client.post('/api/account/email',headers=self.user,json={'email':'alice@example.com','password':'alice-test-password'})
        self.assertEqual(r.status_code,202)
        self.assertEqual(self.complete(self.secret()).status_code,200)
        self.assertTrue(self.client.get('/api/me',headers=self.user).json['email_verified'])
        self.sender.side_effect=smtplib.SMTPException('private error mail-secret')
        r=self.client.post('/api/admin/invitations',headers=self.admin,json={'email':'fail@example.com'})
        self.assertEqual(r.status_code,502);self.assertNotIn('mail-secret',r.text)
        self.assertEqual(self.client.get('/api/admin/invitations',headers=self.admin).json,[])
        r=self.client.post('/api/auth/register',json={'username':'failed','password':'failed-test-password','email':'fail@example.com'})
        self.assertEqual(r.status_code,502)
        self.assertNotIn('failed',[u['username'] for u in self.client.get('/api/admin/users',headers=self.admin).json])
        r=self.client.post('/api/auth/forgot-password',json={'email':'alice@example.com'})
        self.assertEqual(r.status_code,202)

    def test_smtp_password_redaction_and_validation(self):
        result=self.client.get('/api/admin/smtp',headers=self.admin)
        self.assertNotIn('mail-secret',result.text);self.assertNotIn('password',result.json)
        self.assertTrue(result.json['password_set'])
        self.assertEqual(self.client.put('/api/admin/smtp',headers=self.admin,json={'host':'new.example.com'}).status_code,200)
        self.client.post('/api/admin/smtp/test',headers=self.admin,json={'email':'test@example.com'})
        self.assertEqual(self.sender.call_args.args[0]['password'],'mail-secret')
        for invalid in [{'port':True},{'security':'bad'},{'public_url':'https://good.example@bad.example/'},{'sender':'x@example.com\r\nBcc:bad@example.com'},{'host':[]},{'enabled':'true'}]:
            self.assertEqual(self.client.put('/api/admin/smtp',headers=self.admin,json=invalid).status_code,400,invalid)

    def test_legacy_personal_key_cannot_administer(self):
        secret = 'pre-existing-personal-key'
        with closing(sqlite3.connect(self.config['DATABASE'])) as db, db:
            db.execute("INSERT INTO tokens(user_id,digest,name,expires_at,kind) VALUES(1,?,'Old key','2099-01-01','api')", (hashlib.sha256(secret.encode()).hexdigest(),))
        self.assertEqual(self.client.get('/api/admin/users', headers={'Authorization':'Bearer '+secret}).status_code,403)

    def test_role_migration_preserves_accounts_and_passwords(self):
        from server.app import SCHEMA
        from werkzeug.security import generate_password_hash
        path = self.tmp.name+'/old-db'
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript(SCHEMA)
            for uid, name in [(5,'alice'),(9,'admin')]:
                db.execute('INSERT INTO users(id,username,password_hash) VALUES(?,?,?)', (uid,name,generate_password_hash('previous-test-password')))
        config = dict(self.config,DATABASE=path,ADMIN_USERNAME='operator')
        migrated = create_app(config)
        client = migrated.test_client()
        result = client.post('/api/auth/login',json={'username':'operator','password':'admin-test-password'})
        self.assertEqual(result.status_code,200)
        me = client.get('/api/me',headers={'Authorization':'Bearer '+result.json['token']}).json
        self.assertEqual((me['id'],me['role']),(10,'admin'))
        create_app(dict(config,ADMIN_USERNAME='alice'))
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute("SELECT role,active FROM users WHERE username='alice'").fetchone(),('user',1))

    def test_cli_creates_dedicated_admin_and_does_not_replace_existing(self):
        runner=self.app.test_cli_runner()
        result=runner.invoke(args=['create-admin','--username','operator','--password','operator-test-password'])
        self.assertEqual(result.exit_code,0,result.output)
        self.assertEqual(self.client.get('/api/me',headers=self.login('operator','operator-test-password')).json['role'],'admin')
        result=runner.invoke(args=['create-admin','--username','alice','--password','operator-test-password'])
        self.assertNotEqual(result.exit_code,0)
        self.login('alice','alice-test-password')


class SMTPTransportTest(unittest.TestCase):
    def test_tls_and_starttls_verify_certificates(self):
        config=dict(host='mail.example.com',port=587,security='starttls',username='user',password='secret',sender='sender@example.com')
        with patch('server.accounts.smtplib.SMTP') as factory:
            send_mail(config,'to@example.com','Test','Content')
            smtp=factory.return_value.__enter__.return_value
            self.assertTrue(smtp.starttls.call_args.kwargs['context'].check_hostname)
            smtp.login.assert_called_once_with('user','secret')
            smtp.send_message.assert_called_once()
        with patch('server.accounts.smtplib.SMTP_SSL') as factory:
            send_mail(dict(config,security='tls'),'to@example.com','Test','Content')
            self.assertTrue(factory.call_args.kwargs['context'].check_hostname)
            factory.return_value.__enter__.return_value.starttls.assert_not_called()
