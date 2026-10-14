"""SuuLess: one SQLite database, strictly user-scoped resources."""
import click
from contextlib import closing
import csv
import hashlib
import io
import os
import re
import secrets
import sqlite3
import threading
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from babel.numbers import get_currency_precision
from pathlib import Path
from .timezones import (VALID_TIMEZONES, ALIASES, TZDATA_VERSION, get_zone,
                        canonical_timezone, timezone_catalog, timezone_info)

from .accounts import SCHEMA as ACCOUNT_SCHEMA, PUBLIC_PATHS, register_routes as register_account_routes, mail_config, email_address, environment_mail_config

from .sync import SCHEMA as SYNC_SCHEMA, events
from .analysis import analyze, habits
from .coaching import (SCHEMA as COACHING_SCHEMA, TRIGGERS, invalidate_checkins,
                       reminder_preferences, register_routes, plan_for, goal_for)
from .push import SCHEMA as PUSH_SCHEMA, queue_refresh, topic_for

from flask import Flask, Response, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from .international import (LANGUAGES, CURRENCIES, TIMEZONES, language, translate,
                            currency_catalog, price_micros, price_string, money, cost_summary)

UTC = timezone.utc
SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
 pack_price_cents INTEGER NOT NULL DEFAULT 1200, pack_size INTEGER NOT NULL DEFAULT 20,
 timezone TEXT NOT NULL DEFAULT 'Europe/Paris', daily_target INTEGER NOT NULL DEFAULT 10
);
CREATE TABLE IF NOT EXISTS account_sequence (
 id INTEGER PRIMARY KEY CHECK(id=1), last_id INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS installation_state (
 id INTEGER PRIMARY KEY CHECK(id=1), initial_account_handled INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS tokens (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 digest TEXT UNIQUE NOT NULL, name TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cigarettes (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 occurred_at TEXT NOT NULL, quantity INTEGER NOT NULL,
 unit_cost_micros INTEGER NOT NULL, source TEXT NOT NULL,
 idempotency_key TEXT, UNIQUE(user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS cigarettes_user_date ON cigarettes(user_id, occurred_at);
CREATE TABLE IF NOT EXISTS auth_attempts (address TEXT NOT NULL, attempted_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS auth_attempts_date ON auth_attempts(attempted_at);
"""


def now():
    return datetime.now(UTC)


def stamp(dt):
    return dt.astimezone(UTC).isoformat(timespec='microseconds')


def fail(code, status=400, *args):
    from flask import abort
    g.error_code = code
    abort(status, description=translate(code, *args))


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        fail('invalid_integer', 400, translate(label), low, high)
    return value


def body():
    data = request.get_json()
    if not isinstance(data, dict):
        fail('json_object')
    return data


def initialize_account(conn, config):
    """Run inside the startup transaction, once per installation, across workers."""
    if conn.execute('SELECT 1 FROM installation_state WHERE id=1').fetchone():
        return
    # Existing installations (including deleted accounts) must not be reprovisioned.
    if conn.execute('SELECT last_id FROM account_sequence WHERE id=1').fetchone()[0] > 0:
        conn.execute('INSERT INTO installation_state VALUES(1,1)')
        return
    username, password = config['ADMIN_USERNAME'], config['ADMIN_PASSWORD']
    if username == '' and password == '':
        return
    if not isinstance(username, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{3,40}', username):
        raise ValueError('ADMIN_USERNAME must contain 3–40 letters, digits, underscores, dots or hyphens')
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError('ADMIN_PASSWORD must contain 12–256 characters')
    user_id = conn.execute('UPDATE account_sequence SET last_id=last_id+1 WHERE id=1 RETURNING last_id').fetchone()[0]
    conn.execute("INSERT INTO users(id,username,password_hash,role) VALUES(?,?,?,'admin')",
                 (user_id, username.lower(), generate_password_hash(password)))
    conn.execute('INSERT INTO installation_state VALUES(1,1)')


def create_app(config=None):
    app = Flask(__name__, static_folder='static', static_url_path='/static')
    app.config.update(DATABASE=os.environ.get('DATABASE', 'data/stopclop.db'),
                      ALLOW_REGISTRATION=os.environ.get('ALLOW_REGISTRATION', 'true').lower() == 'true',
                      ADMIN_USERNAME=os.environ.get('ADMIN_USERNAME', ''),
                      ADMIN_PASSWORD=os.environ.get('ADMIN_PASSWORD', ''),
                      MAX_CONTENT_LENGTH=16 * 1024,
                      PUSH_PUBLIC_URL=os.environ.get('PUSH_PUBLIC_URL', ''),
                      PUSH_INTERNAL_URL=os.environ.get('PUSH_INTERNAL_URL', ''))
    if config:
        app.config.update(config)
    app.config['SMTP_ENV_CONFIG'] = environment_mail_config()
    Path(app.config['DATABASE']).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(app.config['DATABASE'])) as conn:
        conn.executescript(SCHEMA + PUSH_SCHEMA + SYNC_SCHEMA + COACHING_SCHEMA + ACCOUNT_SCHEMA)
        # Serialize additive migrations across Gunicorn workers; preserve existing EUR data.
        conn.execute('BEGIN IMMEDIATE')
        try:
            columns = {row[1] for row in conn.execute('PRAGMA table_info(users)')}
            adding_roles = 'role' not in columns
            for column, definition in [('role', "TEXT NOT NULL DEFAULT 'user'"), ('active', 'INTEGER NOT NULL DEFAULT 1'), ('suspended', 'INTEGER NOT NULL DEFAULT 0'), ('email', 'TEXT'), ('email_verified', 'INTEGER NOT NULL DEFAULT 0')]:
                if column not in columns:
                    conn.execute(f'ALTER TABLE users ADD COLUMN {column} {definition}')
            conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS users_email ON users(email)')
            if adding_roles and app.config['ADMIN_USERNAME']:
                conn.execute("UPDATE users SET role='admin' WHERE username=?", (app.config['ADMIN_USERNAME'].lower(),))
            for column, definition in [('language', "TEXT NOT NULL DEFAULT 'en'"),
                                       ('currency', "TEXT NOT NULL DEFAULT 'EUR'"),
                                       ('pack_price_micros', 'INTEGER NOT NULL DEFAULT 12000000')]:
                if column not in columns:
                    conn.execute(f'ALTER TABLE users ADD COLUMN {column} {definition}')
                    if column == 'pack_price_micros':
                        conn.execute('UPDATE users SET pack_price_micros=pack_price_cents*10000')
            columns = {row[1] for row in conn.execute('PRAGMA table_info(cigarettes)')}
            if 'currency' not in columns:
                conn.execute("ALTER TABLE cigarettes ADD COLUMN currency TEXT NOT NULL DEFAULT 'EUR'")
            if 'trigger' not in columns:
                conn.execute("ALTER TABLE cigarettes ADD COLUMN trigger TEXT NOT NULL DEFAULT ''")
            columns = {row[1] for row in conn.execute('PRAGMA table_info(tokens)')}
            for column, definition in [('kind', "TEXT NOT NULL DEFAULT 'legacy'"),
                                       ('client', 'TEXT'), ('created_at', 'TEXT')]:
                if column not in columns:
                    conn.execute(f'ALTER TABLE tokens ADD COLUMN {column} {definition}')
            # Old sessions were always named Session, but API keys could use that name too.
            conn.execute("UPDATE tokens SET kind='api' WHERE kind='legacy' AND name<>'Session'")
            # Never reuse an account ID after deletion (including requests still in flight).
            conn.execute("INSERT INTO account_sequence SELECT 1,COALESCE(MAX(id),0) FROM users WHERE true ON CONFLICT(id) DO UPDATE SET last_id=MAX(last_id,excluded.last_id)")
            initialize_account(conn, app.config)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def db():
        if 'db' not in g:
            g.db = sqlite3.connect(app.config['DATABASE'], timeout=15)
            g.db.row_factory = sqlite3.Row
            g.db.execute('PRAGMA foreign_keys=ON')
        return g.db

    @app.teardown_appcontext
    def close_db(_error):
        if 'db' in g:
            g.db.close()

    @app.errorhandler(HTTPException)
    def error(exc):
        code = getattr(g, 'error_code', None)
        if code is None:
            code = {404: 'not_found', 413: 'payload_too_large', 415: 'json_required'}.get(exc.code, 'request_error')
            return jsonify(error=translate(code), code=code), exc.code
        return jsonify(error=exc.description, code=code), exc.code

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.before_request
    def authenticate():
        if not request.path.startswith('/api/') or request.path in ({'/api/auth/login', '/api/auth/register', '/api/config'} | PUBLIC_PATHS):
            return
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            fail('auth_required', 401)
        digest = hashlib.sha256(auth[7:].encode()).hexdigest()
        token = db().execute('SELECT * FROM tokens WHERE digest=? AND expires_at>?', (digest, stamp(now()))).fetchone()
        if token is None:
            fail('invalid_token', 401)
        g.token = token
        g.user = db().execute('SELECT * FROM users WHERE id=?', (token['user_id'],)).fetchone()
        if g.user is None or not g.user['active']:
            fail('invalid_token', 401)
        if request.path.startswith('/api/admin/') and (g.user['role'] != 'admin' or g.token['kind'] != 'session'):
            fail('admin_required', 403)
        if g.user['role'] == 'admin' and not (request.path.startswith('/api/admin/') or request.path in ('/api/me', '/api/auth/logout', '/api/account/email')):
            fail('user_space_only', 403)
        if g.user['role'] == 'admin' and request.method == 'DELETE' and request.path == '/api/me':
            fail('admin_protected', 403)

    def issue_token(user_id, name, days, kind="api", client=None):
        secret = secrets.token_urlsafe(32)
        created = now()
        expiry = stamp(created + timedelta(days=days))
        cursor = db().execute('INSERT INTO tokens(user_id,digest,name,expires_at,kind,client,created_at) VALUES(?,?,?,?,?,?,?)',
                              (user_id, hashlib.sha256(secret.encode()).hexdigest(), name, expiry, kind, client, stamp(created)))
        return dict(token=secret, id=cursor.lastrowid, expires_at=expiry)

    def session_duration(data):
        client = data.get('client', 'web')
        if client not in ('web', 'android'):
            fail('invalid_input')
        return 30 if client == 'android' else 1

    def auth_limit():
        cutoff = stamp(now() - timedelta(minutes=15))
        with db():
            db().execute('DELETE FROM auth_attempts WHERE attempted_at<?', (cutoff,))
            count = db().execute('SELECT COUNT(*) FROM auth_attempts WHERE address=?', (request.remote_addr,)).fetchone()[0]
            if count >= 30:
                fail('rate_limit', 429)
            db().execute('INSERT INTO auth_attempts VALUES(?,?)', (request.remote_addr, stamp(now())))

    @app.cli.command('create-admin')
    @click.option('--username', prompt=True)
    @click.password_option()
    def create_admin(username, password):
        """Create a dedicated administrator on an existing installation."""
        if not re.fullmatch(r'[a-zA-Z0-9_.-]{3,40}', username) or not 12 <= len(password) <= 256:
            raise click.ClickException('Username: 3–40 allowed characters; password: 12–256 characters.')
        with db():
            db().execute('BEGIN IMMEDIATE')
            if db().execute('SELECT 1 FROM users WHERE username=?', (username.lower(),)).fetchone():
                raise click.ClickException('Username already exists. Choose a dedicated administrator name.')
            uid = db().execute('UPDATE account_sequence SET last_id=last_id+1 WHERE id=1 RETURNING last_id').fetchone()[0]
            db().execute("INSERT INTO users(id,username,password_hash,role) VALUES(?,?,?,'admin')", (uid, username.lower(), generate_password_hash(password)))
        click.echo('Administrator created.')

    deliver_account_email = register_account_routes(app, db, body, fail, now, stamp, auth_limit)

    @app.get('/')
    def index():
        return send_from_directory(app.static_folder, 'index.html')

    @app.get('/healthz')
    def health():
        db().execute('SELECT 1 FROM users LIMIT 1')
        return jsonify(status='ok')

    @app.get('/api/config')
    def public_config():
        instant = now()
        return jsonify(registration_enabled=app.config['ALLOW_REGISTRATION'],
                       email_required=bool(mail_config(db()).get('enabled')),
                       languages=[dict(code=code, name=name) for code, name in LANGUAGES.items()],
                       currencies=currency_catalog(language()), timezones=TIMEZONES,
                       timezone_options=timezone_catalog(language(), instant), timezone_aliases=ALIASES,
                       timezone_offsets_at=stamp(instant), tzdata_version=TZDATA_VERSION)

    @app.post('/api/auth/register')
    def register():
        if not app.config['ALLOW_REGISTRATION']:
            fail('registration_closed', 403)
        auth_limit()
        data = body()
        days = session_duration(data)
        username = data.get('username', '')
        password = data.get('password', '')
        if not isinstance(username, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{3,40}', username):
            fail('invalid_username')
        if not isinstance(password, str) or not 12 <= len(password) <= 256:
            fail('invalid_password')
        locale = data.get('language', 'en')
        if not isinstance(locale, str) or locale not in LANGUAGES:
            fail('invalid_language')
        tz = data.get('timezone', 'Europe/Paris')
        if not isinstance(tz, str) or tz not in VALID_TIMEZONES:
            fail('invalid_timezone')
        # New accounts may normalize browser aliases; existing accounts never auto-change.
        tz = canonical_timezone(tz) or tz
        email_required = bool(mail_config(db()).get('enabled'))
        email = email_address(data.get('email')) if email_required else None
        if email_required and not email:
            fail('invalid_email')
        try:
            with db():
                db().execute('BEGIN IMMEDIATE')
                user_id = db().execute('UPDATE account_sequence SET last_id=last_id+1 WHERE id=1 RETURNING last_id').fetchone()[0]
                cursor = db().execute('INSERT INTO users(id,username,password_hash,language,timezone,email,active) VALUES(?,?,?,?,?,?,?)',
                                      (user_id, username.lower(), generate_password_hash(password), locale, tz, email, int(not email_required)))
                if email_required:
                    deliver_account_email(email, 'activate', user_id, locale)
                    result = dict(activation_required=True, message=translate('email_requested'))
                else:
                    result = issue_token(cursor.lastrowid, 'Session', days, 'session', data.get('client', 'web'))
        except sqlite3.IntegrityError:
            fail('username_taken', 409)
        return jsonify(result), 201

    @app.post('/api/auth/login')
    def login():
        auth_limit()
        data = body()
        days = session_duration(data)
        username, password = data.get('username', ''), data.get('password', '')
        if not isinstance(username, str) or not isinstance(password, str) or len(password) > 256:
            fail('invalid_credentials', 401)
        user = db().execute('SELECT * FROM users WHERE username=?', (username.lower(),)).fetchone()
        # Always perform the expensive password operation, including unknown accounts.
        valid = check_password_hash(user['password_hash'], password) if user else check_password_hash(app.config['DUMMY_HASH'], password)
        if not user or not valid or not user['active']:
            fail('invalid_credentials', 401)
        with db():
            db().execute('DELETE FROM tokens WHERE expires_at<?', (stamp(now()),))
            result = issue_token(user['id'], 'Session', days, 'session', data.get('client', 'web'))
        return jsonify(result)

    app.config['DUMMY_HASH'] = generate_password_hash(secrets.token_urlsafe(32))

    @app.post('/api/auth/logout')
    def logout():
        with db():
            db().execute('DELETE FROM tokens WHERE id=?', (g.token['id'],))
        return '', 204

    @app.get('/api/me')
    def me():
        return jsonify(id=g.user['id'], username=g.user['username'], role=g.user['role'], language=g.user['language'], email=g.user['email'], email_verified=bool(g.user['email_verified']))

    @app.delete('/api/me')
    def delete_account():
        auth_limit()
        data = body()
        password = data.get('password')
        if (data.get('confirm') is not True or not isinstance(password, str)
                or len(password) > 256 or not check_password_hash(g.user['password_hash'], password)):
            fail('account_delete_invalid', 400)
        with db():
            db().execute('BEGIN IMMEDIATE')
            # FK order matters; token deletion also removes push subscriptions/outbox.
            for table in ('cravings', 'checkins', 'journeys', 'cigarettes', 'tokens', 'sync_revisions'):
                # table comes only from the fixed tuple above.
                db().execute(f'DELETE FROM {table} WHERE user_id=?', (g.user['id'],))  # nosec B608
            db().execute('DELETE FROM users WHERE id=?', (g.user['id'],))
        return '', 204

    @app.get('/api/tokens')
    def tokens():
        rows = db().execute('SELECT id,name,expires_at,kind,client,created_at FROM tokens WHERE user_id=? AND expires_at>? ORDER BY id DESC', (g.user['id'], stamp(now())))
        return jsonify([dict(row, current=row['id'] == g.token['id']) for row in rows])

    @app.delete('/api/sessions/others')
    def revoke_other_sessions():
        with db():
            db().execute("DELETE FROM tokens WHERE user_id=? AND kind='session' AND id<>?",
                         (g.user['id'], g.token['id']))
        return '', 204

    @app.post('/api/tokens')
    def new_token():
        data = body()
        name = data.get('name', 'Stream Deck')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
            fail('invalid_key_name')
        with db():
            result = issue_token(g.user['id'], name.strip(), 365)
        return jsonify(result), 201

    @app.delete('/api/tokens/<int:token_id>')
    def revoke_token(token_id):
        with db():
            deleted = db().execute('DELETE FROM tokens WHERE id=? AND user_id=?', (token_id, g.user['id'])).rowcount
        if not deleted:
            fail('key_not_found', 404)
        return '', 204

    # Bound streaming requests per worker, reserving threads for ordinary API calls.
    sync_slots = threading.BoundedSemaphore(16)

    @app.get('/api/sync/config')
    def sync_config():
        return jsonify(transport='sse', path='/api/sync/events')

    @app.get('/api/sync/events')
    def sync_events():
        cursor = request.headers.get('Last-Event-ID', '')
        if cursor and not re.fullmatch('[0-9a-f]{32}', cursor):
            fail('invalid_input')
        if not sync_slots.acquire(blocking=False):
            return jsonify(error='Synchronization capacity reached'), 503, {'Retry-After': '30'}
        stream = events(app.config['DATABASE'], g.token['id'], g.user['id'], g.token['digest'], cursor)
        released = False
        def release():
            nonlocal released
            if not released:
                released = True
                sync_slots.release()
        def generate():
            try:
                yield from stream
            finally:
                stream.close()
                release()
        response = Response(generate(), mimetype='text/event-stream', headers={'X-Accel-Buffering': 'no'})
        response.call_on_close(release)
        return response

    @app.route('/api/push', methods=['GET', 'PUT', 'DELETE'])
    def push_subscription():
        enabled = bool(app.config['PUSH_PUBLIC_URL'] and app.config['PUSH_INTERNAL_URL'])
        if request.method == 'DELETE':
            with db():
                db().execute('DELETE FROM push_subscriptions WHERE token_id=?', (g.token['id'],))
            return '', 204
        if request.method == 'PUT':
            if not enabled:
                fail('push_unavailable', 503)
            endpoint = body().get('endpoint')
            try:
                topic_for(endpoint, app.config['PUSH_PUBLIC_URL'])
            except ValueError:
                fail('push_invalid_endpoint')
            with db():
                count = db().execute('SELECT COUNT(*) FROM push_subscriptions s JOIN tokens t ON t.id=s.token_id WHERE t.user_id=?', (g.user['id'],)).fetchone()[0]
                existing = db().execute('SELECT 1 FROM push_subscriptions WHERE token_id=?', (g.token['id'],)).fetchone()
                if count >= 16 and not existing:
                    fail('push_limit', 429)
                db().execute('INSERT INTO push_subscriptions(token_id,endpoint) VALUES (?,?) ON CONFLICT(token_id) DO UPDATE SET endpoint=excluded.endpoint',
                             (g.token['id'], endpoint))
                queue_refresh(db(), g.user['id'])
        registered = db().execute('SELECT 1 FROM push_subscriptions WHERE token_id=?', (g.token['id'],)).fetchone() is not None
        return jsonify(enabled=enabled, server=app.config['PUSH_PUBLIC_URL'] if enabled else None, registered=registered)

    @app.route('/api/settings', methods=['GET', 'PUT'])
    def settings():
        if request.method == 'PUT':
            data = body()
            currency = data.get('currency', g.user['currency'])
            locale = data.get('language', g.user['language'])
            if not isinstance(currency, str) or currency not in CURRENCIES:
                fail('invalid_currency')
            if not isinstance(locale, str) or locale not in LANGUAGES:
                fail('invalid_language')
            if currency != g.user['currency'] and 'pack_price' not in data:
                fail('price_required')
            if 'pack_price' in data:
                value = data['pack_price']
            elif 'pack_price_cents' in data:
                cents = integer(data['pack_price_cents'], 0, 100000000, 'pack_price')
                value = str(Decimal(cents) / 100)
            else:
                value = price_string(g.user['pack_price_micros'], currency)
            try:
                price = price_micros(value, currency)
            except ValueError:
                fail('invalid_price', 400, get_currency_precision(currency), currency)
            size = integer(data.get('pack_size', g.user['pack_size']), 1, 1000, 'pack_size')
            target = integer(data.get('daily_target', g.user['daily_target']), 0, 200, 'daily_target')
            tz = data.get('timezone', g.user['timezone'])
            if not isinstance(tz, str) or tz not in VALID_TIMEZONES:
                fail('invalid_timezone')
            with db():
                db().execute('UPDATE users SET pack_price_cents=?,pack_price_micros=?,pack_size=?,daily_target=?,timezone=?,currency=?,language=? WHERE id=?',
                             (int((Decimal(price) / 10000).quantize(Decimal('1'), rounding=ROUND_HALF_UP)),
                              price, size, target, tz, currency, locale, g.user['id']))
                queue_refresh(db(), g.user['id'])
            g.user = db().execute('SELECT * FROM users WHERE id=?', (g.user['id'],)).fetchone()
        instant = now()
        return jsonify({**{key: g.user[key] for key in ('pack_price_cents', 'pack_size', 'daily_target', 'timezone', 'currency', 'language')},
                        'pack_price': price_string(g.user['pack_price_micros'], g.user['currency']),
                        'timezone_info': timezone_info(g.user['timezone'], g.user['language'], instant),
                        'reminders': reminder_preferences(db(), g.user['id']),
                        'coaching_goal': goal_for(g.user, plan_for(db(), g.user['id']), instant.astimezone(get_zone(g.user['timezone'])).date().isoformat()),
                        'local_today': instant.astimezone(get_zone(g.user['timezone'])).date().isoformat(),
                        'local_datetime': instant.astimezone(get_zone(g.user['timezone'])).isoformat()})

    def period():
        tz = get_zone(g.user['timezone'])
        today = now().astimezone(tz).date()
        try:
            end = date.fromisoformat(request.args.get('end', today.isoformat()))
            if end.year < 2000:
                raise ValueError()
            start = date.fromisoformat(request.args.get('start', (end - timedelta(days=29)).isoformat()))
        except ValueError:
            fail('invalid_dates')
        if start.year < 2000 or not 0 <= (end - start).days <= 365 or end > today:
            fail('invalid_period')
        return tz, today, start, end

    def bounds(start, end, tz):
        return stamp(datetime.combine(start, time.min, tz)), stamp(datetime.combine(end + timedelta(days=1), time.min, tz))

    def entries(start, end, tz):
        low, high = bounds(start, end, tz)
        return db().execute('SELECT * FROM cigarettes WHERE user_id=? AND occurred_at>=? AND occurred_at<? ORDER BY occurred_at DESC,id DESC',
                            (g.user['id'], low, high)).fetchall()

    def serialize(row):
        return dict(id=row['id'], occurred_at=row['occurred_at'],
                    local_datetime=datetime.fromisoformat(row['occurred_at']).astimezone(get_zone(g.user['timezone'])).isoformat(), quantity=row['quantity'],
                    cost=money(row['quantity'] * row['unit_cost_micros'], row['currency']), currency=row['currency'], source=row['source'], trigger=row['trigger'])

    @app.post('/api/cigarettes')
    def add():
        data = body() if request.data else {}
        quantity = integer(data.get('quantity', 1), 1, 200, 'quantity')
        trigger = data.get('trigger', '')
        if trigger not in TRIGGERS:
            fail('invalid_input')
        source = data.get('source', 'api')
        if source not in ('web', 'android', 'api', 'streamdeck'):
            fail('invalid_source')
        occurred = now()
        if 'occurred_at_local' in data:
            if 'occurred_at' in data:
                fail('invalid_timestamp')
            try:
                local = datetime.fromisoformat(data['occurred_at_local'])
                if local.tzinfo is not None:
                    raise ValueError()
                tz = get_zone(g.user['timezone'])
                zoned = local.replace(tzinfo=tz, fold=0)
                occurred = zoned.astimezone(UTC)
                # Reject nonexistent wall times during spring DST transitions.
                if occurred.astimezone(tz).replace(tzinfo=None) != local:
                    raise ValueError()
            except (TypeError, ValueError, OverflowError):
                fail('invalid_timestamp')
        if 'occurred_at' in data:
            try:
                occurred = datetime.fromisoformat(data['occurred_at'].replace('Z', '+00:00'))
                if occurred.tzinfo is None:
                    raise ValueError()
                occurred = occurred.astimezone(UTC)
            except (AttributeError, TypeError, ValueError, OverflowError):
                fail('invalid_timestamp')
        received_at = now()
        # A widget's clock can be slightly ahead even with automatic time enabled.
        # Clamp a small skew to server time so no future entry/day is stored.
        # Explicit local dates remain strict (they are manually entered).
        if 'occurred_at' in data and received_at < occurred <= received_at + timedelta(seconds=5):
            occurred = received_at
        if occurred > received_at or occurred.year < 2000:
            fail('invalid_entry_date')
        key = request.headers.get('Idempotency-Key')
        if key is not None and not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', key):
            fail('invalid_idempotency')
        unit = int((Decimal(g.user['pack_price_micros']) / g.user['pack_size']).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        with db():
            if key:
                previous = db().execute('SELECT * FROM cigarettes WHERE user_id=? AND idempotency_key=?', (g.user['id'], key)).fetchone()
                if previous:
                    return jsonify(serialize(previous)), 200
            try:
                cursor = db().execute('INSERT INTO cigarettes(user_id,occurred_at,quantity,unit_cost_micros,source,idempotency_key,currency,trigger) VALUES(?,?,?,?,?,?,?,?)',
                                      (g.user['id'], stamp(occurred), quantity, unit, source, key, g.user['currency'], trigger))
            except sqlite3.IntegrityError:
                previous = db().execute('SELECT * FROM cigarettes WHERE user_id=? AND idempotency_key=?', (g.user['id'], key)).fetchone()
                return jsonify(serialize(previous)), 200
            row = db().execute('SELECT * FROM cigarettes WHERE id=?', (cursor.lastrowid,)).fetchone()
            invalidate_checkins(db(), g.user['id'], row['occurred_at'])
            queue_refresh(db(), g.user['id'])
        return jsonify(serialize(row)), 201

    @app.get('/api/cigarettes')
    def history():
        tz, _, start, end = period()
        try:
            limit = integer(int(request.args.get('limit', 100)), 1, 500, 'limit')
            offset = integer(int(request.args.get('offset', 0)), 0, 10000000, 'offset')
        except ValueError:
            fail('invalid_pagination')
        rows = entries(start, end, tz)
        return jsonify(items=[serialize(row) for row in rows[offset:offset + limit]], total=len(rows))

    @app.delete('/api/cigarettes/<int:entry_id>')
    def remove(entry_id):
        with db():
            row = db().execute('SELECT occurred_at FROM cigarettes WHERE id=? AND user_id=?', (entry_id, g.user['id'])).fetchone()
            if row:
                invalidate_checkins(db(), g.user['id'], row['occurred_at'])
            deleted = db().execute('DELETE FROM cigarettes WHERE id=? AND user_id=?', (entry_id, g.user['id'])).rowcount
            if deleted:
                queue_refresh(db(), g.user['id'])
        if not deleted:
            fail('entry_not_found', 404)
        return '', 204

    @app.get('/api/stats')
    def stats():
        tz, today, start, end = period()
        days = (end - start).days + 1
        daily = {(start + timedelta(days=i)).isoformat(): {'quantity': 0, 'amounts': {}} for i in range(days)}
        period_rows = entries(start, end, tz)
        for row in period_rows:
            day = datetime.fromisoformat(row['occurred_at']).astimezone(tz).date().isoformat()
            daily[day]['quantity'] += row['quantity']
            amounts = daily[day]['amounts']
            amounts[row['currency']] = amounts.get(row['currency'], 0) + row['quantity'] * row['unit_cost_micros']
        low, high = bounds(today, today, tz)
        def total(condition='', params=()):
            # condition is a fixed internal SQL fragment; values stay parameterized.
            rows = db().execute('SELECT currency,SUM(quantity) AS quantity,SUM(quantity*unit_cost_micros) AS amount FROM cigarettes WHERE user_id=? ' + condition + ' GROUP BY currency',  # nosec B608
                                (g.user['id'], *params)).fetchall()
            return dict(quantity=sum(row['quantity'] for row in rows),
                        **cost_summary({row['currency']: row['amount'] for row in rows}, g.user['currency']))
        quantity = sum(day['quantity'] for day in daily.values())
        period_amounts = {}
        for day in daily.values():
            for code, amount in day['amounts'].items():
                period_amounts[code] = period_amounts.get(code, 0) + amount
        previous_start, previous_end = start - timedelta(days=days), start - timedelta(days=1)
        previous = []
        if previous_start.year >= 2000:
            previous_days = {(previous_start + timedelta(days=i)).isoformat(): {'quantity': 0, 'amounts': {}} for i in range(days)}
            for row in entries(previous_start, previous_end, tz):
                day = previous_days[datetime.fromisoformat(row['occurred_at']).astimezone(tz).date().isoformat()]
                day['quantity'] += row['quantity']
                day['amounts'][row['currency']] = day['amounts'].get(row['currency'], 0) + row['quantity'] * row['unit_cost_micros']
            previous = list(previous_days.values())
        analysis = analyze([dict(date=d, **v) for d, v in daily.items()], previous, g.user['currency'],
                           previous_start.isoformat() if previous else None,
                           previous_end.isoformat() if previous else None, end == today)
        analysis.update(habits([dict(date=d, **v) for d, v in daily.items()], period_rows, tz, end == today, g.user['currency']))
        first = db().execute('SELECT MIN(occurred_at) FROM cigarettes WHERE user_id=?', (g.user['id'],)).fetchone()[0]
        history_start = datetime.fromisoformat(first).astimezone(tz).date() if first else None
        history_days = max(0, (today-history_start).days+1) if history_start else 0
        return jsonify(history_start=history_start.isoformat() if history_start else None,
                       history_days=history_days, analysis=analysis, start=start.isoformat(), end=end.isoformat(), timezone=g.user['timezone'],
                       today=total('AND occurred_at>=? AND occurred_at<?', (low, high)), total=total(),
                       period=dict(quantity=quantity, **cost_summary(period_amounts, g.user['currency']),
                                   average_per_day=round(quantity / days, 2), days=days,
                                   days_without_entries=sum(day['quantity'] == 0 for day in daily.values())),
                       daily=[dict(date=d, quantity=v['quantity'], **cost_summary(v['amounts'], g.user['currency'])) for d, v in daily.items()])

    @app.get('/api/export.csv')
    def export():
        tz, _, start, end = period()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['id', 'local_datetime', 'quantity', 'cost', 'currency', 'source'])
        for row in entries(start, end, tz):
            writer.writerow([row['id'], datetime.fromisoformat(row['occurred_at']).astimezone(tz).isoformat(),
                             row['quantity'], price_string(row['quantity'] * row['unit_cost_micros'], row['currency']), row['currency'], row['source']])
        return app.response_class('\ufeff' + output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=suuless.csv'})

    register_routes(app, db, lambda: now(), stamp, body, fail, integer, bounds, entries)
    return app
