"""Køyr: python -m unittest discover -s tests (frå medlemsregister/)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pyotp
from werkzeug.security import generate_password_hash
import app as module


class BoardAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(module, 'DB_PATH', Path(self.tmp.name) / 'test.db'),
                        patch.object(module, 'DB_KEY', ''), patch.object(module, '_use_sqlcipher', False)]
        for p in self.patches:
            p.start()
        module.app.config.update(TESTING=True, SECRET_KEY='test-only-key', SESSION_COOKIE_SECURE=False)
        module.init_db()
        self.client = module.app.test_client()
        self.secret = pyotp.random_base32()
        with module.get_db() as db:
            db.execute('INSERT INTO board_users(username,password_hash,totp_secret,session_version) VALUES (?,?,?,?)',
                       ('styret', generate_password_hash('a sufficiently long test password'), self.secret, 'version-1'))

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def token(self, client=None):
        client = client or self.client
        client.get('/login')
        with client.session_transaction() as s:
            return s['csrf_token']

    def login(self, code=None, password='a sufficiently long test password', client=None):
        client = client or self.client
        return client.post('/login', data=dict(username='STYRET', password=password,
                           code=code or pyotp.TOTP(self.secret).now(), csrf_token=self.token(client)))

    def test_two_factors_and_protected_data(self):
        self.assertEqual(self.client.get('/api/members', headers={'Accept':'application/json'}).status_code, 401)
        self.assertEqual(self.login(password='wrong').status_code, 401)
        self.assertEqual(self.login(code='abcdef').status_code, 401)
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.client.get('/api/members').status_code, 200)
        self.assertIn(b'X-CSRF-Token', self.client.get('/').data)

    def test_replay_rejected_across_clients(self):
        # Frys tidspunkt slik at testen ikkje kryssar eit kodeskifte.
        with patch('styre_auth.time.time', return_value=1800000010):
            code = pyotp.TOTP(self.secret).at(1800000010)
            self.assertEqual(self.login(code=code).status_code, 302)
            self.assertEqual(self.login(code=code, client=module.app.test_client()).status_code, 401)

    def test_rate_limit_persisted_and_expires(self):
        with patch('styre_auth.time.time', return_value=1800000010):
            for _ in range(5):
                self.assertEqual(self.login(password='wrong').status_code, 401)
            self.assertEqual(self.login(client=module.app.test_client()).status_code, 429)
        with patch('styre_auth.time.time', return_value=1800000311):
            self.assertEqual(self.login(code=pyotp.TOTP(self.secret).at(1800000311)).status_code, 302)

    def test_csrf_and_logout(self):
        self.assertEqual(self.client.post('/login', data={'csrf_token':'ø'}).status_code, 400)
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.client.post('/api/members', json={}).status_code, 400)
        # Gyldig token kjem fram til valideringa av medlemsdata.
        response = self.client.post('/api/members', json={}, headers={'X-CSRF-Token':self.token()})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.is_json)
        self.assertEqual(self.client.get('/logout').status_code, 405)
        self.assertEqual(self.client.post('/logout', data={'csrf_token':self.token()}).status_code, 302)
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_revoke_and_reset_invalidate_sessions(self):
        self.assertEqual(self.login().status_code, 302)
        with module.get_db() as db:
            db.execute("UPDATE board_users SET session_version='new-version'")
        self.assertEqual(self.client.get('/').status_code, 302)
        with module.get_db() as db:
            db.execute("UPDATE board_users SET session_version='version-1', active=0")
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_session_expires_after_eight_hours(self):
        self.assertEqual(self.login().status_code, 302)
        with self.client.session_transaction() as s:
            s['board_logged_in_at'] -= 8 * 3600
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_legacy_session_has_no_access(self):
        with self.client.session_transaction() as s:
            s['admin_logged_in'] = True
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_cli_enrollment_confirmation_reset_and_revoke(self):
        runner = module.app.test_cli_runner()
        secret = pyotp.random_base32()
        now = 1800000010
        password = 'another sufficiently long password'
        with patch('styre_auth.pyotp.random_base32', return_value=secret), patch('styre_auth.time.time', return_value=now):
            result = runner.invoke(args=['styrekonto','ny'], input=f'{password}\n{password}\nwrong\n')
            self.assertNotEqual(result.exit_code, 0)
            with module.get_db() as db:
                self.assertIsNone(db.execute("SELECT 1 FROM board_users WHERE username='ny'").fetchone())
            code = pyotp.TOTP(secret).at(now)
            result = runner.invoke(args=['styrekonto','ny'], input=f'{password}\n{password}\n{code}\n')
            self.assertEqual(result.exit_code, 0)
            result = runner.invoke(args=['styrekonto','ny','--nullstill'], input=f'{password}\n{password}\n{code}\n')
            self.assertEqual(result.exit_code, 0)
        self.assertEqual(runner.invoke(args=['styrekonto','ny','--sperr']).exit_code, 0)
        with module.get_db() as db:
            self.assertEqual(db.execute("SELECT active FROM board_users WHERE username='ny'").fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
