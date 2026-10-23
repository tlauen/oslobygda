import sqlite3
import tempfile
import unittest
from pathlib import Path
from import_medlemsdata import import_data


class ImportTests(unittest.TestCase):
    def test_import_preserves_accounts_and_rejects_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = (Path(folder) / name for name in ('source.db', 'target.db'))
            schema = '''CREATE TABLE members(id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE payments(id INTEGER PRIMARY KEY, member_id INTEGER REFERENCES members(id));
            CREATE TABLE app_settings(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE medlemsar_arkiv(ar INTEGER PRIMARY KEY);'''
            with sqlite3.connect(src) as db:
                db.executescript(schema)
                db.executescript("INSERT INTO members VALUES(10,'test'); INSERT INTO payments VALUES(20,10); INSERT INTO app_settings VALUES('medlemsbetalingsar','2025');")
            with sqlite3.connect(dst) as db:
                db.executescript(schema)
                db.executescript("CREATE TABLE board_users(username TEXT, secret TEXT); INSERT INTO board_users VALUES('admin','test-secret'); INSERT INTO app_settings VALUES('medlemsbetalingsar','2026');")
            self.assertEqual(import_data(src, dst)['members'], 1)
            with sqlite3.connect(dst) as db:
                self.assertEqual(db.execute('SELECT * FROM board_users').fetchall(), [('admin','test-secret')])
                self.assertEqual(db.execute('SELECT value FROM app_settings').fetchone()[0], '2025')
            with self.assertRaisesRegex(ValueError, 'ikkje tomt'):
                import_data(src, dst)
            with sqlite3.connect(dst) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM members').fetchone()[0], 1)

    def test_invalid_source_preserves_target(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = (Path(folder) / name for name in ('source.db','target.db'))
            schema='CREATE TABLE members(id INTEGER PRIMARY KEY); CREATE TABLE payments(member_id INTEGER REFERENCES members(id)); CREATE TABLE medlemsar_arkiv(ar INTEGER); CREATE TABLE app_settings(key TEXT,value TEXT);'
            with sqlite3.connect(src) as db:
                db.executescript(schema)
                db.execute('INSERT INTO payments VALUES (999)')
            with sqlite3.connect(dst) as db:
                db.executescript(schema)
                db.executescript("CREATE TABLE board_users(username TEXT); INSERT INTO app_settings VALUES('medlemsbetalingsar','2026');")
            with self.assertRaises(ValueError):
                import_data(src,dst)
            with sqlite3.connect(dst) as db:
                self.assertEqual(db.execute('SELECT value FROM app_settings').fetchone()[0], '2026')
