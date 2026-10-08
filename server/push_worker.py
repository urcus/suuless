"""Run one dispatcher alongside the API against the same SQLite volume."""
from contextlib import closing
import signal
import sqlite3
import time
from pathlib import Path
from .app import create_app
from .push import dispatch


def main():
    app = create_app()
    public, internal = app.config['PUSH_PUBLIC_URL'], app.config['PUSH_INTERNAL_URL']
    if not public or not internal:
        raise SystemExit('PUSH_PUBLIC_URL and PUSH_INTERNAL_URL are required')
    stopped = False
    def stop(*_):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with closing(sqlite3.connect(app.config['DATABASE'], timeout=15)) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        while not stopped:
            try:
                dispatch(conn, public, internal)
                Path('/tmp/push-worker-health').touch()
            except sqlite3.Error:
                print('Push dispatcher: database temporarily unavailable', flush=True)
            time.sleep(2)


if __name__ == '__main__':
    main()
