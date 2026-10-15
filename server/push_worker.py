"""Run one dispatcher alongside the API against the same application database."""
from contextlib import closing
import signal
from .database import connect, DatabaseError
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
    with closing(connect(app.config['DATABASE_TARGET'])) as conn:
        while not stopped:
            try:
                dispatch(conn, public, internal)
                # non-secret health marker in the worker container's temporary filesystem.
                Path('/tmp/push-worker-health').touch()  # nosec B108
            except DatabaseError:
                print('Push dispatcher: database temporarily unavailable', flush=True)
            time.sleep(2)


if __name__ == '__main__':
    main()
