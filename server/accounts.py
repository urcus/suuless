"""Administration and single-use email account workflows."""
import hashlib
import json
import logging
import os
import re
import secrets
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from urllib.parse import urlsplit

from flask.logging import default_handler

from flask import current_app, g, jsonify, request, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

from .international import LANGUAGES, translate

MAIL_LOG = logging.getLogger('suuless.smtp')
MAIL_LOG.setLevel(logging.INFO)
if not MAIL_LOG.handlers:
    MAIL_LOG.addHandler(default_handler)
MAIL_LOG.propagate = False

SCHEMA = '''
CREATE TABLE IF NOT EXISTS mail_settings (id INTEGER PRIMARY KEY CHECK(id=1), config TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS account_links (
 id INTEGER PRIMARY KEY, digest TEXT UNIQUE NOT NULL, purpose TEXT NOT NULL,
 email TEXT NOT NULL, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
 language TEXT NOT NULL, expires_at TEXT NOT NULL
);
'''
PUBLIC_PATHS = {'/api/auth/forgot-password', '/api/auth/resend-activation', '/api/auth/complete'}


def email_address(value):
    if not isinstance(value, str) or len(value) > 254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", value):
        return None
    return value.lower()


def validate_mail_config(config):
    if not isinstance(config.get('enabled'), bool):
        raise ValueError('Invalid SMTP configuration')
    if not config['enabled']:
        return
    for key in ('host','username','password','sender','public_url','security'):
        if not isinstance(config.get(key), str) or len(config[key]) > 2048 or '\r' in config[key] or '\n' in config[key]:
            raise ValueError('Invalid SMTP configuration')
    try:
        url = urlsplit(config['public_url'])
        url.port  # Validate malformed ports as well as host syntax.
    except ValueError:
        raise ValueError('Invalid SMTP public URL') from None
    if (url.scheme not in ('http','https') or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path not in ('','/')
            or not email_address(config['sender']) or not config['host'].strip()
            or type(config.get('port')) is not int or not 1 <= config['port'] <= 65535
            or config['security'] not in ('tls','starttls','plain')):
        raise ValueError('Invalid SMTP configuration')
    config['public_url'] = config['public_url'].rstrip('/')


def environment_mail_config():
    """An explicit SMTP_ENABLED selects environment ownership, without DB writes."""
    enabled = os.environ.get('SMTP_ENABLED', '').strip().lower()
    if not enabled:
        return None
    if enabled not in ('true', 'false'):
        raise ValueError('SMTP_ENABLED must be true or false')
    try:
        port = int(os.environ.get('SMTP_PORT', '') or '587')
    except ValueError:
        raise ValueError('SMTP_PORT must be an integer between 1 and 65535') from None
    config = dict(enabled=enabled == 'true', host=os.environ.get('SMTP_HOST', ''),
                  port=port, security=os.environ.get('SMTP_SECURITY', '') or 'starttls',
                  username=os.environ.get('SMTP_USERNAME', ''), password=os.environ.get('SMTP_PASSWORD', ''),
                  sender=os.environ.get('SMTP_FROM', ''), public_url=os.environ.get('SMTP_PUBLIC_URL', ''))
    validate_mail_config(config)
    return config


def mail_config(db):
    config = current_app.config.get('SMTP_ENV_CONFIG')
    if config is not None:
        return dict(config)
    row = db.execute('SELECT config FROM mail_settings WHERE id=1').fetchone()
    return json.loads(row[0]) if row else {}


def send_mail(config, recipient, subject, content):
    message = EmailMessage()
    message['From'] = config['sender']
    message['To'] = recipient
    message['Subject'] = subject
    message.set_content(content)
    message['Date'] = formatdate(localtime=False, usegmt=True)
    message['Message-ID'] = make_msgid(domain=config['sender'].rsplit('@', 1)[-1])
    event_id = secrets.token_hex(8)
    stage = 'connect'
    MAIL_LOG.info('SMTP submission started event=%s', event_id)
    try:
        context = ssl.create_default_context()
        factory = smtplib.SMTP_SSL if config['security'] == 'tls' else smtplib.SMTP
        options = {'timeout': 10}
        if config['security'] == 'tls':
            options['context'] = context
        with factory(config['host'], config['port'], **options) as smtp:
            if config['security'] == 'starttls':
                stage = 'starttls'
                smtp.starttls(context=context)
            if config['username']:
                stage = 'authenticate'
                smtp.login(config['username'], config['password'])
            stage = 'submit'
            refused = smtp.send_message(message)
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
            MAIL_LOG.info('SMTP submission accepted event=%s delivery=unconfirmed', event_id)
            stage = 'disconnect'
    except (OSError, smtplib.SMTPException) as error:
        code = getattr(error, 'smtp_code', None)
        # SMTP responses can contain addresses, credentials or message content.
        # Log only the stage, exception class and numeric response code.
        MAIL_LOG.warning('SMTP submission failed event=%s stage=%s error=%s smtp_code=%s',
                         event_id, stage, type(error).__name__, code if isinstance(code, int) else 'unavailable')
        raise


def register_routes(app, db, body, fail, now, stamp, auth_limit):
    def deliver(email, purpose, user_id=None, locale='en'):
        config = mail_config(db())
        if not config.get('enabled'):
            fail('mail_unavailable', 503)
        secret = secrets.token_urlsafe(32)
        expiry = stamp(now() + timedelta(hours=1 if purpose == 'reset' else 48))
        db().execute('DELETE FROM account_links WHERE email=? AND purpose=?', (email, purpose))
        db().execute('INSERT INTO account_links(digest,purpose,email,user_id,language,expires_at) VALUES(?,?,?,?,?,?)',
                     (hashlib.sha256(secret.encode()).hexdigest(), purpose, email, user_id, locale, expiry))
        url = config['public_url'] + '/account#token=' + secret + '&purpose=' + purpose
        messages = {
            'en': ('SuuLess · Your account', {'invite':'You are invited to SuuLess.', 'activate':'Activate your SuuLess account.', 'reset':'Reset your SuuLess password.'}, 'Open this link within {hours} hours. It can be used only once. If you did not request this, ignore this email.'),
            'fr': ('SuuLess · Votre compte', {'invite':'Vous êtes invité sur SuuLess.', 'activate':'Activez votre compte SuuLess.', 'reset':'Réinitialisez votre mot de passe SuuLess.'}, 'Ouvrez ce lien sous {hours} heures. Il est à usage unique. Si vous n’êtes pas à l’origine de cette demande, ignorez ce message.'),
            'ja': ('スーレス · アカウント', {'invite':'スーレスへの招待です。', 'activate':'スーレスのアカウントを有効にしてください。', 'reset':'スーレスのパスワードを再設定してください。'}, '{hours}時間以内にリンクを開いてください。リンクは一度だけ使用できます。心当たりがない場合は、このメールを無視してください。'),
        }
        subject, introductions, note = messages[locale]
        try:
            send_mail(config, email, subject, introductions[purpose]+'\n\n'+url+'\n\n'+note.format(hours=1 if purpose == 'reset' else 48))
        except (OSError, smtplib.SMTPException):
            fail('mail_failed', 502)

    @app.get('/admin')
    def admin_page():
        return send_from_directory(app.static_folder, 'admin.html')

    @app.get('/account')
    def account_page():
        return send_from_directory(app.static_folder, 'account.html')

    @app.post('/api/account/email')
    def set_email():
        auth_limit()
        data = body()
        email, password = email_address(data.get('email')), data.get('password')
        if not email:
            fail('invalid_email')
        if not isinstance(password, str) or len(password) > 256 or not check_password_hash(g.user['password_hash'], password):
            fail('invalid_credentials', 400)
        with db():
            db().execute('BEGIN IMMEDIATE')
            if db().execute('SELECT 1 FROM users WHERE email=? AND id<>?', (email, g.user['id'])).fetchone():
                fail('email_taken', 409)
            db().execute('UPDATE users SET email=?,email_verified=0 WHERE id=?', (email, g.user['id']))
            db().execute('DELETE FROM account_links WHERE user_id=?', (g.user['id'],))
            deliver(email, 'activate', g.user['id'], g.user['language'])
        return jsonify(message=translate('email_requested')), 202

    @app.get('/api/admin/users')
    def admin_users():
        return jsonify([dict(row) for row in db().execute('SELECT id,username,email,role,active,suspended,email_verified,language FROM users ORDER BY id')])

    @app.patch('/api/admin/users/<int:user_id>')
    def admin_user_update(user_id):
        data = body()
        if set(data) != {'active'} or type(data['active']) is not bool:
            fail('invalid_input')
        with db():
            db().execute('BEGIN IMMEDIATE')
            user = db().execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
            if not user:
                fail('not_found', 404)
            if user['role'] == 'admin':
                fail('admin_protected', 403)
            # Pending email verification cannot be bypassed by an administrator.
            pending = bool(user['email'] and not user['email_verified'])
            if data['active'] and pending:
                deliver(user['email'], 'activate', user_id, user['language'])
            db().execute('UPDATE users SET active=?,suspended=? WHERE id=?', (int(data['active'] and not pending), int(not data['active']), user_id))
            if not data['active']:
                db().execute('DELETE FROM tokens WHERE user_id=?', (user_id,))
                db().execute('DELETE FROM account_links WHERE user_id=?', (user_id,))
        return '', 204

    @app.put('/api/admin/profile')
    def admin_profile():
        data = body()
        if set(data) != {'language'} or not isinstance(data['language'], str) or data['language'] not in LANGUAGES:
            fail('invalid_language')
        with db():
            db().execute('UPDATE users SET language=? WHERE id=?', (data['language'], g.user['id']))
        return '', 204

    @app.route('/api/admin/smtp', methods=['GET', 'PUT'])
    def admin_smtp():
        config = mail_config(db())
        if request.method == 'PUT':
            if app.config.get('SMTP_ENV_CONFIG') is not None:
                fail('smtp_environment_managed', 409)
            data = body()
            allowed = {'enabled','host','port','security','username','password','sender','public_url'}
            if set(data) - allowed:
                fail('invalid_input')
            config.update(data)
            try:
                validate_mail_config(config)
            except ValueError:
                fail('invalid_input')
            with db():
                db().execute('INSERT INTO mail_settings VALUES(1,?) ON CONFLICT(id) DO UPDATE SET config=excluded.config', (json.dumps(config),))
        return jsonify({**{k:v for k,v in config.items() if k != 'password'}, 'password_set':bool(config.get('password')), 'managed_by_environment':app.config.get('SMTP_ENV_CONFIG') is not None})

    @app.post('/api/admin/smtp/test')
    def admin_smtp_test():
        auth_limit()
        email = email_address(body().get('email'))
        if not email:
            fail('invalid_email')
        config = mail_config(db())
        if not config.get('enabled'):
            fail('mail_unavailable', 503)
        try:
            send_mail(config, email, 'SuuLess · SMTP', 'SuuLess SMTP test / Test SMTP / SMTP テスト')
        except (OSError, smtplib.SMTPException):
            fail('mail_failed', 502)
        return '', 204

    @app.route('/api/admin/invitations', methods=['GET', 'POST'])
    def admin_invitations():
        if request.method == 'GET':
            return jsonify([dict(row) for row in db().execute("SELECT id,email,language,expires_at FROM account_links WHERE purpose='invite' AND expires_at>? ORDER BY id DESC", (stamp(now()),))])
        auth_limit()
        data = body()
        email, locale = email_address(data.get('email')), data.get('language', g.user['language'])
        if not email or not isinstance(locale, str) or locale not in LANGUAGES:
            fail('invalid_email')
        with db():
            db().execute('BEGIN IMMEDIATE')
            if db().execute('SELECT 1 FROM users WHERE email=?', (email,)).fetchone():
                fail('email_taken', 409)
            deliver(email, 'invite', locale=locale)
        return '', 204

    @app.delete('/api/admin/invitations/<int:invitation_id>')
    def cancel_invitation(invitation_id):
        with db():
            db().execute("DELETE FROM account_links WHERE id=? AND purpose='invite'", (invitation_id,))
        return '', 204

    @app.post('/api/auth/forgot-password')
    @app.post('/api/auth/resend-activation')
    def request_email():
        auth_limit()
        email = email_address(body().get('email'))
        # Identical response for absent, ineligible and eligible accounts.
        user = db().execute('SELECT * FROM users WHERE email=?', (email,)).fetchone() if email else None
        purpose = 'reset' if request.path.endswith('forgot-password') else 'activate'
        eligible = user and not user['suspended'] and ((purpose == 'reset' and user['active'] and user['email_verified'])
                             or (purpose == 'activate' and not user['email_verified']))
        if eligible and mail_config(db()).get('enabled'):
            try:
                with db():
                    db().execute('BEGIN IMMEDIATE')
                    deliver(email, purpose, user['id'], user['language'])
            except Exception as exc:
                # Do not expose account existence or SMTP credentials in errors/logs.
                from werkzeug.exceptions import HTTPException
                if not isinstance(exc, HTTPException) or exc.code != 502:
                    raise
                app.logger.warning('Account email delivery failed')
        return jsonify(message=translate('email_requested')), 202

    @app.post('/api/auth/complete')
    def complete_email():
        auth_limit()
        data = body()
        secret = data.get('token')
        if not isinstance(secret, str) or not 20 <= len(secret) <= 200:
            fail('invalid_account_link')
        with db():
            db().execute('BEGIN IMMEDIATE')
            link = db().execute('SELECT * FROM account_links WHERE digest=? AND expires_at>?',
                                (hashlib.sha256(secret.encode()).hexdigest(), stamp(now()))).fetchone()
            if not link:
                fail('invalid_account_link')
            purpose, user_id = link['purpose'], link['user_id']
            if purpose in ('invite','reset'):
                password = data.get('password')
                if not isinstance(password, str) or not 12 <= len(password) <= 256:
                    fail('invalid_password')
            if purpose == 'invite':
                username = data.get('username')
                if not isinstance(username, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{3,40}', username):
                    fail('invalid_username')
                if db().execute('SELECT 1 FROM users WHERE username=? OR email=?', (username.lower(), link['email'])).fetchone():
                    fail('username_taken', 409)
                user_id = db().execute('UPDATE account_sequence SET last_id=last_id+1 WHERE id=1 RETURNING last_id').fetchone()[0]
                db().execute('INSERT INTO users(id,username,password_hash,email,email_verified,language) VALUES(?,?,?,?,1,?)',
                             (user_id, username.lower(), generate_password_hash(password), link['email'], link['language']))
            elif purpose == 'activate':
                if db().execute('SELECT suspended FROM users WHERE id=?', (user_id,)).fetchone()[0]:
                    fail('invalid_account_link')
                db().execute('UPDATE users SET active=1,email_verified=1 WHERE id=?', (user_id,))
            else:
                user = db().execute('SELECT active,email_verified FROM users WHERE id=?', (user_id,)).fetchone()
                if not user or not user['active'] or not user['email_verified']:
                    fail('invalid_account_link')
                db().execute('UPDATE users SET password_hash=? WHERE id=?', (generate_password_hash(password), user_id))
                db().execute('DELETE FROM tokens WHERE user_id=?', (user_id,))
            db().execute('DELETE FROM account_links WHERE id=? OR user_id=?', (link['id'], user_id))
        return jsonify(message=translate('account_link_completed'))

    return deliver
