import sqlite3
import tempfile
import unittest
from pathlib import Path

from backup import create_backup, verify_restore


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'live.db'
        self.directory = self.root / 'copies'
        self.db = sqlite3.connect(self.source)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('CREATE TABLE members(id INTEGER); CREATE TABLE payments(id INTEGER); CREATE TABLE board_users(id INTEGER); INSERT INTO members VALUES (7);')
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_wal_snapshot_permissions_rotation_and_restore(self):
        first = create_backup(self.source, self.directory, keep=2)
        self.assertEqual(first.stat().st_mode & 0o777, 0o600)
        with sqlite3.connect(first) as backup:
            self.assertEqual(backup.execute('SELECT id FROM members').fetchall(), [(7,)])
        self.db.execute('INSERT INTO members VALUES (8)')  # ikkje committa
        second = create_backup(self.source, self.directory, keep=2)
        with sqlite3.connect(second) as backup:
            self.assertEqual(backup.execute('SELECT COUNT(*) FROM members').fetchone()[0], 1)
        self.db.commit()
        third = create_backup(self.source, self.directory, keep=2)
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        verify_restore(third)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM members').fetchone()[0], 2)

    def test_failed_backup_preserves_old_copies(self):
        old = create_backup(self.source, self.directory, keep=1)
        corrupt = self.root / 'corrupt.db'
        corrupt.write_bytes(b'not sqlite')
        with self.assertRaises(sqlite3.DatabaseError):
            create_backup(corrupt, self.directory, keep=1)
        self.assertTrue(old.exists())
        self.assertEqual(list(self.directory.glob('.backup-*')), [])
        with self.assertRaises(FileNotFoundError):
            create_backup(self.root / 'missing.db', self.directory)
        self.assertFalse((self.root / 'missing.db').exists())
