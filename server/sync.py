"""Authenticated invalidation stream; revisions survive restarts and offline clients."""
from contextlib import closing
from datetime import datetime, timezone
import secrets
from .database import connect
import time

SCHEMA = '''
CREATE TABLE IF NOT EXISTS sync_revisions (
 user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 revision TEXT NOT NULL
);
'''


def changed(conn, user_id):
    conn.execute('''INSERT INTO sync_revisions(user_id,revision) VALUES (?,?)
                    ON CONFLICT(user_id) DO UPDATE SET revision=excluded.revision''', (user_id,secrets.token_hex(16)))


def events(database, token_id, user_id, digest, cursor='', duration=60, interval=1, clock=time.monotonic, sleep=time.sleep):
    """No open transaction during waits; revalidate session before every event."""
    deadline = clock() + duration
    heartbeat = clock()
    with closing(connect(database, timeout=5)) as conn:
        while clock() < deadline:
            row = conn.execute('''SELECT COALESCE(s.revision, ?) FROM tokens t
                LEFT JOIN sync_revisions s ON s.user_id=t.user_id
                WHERE t.id=? AND t.user_id=? AND t.digest=? AND t.expires_at>?''',
                ('0'*32, token_id, user_id, digest, datetime.now(timezone.utc).isoformat(timespec='microseconds'))).fetchone()
            if row is None:
                yield 'event: revoked\ndata: {}\n\n'
                return
            revision = row[0]
            if revision != cursor:
                yield f'id: {revision}\nevent: refresh\ndata: {{}}\n\n'
                cursor = revision
                heartbeat = clock()
            elif clock() >= heartbeat:
                yield ': keepalive\n\n'
                heartbeat = clock()+10
            sleep(interval)
