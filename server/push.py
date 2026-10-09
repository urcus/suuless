"""Per-session UnifiedPush subscriptions and a durable, coalescing refresh outbox."""
import re
from .sync import changed
import sqlite3
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

SCHEMA = '''
CREATE TABLE IF NOT EXISTS push_subscriptions (
 token_id INTEGER PRIMARY KEY REFERENCES tokens(id) ON DELETE CASCADE,
 endpoint TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS push_outbox (
 token_id INTEGER PRIMARY KEY REFERENCES push_subscriptions(token_id) ON DELETE CASCADE,
 revision TEXT NOT NULL DEFAULT (lower(hex(randomblob(16)))),
 attempts INTEGER NOT NULL DEFAULT 0,
 next_attempt REAL NOT NULL DEFAULT 0
);
'''


def topic_for(endpoint, public_url):
    if not isinstance(endpoint, str) or len(endpoint) > 512:
        raise ValueError('Invalid endpoint')
    expected, actual = urlsplit(public_url), urlsplit(endpoint)
    if (expected.scheme != 'https' or not expected.netloc or expected.path not in ('', '/')
            or actual.scheme != expected.scheme or actual.netloc != expected.netloc
            or actual.username or actual.password or actual.fragment or actual.query not in ('', 'up=1')
            or not re.fullmatch(r'/up[A-Za-z0-9_-]{12,200}', actual.path)):
        raise ValueError('Invalid endpoint')
    return actual.path[1:]


def queue_refresh(conn, user_id):
    changed(conn, user_id)
    # Called in the same transaction as the change. No network on the request path.
    for row in conn.execute('SELECT s.token_id FROM push_subscriptions s JOIN tokens t ON t.id=s.token_id WHERE t.user_id=?', (user_id,)).fetchall():
        conn.execute('''INSERT INTO push_outbox(token_id) VALUES (?)
                        ON CONFLICT(token_id) DO UPDATE SET revision=lower(hex(randomblob(16))), attempts=0, next_attempt=0''', (row[0],))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send_refresh(internal_url, topic):
    request = Request(internal_url.rstrip('/') + '/' + topic + '?up=1', data=b'refresh',
                      headers={'Content-Type': 'application/octet-stream', 'TTL': '300'})
    with build_opener(NoRedirect).open(request, timeout=3) as response:
        response.read(4096)


def dispatch(conn, public_url, internal_url, sender=send_refresh, clock=time.time):
    """Single worker; revision checks preserve changes arriving during delivery."""
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute('DELETE FROM push_subscriptions WHERE token_id IN (SELECT id FROM tokens WHERE expires_at<=?)',
                     (datetime.now(timezone.utc).isoformat(timespec='microseconds'),))
    rows = conn.execute('''SELECT q.*,s.endpoint FROM push_outbox q JOIN push_subscriptions s USING(token_id)
                           WHERE q.next_attempt<=? ORDER BY q.next_attempt LIMIT 16''', (clock(),)).fetchall()
    for row in rows:
        try:
            sender(internal_url, topic_for(row['endpoint'], public_url))
        except Exception:
            # Never log the capability URL or let a push failure affect consumption.
            with conn:
                conn.execute('''UPDATE push_outbox SET attempts=attempts+1,next_attempt=?
                                WHERE token_id=? AND revision=?''',
                             (clock()+min(300, 5*2**min(row['attempts'], 6)), row['token_id'], row['revision']))
        else:
            with conn:
                conn.execute('DELETE FROM push_outbox WHERE token_id=? AND revision=?', (row['token_id'], row['revision']))
    return len(rows)
