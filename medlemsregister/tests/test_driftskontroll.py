import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cryptography.fernet import Fernet
from database import managed_db
from driftskontroll import inspect


class OperationsCheckTests(unittest.TestCase):
    def test_read_only_report_counts_invalid_encryption_without_disclosing_values(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            key = Fernet.generate_key()
            secret = 'SECRET-MUST-NOT-APPEAR'
            (root / '.env').write_text('MEDLEMSREGISTER_TOTP_KEY=' + key.decode() + '\nVIPPS_SIGNUP_MODE=production\n')
            path = root / 'medlemsregister.db'
            with managed_db(lambda: sqlite3.connect(path)) as db:
                db.executescript('CREATE TABLE board_users(totp_secret TEXT); CREATE TABLE board_enrollment(totp_secret TEXT); CREATE TABLE members(name TEXT); CREATE TABLE payments(id INTEGER); CREATE TABLE signup_orders(environment TEXT,status TEXT);')
                db.executemany('INSERT INTO board_users VALUES (?)', [('enc:v1:' + Fernet(key).encrypt(secret.encode()).decode(),), (secret,), ('enc:v1:invalid',)])
                db.execute('INSERT INTO signup_orders VALUES (?,?)', (secret, secret))
            original = path.read_bytes()
            report = inspect(root, root / 'missing-logs')
            self.assertEqual(report['totp']['board_users'], {'total': 3, 'encrypted': 2, 'readable': 1})
            self.assertTrue(report['database_integrity_ok'])
            self.assertEqual(report['orders'], [{'environment': 'unknown', 'status': 'unknown', 'count': 1}])
            self.assertNotIn(secret, json.dumps(report))
            self.assertNotIn(key.decode(), json.dumps(report))
            self.assertEqual(path.read_bytes(), original)

    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(sqlite3.OperationalError):
                inspect(root, root)
            self.assertFalse((root / 'medlemsregister.db').exists())
