"""Oppstart skal ikkje endre eksisterande økonomihistorikk eller aktivere jobbar."""
import unittest
import app as module
import test_styre_auth as fixtures
import test_arsmote_utskrift as print_fixtures
from database import managed_db

class StartupTests(unittest.TestCase):
    setUp=fixtures.BoardAuthTests.setUp
    tearDown=fixtures.BoardAuthTests.tearDown
    versions=print_fixtures.PrintTests.versions

    def test_repeated_initialization_preserves_records_and_does_not_activate_jobs(self):
        self.versions()
        tables=('board_users','ledger_journals','ledger_lines','annual_versions','budget_versions',
                'public_ledger_versions','public_ledger_settings','payment_import_settings',
                'public_ledger_queue','annual_publication_queue','budget_publication_queue')
        # Oppstart skal bevare både historikk, kø og eksplisitte innstillingar.
        def state():
            with managed_db(module.get_db) as db:
                existing={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertTrue(set(tables).issubset(existing))
                return {table:[tuple(row) for row in db.execute('SELECT * FROM '+table+' ORDER BY rowid')]
                        for table in tables if table in existing}
        before=state()
        self.assertIn('ledger_journals',before);self.assertIn('annual_versions',before)
        module.init_db();module.init_db()
        self.assertEqual(state(),before)
        with managed_db(module.get_db) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM payment_import_settings WHERE enabled=1').fetchone()[0],0)
