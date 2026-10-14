"""Isolated browser-test fixture: all SMTP deliveries stay in a temporary file."""
import json
import os
from pathlib import Path
from unittest.mock import patch
from werkzeug.serving import make_server
from server.app import create_app

app = create_app(dict(DATABASE=os.environ['ADMIN_TEST_DATABASE'], ADMIN_USERNAME='administrator',
                      ADMIN_PASSWORD='administrator-test-password', TESTING=True))

def capture(config, recipient, subject, content):
    Path(os.environ['ADMIN_TEST_MAIL']).write_text(json.dumps(dict(recipient=recipient, subject=subject, content=content)))

with patch('server.accounts.send_mail', capture):
    server = make_server('127.0.0.1', 0, app, threaded=True)
    print(server.server_port, flush=True)
    server.serve_forever()
