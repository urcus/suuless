"""SMTP submission evidence must not disclose credentials or message contents."""
import smtplib
import unittest
from unittest.mock import patch
from server.accounts import send_mail


class SMTPLoggingTest(unittest.TestCase):
    def setUp(self):
        self.config = dict(host='smtp.example.com', port=465, security='tls',
                           username='private-login', password='private-password', sender='sender@example.com')
        self.factory = patch('server.accounts.smtplib.SMTP_SSL').start()
        self.addCleanup(patch.stopall)
        self.smtp = self.factory.return_value.__enter__.return_value
        self.smtp.send_message.return_value = {}

    def send(self):
        send_mail(self.config, 'private-recipient@example.com', 'Private subject', 'Private link and content')

    def assert_private(self, lines):
        log = '\n'.join(lines)
        for value in ('private-login', 'private-password', 'private-recipient@example.com',
                      'Private subject', 'Private link and content', 'sender@example.com'):
            self.assertNotIn(value, log)

    def test_acceptance_is_logged_without_claiming_delivery(self):
        with self.assertLogs('suuless.smtp', level='INFO') as logs:
            self.send()
        self.assertIn('submission accepted', logs.output[-1])
        self.assertIn('delivery=unconfirmed', logs.output[-1])
        self.assert_private(logs.output)
        message = self.smtp.send_message.call_args.args[0]
        self.assertTrue(message['Date'])
        self.assertTrue(message['Message-ID'])

    def test_authentication_error_logs_only_stage_type_and_code(self):
        self.smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b'private-password private-login')
        with self.assertLogs('suuless.smtp', level='INFO') as logs, self.assertRaises(smtplib.SMTPAuthenticationError):
            self.send()
        self.assertIn('stage=authenticate', logs.output[-1])
        self.assertIn('smtp_code=535', logs.output[-1])
        self.assert_private(logs.output)
        self.smtp.send_message.assert_not_called()

    def test_refused_recipient_is_not_reported_as_success(self):
        self.smtp.send_message.return_value = {'private-recipient@example.com': (550, b'Private link and content')}
        with self.assertLogs('suuless.smtp', level='INFO') as logs, self.assertRaises(smtplib.SMTPRecipientsRefused):
            self.send()
        self.assertIn('stage=submit', logs.output[-1])
        self.assertNotIn('submission accepted', '\n'.join(logs.output))
        self.assert_private(logs.output)

    def test_network_failure_has_safe_diagnostic(self):
        self.factory.side_effect = TimeoutError('private-password')
        with self.assertLogs('suuless.smtp', level='INFO') as logs, self.assertRaises(TimeoutError):
            self.send()
        self.assertIn('stage=connect', logs.output[-1])
        self.assertIn('error=TimeoutError', logs.output[-1])
        self.assert_private(logs.output)
