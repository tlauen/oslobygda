import time
import unittest
from unittest.mock import patch

import pyotp
from werkzeug.security import check_password_hash
import app as module
import test_styre_auth as fixtures


class PasswordResetTests(unittest.TestCase):
    token = fixtures.BoardAuthTests.token

    def setUp(self):
        fixtures.BoardAuthTests.setUp(self)
        with module.get_db() as db:
            db.execute("UPDATE board_users SET username='board@example.org'")
        self.ready = patch('passord_reset.mail_ready', return_value=True)
        self.sender = patch('passord_reset.send_code')
        self.ready.start()
        self.send = self.sender.start()

    def tearDown(self):
        self.sender.stop()
        self.ready.stop()
        fixtures.BoardAuthTests.tearDown(self)

    def start(self, email='board@example.org'):
        return self.client.post('/gløymt-passord', data={'email': email, 'csrf_token': self.token()})

    def finish(self, email_code=None, code=None):
        return self.client.post('/gløymt-passord/byt', data={
            'csrf_token': self.token(), 'email_code': email_code or self.send.call_args.args[1],
            'code': code or pyotp.TOTP(self.secret).now(),
            'password': 'my new sufficiently long password', 'confirmation': 'my new sufficiently long password'})

    def test_reset_keeps_totp_invalidates_sessions_and_is_single_use(self):
        other = module.app.test_client()
        with other.session_transaction() as session:
            session.update(board_username='board@example.org', board_version='version-1', board_logged_in_at=int(time.time()))
        self.assertEqual(other.get('/api/members').status_code, 200)
        self.assertEqual(self.start().status_code, 302)
        self.assertNotIn(self.secret.encode(), self.client.get('/gløymt-passord/byt').data)
        self.assertEqual(self.finish().status_code, 200)
        with module.get_db() as db:
            user = db.execute('SELECT * FROM board_users').fetchone()
            self.assertEqual(user['totp_secret'], self.secret)
            self.assertNotEqual(user['session_version'], 'version-1')
            self.assertTrue(check_password_hash(user['password_hash'], 'my new sufficiently long password'))
        self.assertEqual(other.get('/api/members', headers={'Accept': 'application/json'}).status_code, 401)
        self.assertEqual(self.finish().status_code, 400)

    def test_unknown_inactive_and_failed_delivery_have_same_response(self):
        unknown = self.start('unknown@example.org')
        self.send.assert_not_called()
        with module.get_db() as db:
            db.execute('UPDATE board_users SET active=0')
        inactive = self.start()
        self.assertEqual(unknown.location, inactive.location)
        self.send.assert_not_called()
        with module.get_db() as db:
            db.execute('UPDATE board_users SET active=1')
        self.send.side_effect = RuntimeError('secret provider error')
        with self.assertLogs(module.app.logger, level='ERROR') as logs:
            failed = self.start()
        self.assertEqual(failed.location, unknown.location)
        self.assertNotIn('secret provider error', str(logs.output))
        with module.get_db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM board_password_reset').fetchone()[0], 0)

    def test_expiry_attempts_csrf_and_wrong_totp(self):
        self.assertEqual(self.client.post('/gløymt-passord', data={'email':'board@example.org'}).status_code, 400)
        self.start()
        for _ in range(5):
            self.assertEqual(self.finish(code='bad').status_code, 400)
        self.assertEqual(self.finish().status_code, 400)
        self.start()
        with patch('passord_reset.time.time', return_value=int(time.time()) + 901):
            self.assertEqual(self.finish().status_code, 400)
        self.start()
        self.assertEqual(self.finish(email_code='000000000').status_code, 400)

    def test_revoked_role_changed_version_and_used_totp_rejected(self):
        for change in ("UPDATE board_users SET active=0", "UPDATE board_users SET session_version='changed'", "UPDATE board_users SET last_step=999999999999"):
            with module.get_db() as db:
                db.execute("UPDATE board_users SET active=1,session_version='version-1',last_step=-1")
                db.execute('DELETE FROM login_limits')
            self.start()
            with module.get_db() as db:
                db.execute(change)
            self.assertEqual(self.finish().status_code, 400)
        with module.get_db() as db:
            db.execute("UPDATE board_users SET active=1,last_step=-1,member_id=123")
            db.execute('DELETE FROM login_limits')
        self.send.reset_mock()
        self.start()
        self.send.assert_not_called()

    def test_rate_limit_and_unconfigured(self):
        for _ in range(3):
            self.assertEqual(self.start().status_code, 302)
        self.assertEqual(self.start().status_code, 429)
        with patch('passord_reset.mail_ready', return_value=False):
            self.assertEqual(self.client.get('/gløymt-passord').status_code, 503)

    def test_role_is_checked_again_and_codes_bound_to_browser(self):
        with module.get_db() as db:
            db.execute("INSERT INTO members(full_name,email,membership_type,payment_status,consent_at,created_at,updated_at) VALUES ('Board','board@example.org','styret','ikkje betalt','2026','2026','2026')")
            db.execute("UPDATE board_users SET member_id=(SELECT id FROM members WHERE email='board@example.org')")
        self.start()
        with self.client.session_transaction() as state:
            identifier = state['password_reset_id']
        other = module.app.test_client()
        response = other.post('/gløymt-passord/byt', data={
            'csrf_token': self.token(other), 'email_code': self.send.call_args.args[1],
            'code': pyotp.TOTP(self.secret).now(), 'password': 'a sufficiently long new password',
            'confirmation': 'a sufficiently long new password'})
        self.assertEqual(response.status_code, 400)
        with module.get_db() as db:
            db.execute("UPDATE members SET membership_type='vanleg'")
        self.assertEqual(self.finish().status_code, 400)
        with module.get_db() as db:
            self.assertEqual(db.execute('SELECT session_version FROM board_users').fetchone()[0], 'version-1')
            self.assertIsNotNone(db.execute('SELECT id FROM board_password_reset WHERE id=?', (identifier,)).fetchone())
