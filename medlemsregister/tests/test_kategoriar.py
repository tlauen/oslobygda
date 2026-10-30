import json
import unittest
from datetime import date
from unittest.mock import patch
import app as module
import test_styre_auth as fixtures
import test_arsmote_utskrift as print_fixtures
from rekneskap import ACCOUNTS
from offentleg_rekneskap import validate_ledger
from budsjett import validate_budget
from database import managed_db

class CategoryTests(unittest.TestCase):
    setUp=fixtures.BoardAuthTests.setUp
    tearDown=fixtures.BoardAuthTests.tearDown
    token=fixtures.BoardAuthTests.token
    versions=print_fixtures.PrintTests.versions
    # Reuse fixture helpers, not inherited test methods.
    def test_interest_and_category_notes_in_views(self):
        self.versions();fixtures.BoardAuthTests.login(self)
        module.app.extensions['ledger'].post(dict(kind='income',day='2026-01-02',amount='12,50',account='bank',category='interest',public_text='Bankrenter',evidence_note='Kontoutskrift'),'styret','renter')
        with patch('offentleg_rekneskap.today',return_value=date(2026,12,31)):
            report=module.app.extensions['public_ledger'].preview(2026)
        self.assertEqual(next(x['amount_ore'] for x in report['categories'] if x['category']=='interest'),1250)
        for path in ('/okonomi?year=2026&del=registrer','/okonomi/offentleg/2026','/budsjett/2027'):
            response=self.client.get(path);self.assertEqual(response.status_code,200)
            self.assertIn('Renteinnkome',response.data.decode());self.assertIn('kontoutskrifta',response.data.decode())

    def test_only_agreed_categories_and_no_legacy_notes(self):
        self.assertEqual({code for code,(_,kind) in ACCOUNTS.items() if kind in ('income','expense')},
                         {'membership','grants','donations','event_income','interest','other_income','domain','events','fees','other_expense'})
        self.assertEqual(set(module.app.jinja_env.globals['category_notes']),
                         {code for code,(_,kind) in ACCOUNTS.items() if kind in ('income','expense')})
