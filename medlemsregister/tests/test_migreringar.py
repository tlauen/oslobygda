"""Oppgraderingar skal vere atomiske, repeterbare og trygge ved parallelle startar."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from database import managed_db
from migreringar import Migration, MigrationError, migrate


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test.db"

    def db(self):
        return sqlite3.connect(self.path, timeout=10)

    def test_pending_steps_run_once_and_new_step_preserves_data(self):
        first = Migration(
            1,
            "one",
            lambda db: db.executescript(
                "CREATE TABLE records(value TEXT); INSERT INTO records VALUES ('existing');"
            ),
        )
        second = Migration(
            2, "two", lambda db: db.execute("ALTER TABLE records ADD COLUMN extra TEXT")
        )
        self.assertEqual(migrate(self.db, [first]), [1])
        self.assertEqual(migrate(self.db, [first]), [])
        self.assertEqual(migrate(self.db, [first, second]), [2])
        with closing(self.db()) as db:
            self.assertEqual(
                db.execute("SELECT * FROM records").fetchall(), [("existing", None)]
            )
            self.assertEqual(
                db.execute("SELECT version FROM schema_migrations").fetchall(),
                [(1,), (2,)],
            )

    def test_script_triggers_and_legacy_commits_cannot_escape_rollback(self):
        migrate(
            self.db,
            [
                Migration(
                    1, "one", lambda db: db.execute("CREATE TABLE records(value TEXT)")
                )
            ],
        )

        def broken(db):
            with db:
                db.executescript("""ALTER TABLE records ADD COLUMN extra TEXT;
                    CREATE TRIGGER reject_change BEFORE UPDATE ON records BEGIN
                    SELECT RAISE(ABORT,'immutable; keep original'); END;
                    INSERT INTO records VALUES ('do not commit', 'x');""")
                db.commit()
                db.close()
            raise ValueError("stop")

        with self.assertRaisesRegex(ValueError, "stop"):
            migrate(self.db, [Migration(1, "one", None), Migration(2, "two", broken)])
        with closing(self.db()) as db:
            self.assertEqual(db.execute("SELECT * FROM records").fetchall(), [])
            self.assertEqual(
                len(db.execute("PRAGMA table_info(records)").fetchall()), 1
            )
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                db.execute("SELECT version FROM schema_migrations").fetchall(), [(1,)]
            )

    def test_initial_failure_rolls_back_schema_data_and_version_table(self):
        def broken(db):
            db.executescript(
                "CREATE TABLE records(value TEXT); INSERT INTO records VALUES ('x');"
            )
            raise RuntimeError("stop")

        with self.assertRaises(RuntimeError):
            migrate(self.db, [Migration(1, "one", broken)])
        with closing(self.db()) as db:
            self.assertEqual(
                db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall(),
                [],
            )

    def test_two_startups_apply_each_step_only_once(self):
        barrier = threading.Barrier(2)

        def upgrade():
            barrier.wait(timeout=10)
            return migrate(
                self.db,
                [
                    Migration(
                        1,
                        "one",
                        lambda db: db.executescript(
                            "CREATE TABLE records(value INTEGER); INSERT INTO records VALUES (1);"
                        ),
                    )
                ],
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(upgrade) for _ in range(2)]
            self.assertEqual(sorted(f.result(timeout=15) for f in futures), [[], [1]])
        with closing(self.db()) as db:
            self.assertEqual(db.execute("SELECT * FROM records").fetchall(), [(1,)])

    def test_future_renamed_or_gapped_history_stops_without_applying_changes(self):
        first = Migration(
            1, "one", lambda db: db.execute("CREATE TABLE records(value TEXT)")
        )
        migrate(self.db, [first])
        for registry in (
            [],
            [Migration(1, "renamed", None)],
            [first, Migration(3, "three", None)],
        ):
            with self.subTest(registry=registry), self.assertRaises(MigrationError):
                migrate(self.db, registry)
        with managed_db(self.db) as db:
            db.execute("INSERT INTO schema_migrations VALUES (3,'three','test')")
        with self.assertRaises(MigrationError):
            migrate(
                self.db, [first, Migration(2, "two", None), Migration(3, "three", None)]
            )

    def test_commented_transaction_command_cannot_commit_partial_changes(self):
        def broken(db):
            db.execute("CREATE TABLE records(value TEXT)")
            db.executescript("-- A comment before a transaction command\nCOMMIT;")

        with self.assertRaises(sqlite3.DatabaseError):
            migrate(self.db, [Migration(1, "one", broken)])
        with closing(self.db()) as db:
            self.assertEqual(
                db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall(),
                [],
            )

    def test_foreign_keys_are_enforced_during_migration(self):
        def broken(db):
            db.executescript(
                "CREATE TABLE parent(id INTEGER PRIMARY KEY); CREATE TABLE child(parent_id REFERENCES parent(id));"
            )
            db.execute("INSERT INTO child VALUES (999)")

        with self.assertRaises(sqlite3.IntegrityError):
            migrate(self.db, [Migration(1, "one", broken)])


class AppMigrationTests(unittest.TestCase):
    def setUp(self):
        import test_styre_auth as fixtures

        fixtures.BoardAuthTests.setUp(self)

    def tearDown(self):
        import test_styre_auth as fixtures

        fixtures.BoardAuthTests.tearDown(self)

    def test_existing_unversioned_database_is_adopted_without_changing_history(self):
        import app as module

        def snapshot():
            with managed_db(module.get_db) as db:
                tables = [
                    r[0]
                    for r in db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name<>'schema_migrations' ORDER BY name"
                    )
                ]
                return {
                    name: [
                        tuple(r)
                        for r in db.execute(
                            'SELECT * FROM "' + name + '" ORDER BY rowid'
                        )
                    ]
                    for name in tables
                }

        before = snapshot()
        with managed_db(module.get_db) as db:
            db.execute("DROP TABLE schema_migrations")
        module.init_db()
        self.assertEqual(snapshot(), before)
        # Efter baseline skal dei historiske CREATE/ALTER-funksjonane ikkje kallast.
        with patch.object(
            module, "_initial_schema", side_effect=AssertionError("baseline ran twice")
        ):
            module.init_db()
        self.assertEqual(snapshot(), before)

    def test_old_member_columns_and_payment_year_are_upgraded_once(self):
        import app as module

        legacy = Path(self.tmp.name) / "legacy.db"
        key = Fernet.generate_key()
        with managed_db(lambda: sqlite3.connect(legacy)) as db:
            db.executescript("""CREATE TABLE members (
                id INTEGER PRIMARY KEY, full_name TEXT NOT NULL, email TEXT NOT NULL,
                phone TEXT, membership_type TEXT NOT NULL, payment_status TEXT NOT NULL,
                consent_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                INSERT INTO members VALUES (7,'Fiktiv medlem','legacy@example.invalid','',
                    'styret','ikke betalt','2026','2026-01-01','2026-01-01');
                CREATE TABLE payments(id INTEGER PRIMARY KEY, member_id INTEGER NOT NULL,
                    amount_ore INTEGER NOT NULL, paid_at TEXT NOT NULL, note TEXT, created_at TEXT NOT NULL,
                    FOREIGN KEY(member_id) REFERENCES members(id));
                INSERT INTO payments VALUES (9,7,500,'2026-01-01','','2026-01-01');""")
        with (
            patch.object(module, "DB_PATH", legacy),
            patch.dict(os.environ, MEDLEMSREGISTER_TOTP_KEY=key.decode()),
        ):
            module.init_db()
            with managed_db(module.get_db) as db:
                member = db.execute("SELECT * FROM members WHERE id=7").fetchone()
                self.assertEqual(member["fornamn"], "Fiktiv medlem")
                self.assertEqual(member["membership_type"], "styret")
                self.assertEqual(member["payment_status"], "betalt")
                payment = db.execute("SELECT * FROM payments WHERE id=9").fetchone()
                self.assertEqual(payment["amount_ore"], 500)
                self.assertEqual(
                    payment["for_year"], module._default_medlemsbetalingsar()
                )
                self.assertEqual(
                    db.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[
                        0
                    ],
                    3,
                )

    def test_wrong_or_missing_totp_key_stops_already_versioned_startup(self):
        import app as module

        key = Fernet.generate_key()
        encrypted = "enc:v1:" + Fernet(key).encrypt(b"TEST-TOTP-SECRET").decode()
        with managed_db(module.get_db) as db:
            db.execute("UPDATE board_users SET totp_secret=?", (encrypted,))
        for wrong in ("", Fernet.generate_key().decode()):
            with (
                self.subTest(key_present=bool(wrong)),
                patch.dict(os.environ, MEDLEMSREGISTER_TOTP_KEY=wrong),
            ):
                with self.assertRaises(RuntimeError):
                    module.init_db()
        with managed_db(module.get_db) as db:
            self.assertEqual(
                db.execute("SELECT totp_secret FROM board_users").fetchone()[0],
                encrypted,
            )
            self.assertEqual(
                db.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0],
                3,
            )
        with patch.dict(os.environ, MEDLEMSREGISTER_TOTP_KEY=key.decode()):
            module.init_db()
