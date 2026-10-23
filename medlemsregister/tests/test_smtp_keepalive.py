import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import smtp_keepalive as target


class KeepaliveTests(unittest.TestCase):
    def test_sends_only_every_30_days_and_retries_failure(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(target, 'send_test') as send:
            directory = Path(folder)
            self.assertTrue(target.run(directory, now=100))
            self.assertFalse(target.run(directory, now=100 + target.INTERVAL - 1))
            send.assert_called_once()
            send.side_effect = RuntimeError('test failure')
            with self.assertRaises(RuntimeError):
                target.run(directory, now=100 + target.INTERVAL)
            self.assertIn('100', (directory/'smtp-keepalive.json').read_text())
            send.side_effect = None
            self.assertTrue(target.run(directory, now=100 + target.INTERVAL + 1))
            self.assertEqual((directory/'smtp-keepalive.json').stat().st_mode & 0o777, 0o600)

    def test_exact_message_and_brevo_credentials(self):
        env = {'SMTP_HOST':'smtp-relay.brevo.com','SMTP_PORT':'465','SMTP_USER':'test-login',
               'SMTP_PASSWORD':'test-key','STYRE_EPOST_FRA':'ikkjesvar@oslobygda.no'}
        with patch.dict(os.environ, env), patch.object(target.smtplib, 'SMTP_SSL') as smtp:
            client = smtp.return_value
            client.send_message.return_value = {}
            target.send_test()
            client.login.assert_called_once_with('test-login','test-key')
            message = client.send_message.call_args.args[0]
            self.assertEqual(message['To'], 'folk@oslobygda.no')
            self.assertEqual(message['Subject'], target.SUBJECT)
            self.assertEqual(message['Auto-Submitted'],'auto-generated')
            self.assertNotIn('test-key', message.as_string())
        with patch.dict(os.environ, {'SMTP_HOST':'smtp.domeneshop.no'}):
            with self.assertRaises(ValueError):
                target.send_test()
