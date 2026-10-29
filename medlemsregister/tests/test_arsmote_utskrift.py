import unittest
from unittest.mock import patch
from datetime import date
import app as module
import test_styre_auth as fixtures
from budsjett import CATEGORIES
from database import managed_db

class PrintTests(unittest.TestCase):
    setUp=fixtures.BoardAuthTests.setUp
    tearDown=fixtures.BoardAuthTests.tearDown
    token=fixtures.BoardAuthTests.token

    def versions(self):
        docs=module.app.extensions['annual_documents'];did=docs.create('arsmelding',2026,2027,'PRIVATE-USER')
        text='Innleiing med æ, ø og å.\n\n<script>fiktiv</script>\n'+'Lang omtale. '*400
        docs.save(did,1,'Årsmelding 2026',text,2027,'PRIVATE-USER')
        annual=docs.freeze(did,2,'meeting','','PRIVATE-USER')
        budgets=module.app.extensions['budgets'];budgets.create(2027,'PRIVATE-USER')
        form=dict(title='Budsjett 2027',meeting_year=2027,note='Budsjettomtale med æøå')
        form.update({'amount_'+code:'0' for code in CATEGORIES});form['amount_membership']='5000';form['amount_events']='2000'
        budgets.update(2027,1,'PRIVATE-USER','save',form)
        budget=budgets.freeze(2027,2,'meeting','','PRIVATE-USER')
        ledger=module.app.extensions['ledger'];ledger.opening(2026,{},'','Private grunnlag','PRIVATE-USER','open')
        ledger.post(dict(kind='income',day='2026-01-01',amount='100',account='bank',category='membership',public_text='PRIVATE-PAYER',internal_note='INTERNAL-SECRET',evidence_note='Private grunnlag'),'PRIVATE-USER','income')
        public=module.app.extensions['public_ledger'];financial=public.activate(2026,'PRIVATE-USER',public.preview(2026)['source_revision'])
        return did,text,annual,budget,financial

    def test_print_all_types_without_internal_controls_or_private_fields(self):
        did,text,annual,budget,financial=self.versions();fixtures.BoardAuthTests.login(self)
        for kind,vid in [('arsmelding',annual),('budsjett',budget),('rekneskap',financial)]:
            response=self.client.get(f'/arsmote/utskrift/{kind}/{vid}')
            self.assertEqual(response.status_code,200);self.assertEqual(response.headers['Cache-Control'],'no-store')
            raw=response.data.decode()
            self.assertIn('arsmote-utskrift.css',raw);self.assertIn('window.print()',raw)
            self.assertNotIn('<form',raw);self.assertNotIn('csrf_token',raw)
            for private in ('PRIVATE-USER','PRIVATE-PAYER','INTERNAL-SECRET','Private grunnlag'): self.assertNotIn(private,raw)
        raw=self.client.get(f'/arsmote/utskrift/arsmelding/{annual}').data.decode()
        self.assertIn('&lt;script&gt;fiktiv&lt;/script&gt;',raw);self.assertNotIn('<script>fiktiv</script>',raw)
        self.assertIn('Rapportår 2026',raw);self.assertIn('Møteår 2027',raw)
        self.assertEqual(raw.count('Lang omtale.'),400)

    def test_print_unchanged_after_edit_and_no_database_side_effects(self):
        did,text,annual,budget,financial=self.versions();fixtures.BoardAuthTests.login(self)
        before=self.client.get(f'/arsmote/utskrift/arsmelding/{annual}').data
        module.app.extensions['annual_documents'].save(did,2,'Ny tittel','Endra utkast',2027,'styret')
        self.assertEqual(self.client.get(f'/arsmote/utskrift/arsmelding/{annual}').data,before)
        with managed_db(module.get_db) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM annual_publication_queue').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM budget_publication_queue').fetchone()[0],0)

    def test_requires_login_and_rejects_unknown_or_missing_versions(self):
        self.assertEqual(self.client.get('/arsmote/utskrift/arsmelding/1').status_code,302)
        fixtures.BoardAuthTests.login(self)
        for path in ('/arsmote/utskrift/unknown/1','/arsmote/utskrift/arsmelding/999','/arsmote/utskrift/budsjett/999','/arsmote/utskrift/rekneskap/999'):
            self.assertEqual(self.client.get(path).status_code,404)

    def test_approved_budget_print_contains_decision_and_exact_totals(self):
        did,text,annual,budget,financial=self.versions();fixtures.BoardAuthTests.login(self)
        with patch('budsjett.today',return_value=date(2027,2,24)):
            approved=module.app.extensions['budgets'].freeze(2027,2,'approved','2027-02-24','styret')
        raw=self.client.get(f'/arsmote/utskrift/budsjett/{approved}').data.decode()
        self.assertIn('Godkjend av årsmøtet',raw);self.assertIn('Vedtaksdato 2027-02-24',raw)
        self.assertIn('5 000,00 kr',raw);self.assertIn('2 000,00 kr',raw);self.assertIn('3 000,00 kr',raw)
        self.assertIn('nulltal er ikkje ein stadfesta årsrekneskap',raw)
