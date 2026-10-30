from datetime import date
import json
import sqlite3
import unittest
from unittest.mock import Mock,patch

import app as module
import test_styre_auth as fixtures
from arsdokument import DocumentConflict
from budsjett import CATEGORIES,init_budgets,validate_budget
from database import managed_db
from publisering import validate_envelope,PublicationError,GithubDocuments

class BudgetTests(unittest.TestCase):
    setUp=fixtures.BoardAuthTests.setUp
    tearDown=fixtures.BoardAuthTests.tearDown
    token=fixtures.BoardAuthTests.token
    @property
    def service(self): return module.app.extensions['budgets']
    def create(self): self.service.create(2027,'styret')
    def current(self):
        with managed_db(module.get_db) as db: return dict(db.execute('SELECT * FROM budgets WHERE year=2027').fetchone())
    def form(self,**changes):
        form=dict(title='Budsjett 2027',meeting_year='2027',note='Offentlege føresetnader')
        form.update({'amount_'+code:'0' for code in CATEGORIES});form.update(amount_membership='5000',amount_events='2000');form.update(changes)
        return form
    def payload(self,vid):
        with managed_db(module.get_db) as db: return json.loads(db.execute('SELECT payload FROM budget_versions WHERE id=?',(vid,)).fetchone()[0])
    def ledger(self):
        service=module.app.extensions['ledger'];service.opening(2026,{},'','Dokumentert null','PRIVATE-USER','opening')
        service.post(dict(kind='income',day='2026-06-01',amount='100',account='bank',category='membership',public_text='PRIVATE-PAYER',internal_note='SECRET',evidence_note='Dokumentert'),'PRIVATE-USER','income')

    def test_missing_actuals_and_manual_budget_without_accounting(self):
        self.create();init_budgets(module.get_db)
        content=json.loads(self.current()['content']);self.assertEqual(content['previous']['state'],'not_started')
        self.service.update(2027,1,'styret','save',self.form())
        report=self.service.followup(2027)
        self.assertEqual(report['budget_result_ore'],300000);self.assertFalse(report['started'])
        with self.assertRaises(ValueError): self.service.update(2027,2,'styret','copy_previous',{'confirmed':'yes'})
        with self.assertRaises(DocumentConflict): self.service.create(2027,'styret')

    def test_previous_refresh_preserves_budget_and_frozen_comparison(self):
        self.ledger();self.create()
        self.service.update(2027,1,'styret','save',self.form())
        proposal=self.service.freeze(2027,2,'meeting','','PRIVATE-USER')
        old=self.payload(proposal);self.assertEqual(old['lines'][0]['previous_ore'],10000)
        ledger=module.app.extensions['ledger'];ledger.post(dict(kind='income',day='2026-06-02',amount='50',account='bank',category='membership',public_text='PRIVATE-PAYER',evidence_note='Dokumentert'),'styret','income2')
        self.service.update(2027,2,'styret','refresh_previous',{})
        content=json.loads(self.current()['content'])
        self.assertEqual(content['amounts']['membership'],500000);self.assertEqual(content['previous']['amounts']['membership'],15000)
        self.assertEqual(self.payload(proposal),old)
        self.assertNotIn('PRIVATE',json.dumps(old));self.assertNotIn('SECRET',json.dumps(old))

    def test_proposal_approval_and_followup_uses_approved_version(self):
        self.ledger();self.create();self.service.update(2027,1,'styret','save',self.form())
        proposal=self.service.freeze(2027,2,'meeting','','styret')
        with patch('budsjett.today',return_value=date(2027,2,24)):
            approved=self.service.freeze(2027,2,'approved','2027-02-24','styret')
            self.assertEqual(self.service.freeze(2027,2,'approved','2027-02-24','styret'),approved)
            with self.assertRaises(ValueError): self.service.freeze(2027,2,'approved','2027-02-25','styret')
            self.service.update(2027,2,'styret','save',self.form(amount_events='4000'))
            report=self.service.followup(2027)
            self.assertEqual(report['basis'],'budsjett-'+str(approved));self.assertEqual(report['budget_result_ore'],300000)
            expense=next(r for r in report['rows'] if r['category']=='events');self.assertEqual(expense['remaining_ore'],200000)
        self.assertNotEqual(approved,proposal)
        with managed_db(module.get_db) as db:
            with self.assertRaises(sqlite3.IntegrityError): db.execute('DELETE FROM budget_versions')
            with self.assertRaises(sqlite3.IntegrityError): db.execute('UPDATE budget_edits SET content=\'{}\'')

    def test_stale_revision_invalid_amount_and_explicit_copy(self):
        self.ledger();self.create()
        with self.assertRaises(ValueError): self.service.update(2027,1,'styret','save',self.form(amount_events='-1'))
        self.assertEqual(self.current()['revision'],1)
        with self.assertRaises(ValueError): self.service.update(2027,1,'styret','copy_previous',{})
        self.service.update(2027,1,'styret','copy_previous',{'confirmed':'yes'})
        self.assertEqual(json.loads(self.current()['content'])['amounts']['membership'],10000)
        with self.assertRaises(DocumentConflict): self.service.update(2027,1,'styret','save',self.form())
        with self.assertRaises(DocumentConflict): self.service.freeze(2027,1,'meeting','','styret')

    def test_public_schema_queue_worker_and_budget_stub(self):
        self.create();self.service.update(2027,1,'styret','save',self.form())
        vid=self.service.freeze(2027,2,'meeting','','styret');payload=self.payload(vid);validate_budget(payload)
        bad=dict(payload,email='secret')
        with self.assertRaises(ValueError): validate_budget(bad)
        with self.assertRaises(ValueError): validate_budget(dict(payload,result_ore=1))
        envelope=dict(schema_version=1,year=2027,versions=[payload],ledger_latest=None);validate_envelope(envelope,2027)
        self.service.enqueue(vid,'styret');self.service.enqueue(vid,'styret')
        client=Mock();client.store.return_value='sha';client.visible.return_value=True
        self.assertEqual(module.app.extensions['document_publisher'].run(client)['visible'],1)
        with patch.dict('os.environ',{'GITHUB_DOCUMENTS_TOKEN':'fake-only'}): github=GithubDocuments()
        with patch.object(github,'api',return_value={'stub':True}) as api,patch.object(github,'read',return_value=(envelope,'sha')):
            self.assertEqual(github.store(payload),'sha');self.assertEqual(api.call_args_list[0].args[1],'om/budsjett/2027/index.md')

    def test_routes_auth_csrf_edit_version_and_preview(self):
        self.assertEqual(self.client.get('/budsjett').status_code,302)
        fixtures.BoardAuthTests.login(self)
        self.assertEqual(self.client.post('/budsjett',data={'year':2027}).status_code,400)
        csrf=self.token();self.assertEqual(self.client.post('/budsjett',data={'year':2027,'csrf_token':csrf}).status_code,302)
        self.assertEqual(self.client.get('/budsjett/2027').status_code,200)
        form=self.form();form.update(action='save',revision=1,csrf_token=csrf)
        self.assertEqual(self.client.post('/budsjett/2027',data=form).status_code,302)
        stale=self.client.post('/budsjett/2027',data=form);self.assertEqual(stale.status_code,409)
        self.assertIn('5000'.encode(),stale.data)
        vid=self.service.freeze(2027,2,'meeting','','styret')
        self.assertEqual(self.client.get('/budsjett/versjon/'+str(vid)).status_code,200)
        self.assertEqual(self.client.post('/budsjett/versjon/'+str(vid),data={'csrf_token':csrf}).status_code,400)
        self.assertEqual(self.client.post('/budsjett/versjon/'+str(vid),data={'csrf_token':csrf,'confirmed':'yes'}).status_code,302)
        self.assertEqual(self.client.get('/budsjett/1902').status_code,404)

    def test_actual_spending_and_income_variance_update_without_double_counting(self):
        self.ledger();self.create();self.service.update(2027,1,'styret','save',self.form())
        ledger=module.app.extensions['ledger']
        ledger.post(dict(kind='private_expense',day='2027-03-01',amount='250',category='events',party='Torbjørn',public_text='Kake og arrangement',evidence_note='Bilag'),'styret','2027expense')
        ledger.post(dict(kind='income',day='2027-03-01',amount='1000',account='bank',category='membership',public_text='Kontingent',evidence_note='Rapport'),'styret','2027income')
        ledger.post(dict(kind='private_refund',day='2027-03-02',amount='250',party='Torbjørn',public_text='Oppgjer',evidence_note='Overføring'),'styret','2027refund')
        with patch('budsjett.today',return_value=date(2027,3,2)):
            report=self.service.followup(2027)
        expense=next(r for r in report['rows'] if r['category']=='events')
        income=next(r for r in report['rows'] if r['category']=='membership')
        self.assertEqual(expense['actual_ore'],25000);self.assertEqual(expense['remaining_ore'],175000)
        self.assertIsNone(income['remaining_ore']);self.assertEqual(income['variance_ore'],-400000)
        self.assertEqual(report['actual_result_ore'],75000)
