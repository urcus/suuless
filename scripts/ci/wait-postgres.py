"""Wait for the disposable CI database without logging its connection URL."""
import os
import time
import psycopg

for attempt in range(60):
    try:
        with psycopg.connect(os.environ['TEST_POSTGRES_URL'], connect_timeout=2):
            break
    except psycopg.OperationalError:
        time.sleep(1)
else:
    raise SystemExit('PostgreSQL test service did not become ready')
