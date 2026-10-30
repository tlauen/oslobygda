from copy import deepcopy
from datetime import date
import base64
import json
import unittest
from unittest.mock import Mock,patch

import app as module
import test_styre_auth as fixtures
from database import managed_db
from offentleg_rekneskap import validate_ledger
from publisering import GithubDocuments,PublicationError,PublicationConflict,validate_envelope
from arsdokument import canonical

class PublicLedgerTests(unittest.TestCase):
    setUp=fixtures.BoardAuthTests.setUp
    tearDown=fixtures.BoardAuthTests.tearDown
    token=fixtures.BoardAuthTests.token
    @property
    def ledger(self): return module.app.extensions['ledger']
    @property
    def public(self): return module.app.extensions['public_ledger']
    def setup_ledger(self): self.ledger.opening(2026,{'bank':'1000'},'','Dokumentert saldo','intern-styremedlem','opening')
    def post(self,key,**changes):
        values=dict(kind='income',day='2026-06-01',amount='100',account='bank',category='membership',public_text='Kontingent: PRIVAT BETALARNAMN',internal_note='PRIVATE@example.test VIPPS-SECRET',evidence_note='KONTONUMMER-SECRET')
        values.update(changes)
        return self.ledger.post(values,'intern-styremedlem',key)
    def payload(self,vid):
        with managed_db(module.get_db) as db: return json.loads(db.execute('SELECT payload FROM public_ledger_versions WHERE id=?',(vid,)).fetchone()[0])

    def test_aggregation_balance_detail_sums_and_no_personal_fields(self):
        self.setup_ledger();self.post('member1');self.post('member2',amount='50')
        self.post('cake',kind='private_expense',amount='350',category='events',party='PRIVAT TORBJORN',public_text='Kake til arrangement')
        report=self.public.preview(2026);raw=canonical(report)
        for secret in ('PRIVAT BETALARNAMN','PRIVAT TORBJORN','PRIVATE@example','VIPPS-SECRET','KONTONUMMER-SECRET','intern-styremedlem'):
            self.assertNotIn(secret,raw)
        self.assertEqual(report['membership_ore'],15000)
        self.assertEqual(report['result_ore'],-20000)
        self.assertEqual(report['opening']['assets_ore'],100000)
        self.assertEqual(report['ending']['equity_ore'],80000)
        self.assertEqual(len([row for row in report['transactions'] if row['kind']=='expense']),1)
        self.assertTrue(all(row['category']!='membership' for row in report['transactions']))
        validate_ledger(report,True)
        bad=deepcopy(report);bad['ending']['items'][0]['payer']='private'
        with self.assertRaises(ValueError): validate_ledger(bad,True)
        bad=deepcopy(report);bad['result_ore']+=1
        with self.assertRaises(ValueError): validate_ledger(bad,True)

    def test_activation_revision_coalescing_cutoff_and_disable(self):
        self.setup_ledger();preview=self.public.preview(2026)
        self.post('new')
        with self.assertRaises(ValueError): self.public.activate(2026,'styret',preview['source_revision'])
        first=self.public.activate(2026,'styret',self.public.preview(2026)['source_revision'])
        self.post('later',amount='25');self.public.refresh_enabled()
        with managed_db(module.get_db) as db:
            self.assertEqual(db.execute('SELECT status FROM public_ledger_queue WHERE version_id=?',(first,)).fetchone()[0],'superseded')
        self.assertEqual(self.payload(first)['membership_ore'],10000)
        self.assertEqual(self.public.refresh_enabled(),0)
        self.post('future',day='2026-12-31',amount='1000')
        with patch('offentleg_rekneskap.today',return_value=date(2026,10,29)):
            self.assertEqual(self.public.preview(2026)['membership_ore'],12500)

    def test_fixed_versions_are_frozen_and_approval_has_date(self):
        self.setup_ledger();self.post('paid')
        for account,amount in [('bank','1100'),('vipps','0'),('private','0')]: self.ledger.reconcile(2026,'2026-12-31',account,amount,'','Rapport','styret')
        self.ledger.year_state(2026,True,'Avstemt','styret')
        with patch('offentleg_rekneskap.today',return_value=date(2027,2,24)):
            rev=self.public.preview(2026)['source_revision']
            proposal=self.public.freeze(2026,'meeting',2027,'','styret',rev)
            approved=self.public.freeze(2026,'approved',2027,'2027-02-24','styret',rev)
            self.assertNotEqual(proposal,approved)
            self.assertEqual(self.public.freeze(2026,'approved',2027,'2027-02-24','styret',rev),approved)
            with self.assertRaises(ValueError): self.public.freeze(2026,'approved',2027,'2028-01-01','styret',rev)
        old=self.payload(approved)
        self.ledger.year_state(2026,False,'Ny post','styret');self.post('correction',amount='1')
        self.assertEqual(self.payload(approved),old)
        with managed_db(module.get_db) as db:
            import sqlite3
            with self.assertRaises(sqlite3.IntegrityError): db.execute('DELETE FROM public_ledger_versions WHERE id=?',(approved,))

    def test_routes_auth_csrf_review_and_status(self):
        self.setup_ledger();self.post('paid')
        self.assertEqual(self.client.get('/okonomi/offentleg/2026').status_code,302)
        fixtures.BoardAuthTests.login(self)
        self.assertEqual(self.client.get('/okonomi/offentleg/2026').status_code,200)
        form=dict(action='activate',revision=self.public.preview(2026)['source_revision'],as_of=min(date.today().isoformat(),'2026-12-31'))
        self.assertEqual(self.client.post('/okonomi/offentleg/2026',data=form).status_code,400)
        form['csrf_token']=self.token()
        self.assertEqual(self.client.post('/okonomi/offentleg/2026',data=form).status_code,400)
        form['confirmed']='yes'
        self.assertEqual(self.client.post('/okonomi/offentleg/2026',data=form).status_code,302)
        self.assertEqual(self.client.get('/okonomi/offentleg/versjon/1').status_code,200)
        self.assertEqual(self.client.post('/okonomi/offentleg/2026',data=dict(action='pause',csrf_token=self.token())).status_code,302)
        with managed_db(module.get_db) as db: self.assertEqual(db.execute('SELECT enabled FROM public_ledger_settings').fetchone()[0],0)

    def test_worker_retry_visibility_and_no_live_network(self):
        self.setup_ledger();self.post('paid')
        vid=self.public.activate(2026,'styret',self.public.preview(2026)['source_revision'])
        client=Mock();client.store.side_effect=PublicationError('Nettverksfeil')
        publisher=module.app.extensions['document_publisher']
        self.assertEqual(publisher.run(client)['failed'],1)
        client.store.side_effect=None;client.store.return_value='sha';client.visible.return_value=False
        self.assertEqual(publisher.run(client)['stored'],1)
        client.visible.return_value=True
        self.assertEqual(publisher.run(client)['visible'],1)
        with managed_db(module.get_db) as db: self.assertEqual(db.execute('SELECT status FROM public_ledger_queue WHERE version_id=?',(vid,)).fetchone()[0],'visible')

    def test_remote_merge_conflict_lost_response_and_fixed_integrity(self):
        self.setup_ledger();vid=self.public.activate(2026,'styret',self.public.preview(2026)['source_revision']);payload=self.payload(vid)
        with patch.dict('os.environ',{'GITHUB_DOCUMENTS_TOKEN':'test-only'}): client=GithubDocuments()
        empty=dict(schema_version=1,year=2026,versions=[],ledger_latest=None)
        with patch.object(client,'api',return_value={'stub':True}),patch.object(client,'read',side_effect=[(empty,None),({'schema_version':1,'year':2026,'versions':[],'ledger_latest':payload},'sha')]):
            self.assertEqual(client.store(payload),'sha')
        stored={'schema_version':1,'year':2026,'versions':[],'ledger_latest':payload}
        with patch.object(client,'api',return_value={'stub':True}) as api,patch.object(client,'read',return_value=(stored,'sha')):
            self.assertEqual(client.store(payload),'sha');self.assertEqual(api.call_count,2)
        self.post('new');self.public.refresh_enabled()
        with managed_db(module.get_db) as db: newer=json.loads(db.execute('SELECT payload FROM public_ledger_versions ORDER BY id DESC LIMIT 1').fetchone()[0])
        self.assertTrue(client.contains(dict(stored,ledger_latest=newer),payload))
        bad=deepcopy(stored);bad['private']='forbidden'
        with self.assertRaises(PublicationError): validate_envelope(bad,2026)

    def test_conflict_preserves_unrelated_versions_and_lost_put_is_recoverable(self):
        self.setup_ledger();vid=self.public.activate(2026,'styret',self.public.preview(2026)['source_revision']);payload=self.payload(vid)
        with patch.dict('os.environ',{'GITHUB_DOCUMENTS_TOKEN':'test-only'}): client=GithubDocuments()
        annual=dict(schema_version=1,version_id=1,kind='arsmelding',report_year=2026,meeting_year=2027,source_revision=1,status='meeting',title='Året',body='Tekst',decision_date=None)
        initial=dict(schema_version=1,year=2026,versions=[],ledger_latest=None)
        concurrent=dict(initial,versions=[annual]);stored=dict(concurrent,ledger_latest=payload)
        calls=[]
        def api(method,path,body=None):
            calls.append((method,path,body))
            if method=='GET': return {'stub':True}
            if len([c for c in calls if c[0]=='PUT'])==1: raise PublicationConflict('Samtidig endring')
            return {'commit':{'sha':'commit'}}
        with patch.object(client,'api',side_effect=api),patch.object(client,'read',side_effect=[(deepcopy(initial),None),(deepcopy(concurrent),'other-sha'),(deepcopy(stored),'final-sha')]):
            self.assertEqual(client.store(payload),'final-sha')
        body=[call[2] for call in calls if call[0]=='PUT'][-1]
        decoded=json.loads(base64.b64decode(body['content']))
        self.assertEqual(decoded['versions'],[annual]);self.assertEqual(body['sha'],'other-sha')
        with patch.object(client,'api',return_value={'stub':True}),patch.object(client,'read',return_value=(deepcopy(stored),'final-sha')):
            self.assertEqual(client.store(payload),'final-sha')
        mismatched=deepcopy(annual);mismatched['body']='Anna innhald'
        with self.assertRaises(PublicationError): client.contains(dict(initial,versions=[mismatched]),annual)

    def test_worker_lock_annual_queue_and_missing_credentials(self):
        self.setup_ledger()
        docs=module.app.extensions['annual_documents']
        did=docs.create('arsmelding',2026,2027,'styret');docs.save(did,1,'Året','Tekst',2027,'styret')
        docs.enqueue(docs.freeze(did,2,'meeting','','styret'),'styret')
        publisher=module.app.extensions['document_publisher'];client=Mock();client.store.return_value='sha';client.visible.return_value=True
        with managed_db(module.get_db) as db: db.execute("UPDATE publication_worker SET owner='other',expires=9999999999 WHERE id=1")
        self.assertTrue(publisher.run(client)['busy']);client.store.assert_not_called()
        with managed_db(module.get_db) as db: db.execute('UPDATE publication_worker SET owner=NULL,expires=0 WHERE id=1')
        with patch.dict('os.environ',{'GITHUB_DOCUMENTS_TOKEN':''}):
            with self.assertRaises(PublicationError): publisher.run()
        self.assertEqual(publisher.run(client)['visible'],1)
        with managed_db(module.get_db) as db: self.assertEqual(db.execute('SELECT status FROM annual_publication_queue').fetchone()[0],'visible')

    def test_validation_rejects_membership_details_and_internal_metadata(self):
        self.setup_ledger();self.post('paid');report=self.public.preview(2026)
        row=dict(date='2026-06-01',public_ref='B-'+'a'*16,kind='income',category='membership',label='Medlemskontingent',description='Ein medlem',amount_ore=10000)
        bad=deepcopy(report);bad['transactions'].append(row)
        with self.assertRaises(ValueError): validate_ledger(bad,True)
        bad=deepcopy(report);bad['opening']['items'][0]['account_number']='private'
        with self.assertRaises(ValueError): validate_ledger(bad,True)
        with self.assertRaises(ValueError): validate_ledger(report)

    def test_current_annual_report_prioritizes_approval_and_never_rolls_back(self):
        latest=dict(kind='arsmelding',status='meeting',version_id=3)
        older=dict(kind='arsmelding',status='meeting',version_id=2)
        approved=dict(kind='arsmelding',status='approved',version_id=1)
        envelope=dict(versions=[latest],ledger_latest=None)
        self.assertTrue(GithubDocuments.contains(envelope,older))
        self.assertFalse(GithubDocuments.contains(envelope,approved))
        envelope['versions']=[approved]
        self.assertTrue(GithubDocuments.contains(envelope,latest))
        self.assertFalse(GithubDocuments.contains(envelope,dict(approved,version_id=4)))

    def test_publish_ledger_button_runs_only_selected_snapshot(self):
        self.setup_ledger()
        fixtures.BoardAuthTests.login(self)
        preview=self.public.preview(2026)
        publisher=module.app.extensions['document_publisher']
        with patch.object(publisher,'run',return_value=dict(busy=False,stored=1,visible=0,failed=0)) as run:
            response=self.client.post('/okonomi/offentleg/2026',data=dict(csrf_token=self.token(),action='activate',confirmed='yes',revision=preview['source_revision'],as_of=preview['as_of']))
        self.assertEqual(response.status_code,302)
        with managed_db(module.get_db) as db:vid=db.execute('SELECT MAX(id) FROM public_ledger_versions').fetchone()[0]
        run.assert_called_once_with(target=('ledger','rekneskap-'+str(vid)),limit=1)
        with patch.object(publisher,'run') as run:
            response=self.client.post('/okonomi/offentleg/2026',data=dict(csrf_token=self.token(),action='publish',version_id=vid))
        self.assertEqual(response.status_code,400);run.assert_not_called()
