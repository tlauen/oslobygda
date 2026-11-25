from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock

from database import managed_db


class DatabaseLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test.db"
        self.statements = []
        with managed_db(self.db) as db:
            db.execute("CREATE TABLE records(value TEXT)")

    def db(self):
        connection = sqlite3.connect(self.path)
        connection.set_trace_callback(self.statements.append)
        return connection

    def values(self):
        with closing(self.db()) as db:
            return db.execute("SELECT value FROM records").fetchall()

    def assert_closed(self, db):
        with self.assertRaises(sqlite3.ProgrammingError):
            db.execute("SELECT 1")
        # Ei ny skrivelås skal kunne takast med ein gong, utan å vente på GC.
        with managed_db(lambda: sqlite3.connect(self.path, timeout=0)) as other:
            other.execute("BEGIN IMMEDIATE")

    def test_default_commits_success_and_rolls_back_errors(self):
        with managed_db(self.db) as db:
            db.execute("INSERT INTO records VALUES ('kept')")
        self.assert_closed(db)
        with self.assertRaisesRegex(ValueError, "failure"):
            with managed_db(self.db) as failed:
                failed.execute("INSERT INTO records VALUES ('rollback')")
                raise ValueError("failure")
        self.assert_closed(failed)
        self.assertEqual(self.values(), [("kept",)])
        self.assertIn("ROLLBACK", self.statements)

    def test_manual_mode_rolls_back_uncommitted_early_return(self):
        def early_return():
            with managed_db(self.db, commit_on_success=False) as db:
                db.execute("INSERT INTO records VALUES ('rollback')")
                return db

        connection = early_return()
        self.assert_closed(connection)
        self.assertEqual(self.values(), [])
        self.assertIn("ROLLBACK", self.statements)

    def test_manual_checkpoint_survives_later_failure_but_partial_work_does_not(self):
        with self.assertRaisesRegex(ValueError, "provider failed"):
            with managed_db(self.db, commit_on_success=False) as db:
                db.execute("INSERT INTO records VALUES ('durable checkpoint')")
                db.commit()
                db.execute("INSERT INTO records VALUES ('unfinished')")
                raise ValueError("provider failed")
        self.assert_closed(db)
        self.assertEqual(self.values(), [("durable checkpoint",)])
        self.assertIn("ROLLBACK", self.statements)

    def test_deferred_foreign_key_commit_failure_rolls_back_and_releases_lock(self):
        def database():
            db = self.db()
            db.execute("PRAGMA foreign_keys=ON")
            return db

        with managed_db(database) as db:
            db.executescript(
                "CREATE TABLE parent(id INTEGER PRIMARY KEY); CREATE TABLE child(parent_id INTEGER REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED);"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            with managed_db(database) as failed:
                failed.execute("INSERT INTO child VALUES (999)")
        self.assert_closed(failed)
        with closing(database()) as check:
            self.assertEqual(
                check.execute("SELECT COUNT(*) FROM child").fetchone()[0], 0
            )
        self.assertIn("ROLLBACK", self.statements)

    def test_connection_closes_even_when_commit_or_rollback_fails(self):
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(
            side_effect=sqlite3.OperationalError("commit failed")
        )
        with self.assertRaises(sqlite3.OperationalError):
            with managed_db(lambda: connection):
                pass
        connection.close.assert_called_once()
        connection = Mock(in_transaction=True)
        connection.rollback.side_effect = sqlite3.OperationalError("rollback failed")
        with self.assertRaises(sqlite3.OperationalError):
            with managed_db(lambda: connection, commit_on_success=False):
                pass
        connection.close.assert_called_once()
