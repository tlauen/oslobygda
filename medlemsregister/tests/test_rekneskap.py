import sqlite3
import unittest
import uuid
from io import BytesIO
from pathlib import Path
from werkzeug.datastructures import FileStorage
from unittest.mock import patch
import app as module
import test_styre_auth as fixtures
from database import managed_db
from rekneskap import year_balances,ore,init_ledger
from bilag import store_receipt,MAX_FILE
from okonomi_backup import create_bundle,verify_bundle_restore

class LedgerTests(unittest.TestCase):
    setUp=fixtures.BoardAuthTests.setUp
    tearDown=fixtures.BoardAuthTests.tearDown
    token=fixtures.BoardAuthTests.token
    @property
    def service(self): return module.app.extensions['ledger']
    @property
    def root(self): return Path(self.tmp.name)/'bilag'
    def opening(self,**values): self.service.opening(2026,values,'Torbjørn','Kontoutskrift ved oppstart','styret',uuid.uuid4().hex)
    def post(self,key=None,**values):
        fields=dict(kind='income',day='2026-06-01',amount='100',account='bank',category='membership',public_text='Kontingent',evidence_note='Kontoutskrift')
        fields.update(values)
        return self.service.post(fields,'styret',key or uuid.uuid4().hex)
    def totals(self,year=2026):
        with managed_db(module.get_db) as db: return year_balances(db,year)

    def test_private_expense_repayment_reversal_and_database_immutability(self):
        self.opening(bank='1000')
        self.post(kind='private_expense',amount='350',category='events',party='Torbjørn')
        self.assertEqual(self.totals()['private'],-35000)
        refund=self.post('refund-key',kind='private_refund',amount='350',party='Torbjørn')
        self.assertEqual(self.post('refund-key',kind='private_refund',amount='350',party='Torbjørn'),refund)
        self.assertEqual(self.totals()['events'],35000);self.assertEqual(self.totals()['private'],0)
        with self.assertRaises(ValueError): self.post(kind='private_refund',amount='1',party='Torbjørn')
        reverse=self.service.reverse(refund,'2026-06-02','Feil konto','styret','reverse-key')
        self.assertEqual(self.service.reverse(refund,'2026-06-02','Feil konto','styret','reverse-key'),reverse)
        self.assertEqual(self.totals()['private'],-35000)
        with managed_db(module.get_db) as db:
            for sql in (f'DELETE FROM ledger_journals WHERE id={refund}',f'UPDATE ledger_lines SET amount_ore=0 WHERE journal_id={refund}',f'DELETE FROM ledger_lines WHERE journal_id={refund}'):
                with self.assertRaises(sqlite3.IntegrityError): db.execute(sql)

    def test_vipps_fees_and_partial_refunds(self):
        self.opening();original=self.post(account='vipps')
        self.post(kind='vipps_settlement',amount='100',fee='2')
        totals=self.totals()
        self.assertEqual(totals['bank'],9800);self.assertEqual(totals['vipps'],0)
        self.assertEqual(totals['membership'],-10000);self.assertEqual(totals['fees'],200)
        self.post(kind='refund_income',amount='30',original_id=str(original))
        self.assertEqual(self.totals()['membership'],-7000)
        with self.assertRaises(ValueError): self.post(kind='refund_income',amount='71',original_id=str(original))

    def test_opening_required_balance_guard_and_repeat_init(self):
        with self.assertRaises(ValueError): self.post()
        self.opening(bank='100',private='20')
        self.assertEqual(self.totals()['equity'],-8000);init_ledger(module.get_db)
        with managed_db(module.get_db) as db:
            j=db.execute("INSERT INTO ledger_journals(day,public_text,internal_note,actor,created_at,request_key,request_hash,evidence_note) VALUES ('2026-01-01','x','','styret','x','raw','raw','x')").lastrowid
            db.execute("INSERT INTO ledger_lines(journal_id,account,amount_ore) VALUES (?,'bank',100)",(j,))
            with self.assertRaises(sqlite3.IntegrityError): db.execute("UPDATE ledger_journals SET state='posted' WHERE id=?",(j,))

    def test_close_reopen_and_stale_reconciliation(self):
        self.opening(bank='100')
        for account,amount in [('bank','100'),('vipps','0'),('private','0')]: self.service.reconcile(2026,'2026-12-31',account,amount,'','Kontoutskrift','styret')
        self.post(amount='1')
        with self.assertRaises(ValueError): self.service.year_state(2026,True,'Avstemt','styret')
        for account,amount in [('bank','101'),('vipps','0'),('private','0')]: self.service.reconcile(2026,'2026-12-31',account,amount,'','Kontoutskrift','styret')
        self.service.year_state(2026,True,'Avstemt','styret')
        with self.assertRaises(ValueError): self.post()
        self.service.year_state(2026,False,'Ny dokumentert post','styret');self.post()

    def test_periodization_and_atomic_reversal(self):
        self.opening(bank='1000')
        original=self.post(kind='expense',category='domain',amount='365',day='2026-07-01')
        self.service.periodize(original,'2026-07-01','2027-06-30','styret','periodize-key')
        self.assertEqual(self.totals()['domain'],18400);self.assertEqual(self.totals(2027)['domain'],18100)
        self.service.reverse(original,'2026-07-02','Feil periode','styret','undo-periodized')
        self.assertEqual(self.totals()['domain'],0);self.assertEqual(self.totals(2027)['domain'],0)

    def test_upload_auth_and_backup_restore_corruption_rotation(self):
        self.assertEqual(self.client.get('/okonomi').status_code,302)
        fixtures.BoardAuthTests.login(self)
        with patch.dict(module.app.config,{'BILAG_DIR':str(self.root)}):
            self.assertEqual(self.client.post('/okonomi/bilag',data={}).status_code,400)
            response=self.client.post('/okonomi/bilag',data={'csrf_token':self.token(),'file':(BytesIO(b'%PDF-1.4\nfake receipt'),'receipt.pdf')},content_type='multipart/form-data')
            self.assertEqual(response.status_code,302);self.assertEqual(self.client.get('/okonomi').status_code,200)
            response=self.client.get('/okonomi/bilag/1');self.assertEqual(response.status_code,200)
            self.assertIn('attachment',response.headers['Content-Disposition']);self.assertEqual(response.headers['Cache-Control'],'no-store')
            with managed_db(module.get_db) as db: row=db.execute('SELECT * FROM ledger_receipts').fetchone()
            self.assertEqual((self.root/row['file_key']).stat().st_mode&0o777,0o600)
            copies=Path(self.tmp.name)/'copies';first=create_bundle(module.DB_PATH,self.root,copies,keep=1)
            verify_bundle_restore(first);second=create_bundle(module.DB_PATH,self.root,copies,keep=1)
            self.assertFalse(first.exists());self.assertTrue(second.exists())
            (self.root/row['file_key']).write_bytes(b'corrupt')
            self.assertEqual(self.client.get('/okonomi/bilag/1').status_code,409)
            with self.assertRaises(ValueError): create_bundle(module.DB_PATH,self.root,copies,keep=1)
            self.assertTrue(second.exists());self.assertEqual(list(copies.glob('.okonomi-*')),[]);verify_bundle_restore(second)
        self.client.post('/logout',data={'csrf_token':self.token()})
        self.assertEqual(self.client.get('/okonomi/bilag/1').status_code,302)

    def test_file_amount_and_idempotency_validation(self):
        for data,name in [(b'<html>bad</html>','receipt.pdf'),(b'%PDF-test','receipt.html'),(b'x'*(MAX_FILE+1),'receipt.png')]:
            with self.assertRaises(ValueError): store_receipt(module.get_db,self.root,FileStorage(stream=BytesIO(data),filename=name),'styret')
        for amount in ('NaN','Infinity','1.001','-1','0','1e99999'):
            with self.assertRaises(ValueError): ore(amount)
        self.opening();original=self.post('same-key')
        self.assertEqual(self.post('same-key'),original)
        with self.assertRaises(ValueError): self.post('same-key',amount='200')
        with self.assertRaises(ValueError): self.post(evidence_note='')
        self.assertEqual(self.totals()['membership'],-10000)

    def test_opening_correction_and_attachment(self):
        self.opening(bank='100')
        self.service.opening(2026,{'bank':'120'},'','Retta kontoutskrift','styret','fix-opening',correction=True)
        self.assertEqual(self.totals()['bank'],12000)
        receipt=store_receipt(module.get_db,self.root,FileStorage(stream=BytesIO(b'%PDF-fake'),filename='proof.pdf'),'styret')
        post=self.post()
        self.service.attach(post,receipt,'styret');self.service.attach(post,receipt,'styret')
        with managed_db(module.get_db) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ledger_attachments').fetchone()[0],1)
            with self.assertRaises(sqlite3.IntegrityError): db.execute('DELETE FROM ledger_attachments')
        fixtures.BoardAuthTests.login(self)
        self.assertEqual(self.client.get('/okonomi?year=2026&del=registrer').status_code,200)

    def test_linked_member_payment_cannot_be_deleted(self):
        self.opening();fixtures.BoardAuthTests.login(self)
        with managed_db(module.get_db) as db:
            mid=db.execute("INSERT INTO members(full_name,email,membership_type,payment_status,consent_at,created_at,updated_at) VALUES ('Test','test@example.invalid','vanleg','betalt','x','x','x')").lastrowid
            pid=db.execute("INSERT INTO payments(member_id,amount_ore,paid_at,created_at,for_year) VALUES (?,10000,'2026-06-01','2026-06-01',2026)",(mid,)).lastrowid
        self.post(payment_id=str(pid))
        with self.assertRaises(ValueError): self.post(payment_id=str(pid))
        response=self.client.delete(f'/api/members/{mid}/payments/{pid}',headers={'X-CSRF-Token':self.token()})
        self.assertEqual(response.status_code,409)
        with managed_db(module.get_db) as db: self.assertIsNotNone(db.execute('SELECT 1 FROM payments WHERE id=?',(pid,)).fetchone())

    def test_periodization_closed_target_rolls_back_entire_operation(self):
        self.opening(bank='1000')
        original=self.post(kind='expense',category='domain',amount='365',day='2026-07-01')
        with managed_db(module.get_db) as db: db.execute('INSERT INTO ledger_years(year,closed) VALUES (2027,1)')
        with self.assertRaises(ValueError): self.service.periodize(original,'2026-07-01','2027-06-30','styret','closed-period')
        self.assertNotIn('prepaid',self.totals())
        self.assertEqual(self.totals()['domain'],36500)

    def test_route_post_csrf_and_request_limit(self):
        self.opening();fixtures.BoardAuthTests.login(self)
        values=dict(action='post',year='2026',kind='income',day='2026-06-01',amount='10',account='bank',category='membership',public_text='Kontingent',evidence_note='Kontoutskrift',request_key='route-post')
        self.assertEqual(self.client.post('/okonomi',data=values).status_code,400)
        values['csrf_token']=self.token()
        self.assertEqual(self.client.post('/okonomi',data=values).status_code,302)
        self.assertEqual(self.client.get('/okonomi?year=2026&del=registrer').status_code,200)
        self.assertEqual(self.client.post('/okonomi',data={'payload':'x'*70000}).status_code,413)

    def test_standard_backup_entry_includes_receipts(self):
        import backup
        store_receipt(module.get_db,self.root,FileStorage(stream=BytesIO(b'%PDF-fake'),filename='proof.pdf'),'styret')
        copies=Path(self.tmp.name)/'standard-backup'
        args=['backup.py','--db',str(module.DB_PATH),'--directory',str(copies),'--bilag-dir',str(self.root)]
        with patch('sys.argv',args): backup.main()
        bundles=list(copies.glob('okonomi-*'));self.assertEqual(len(bundles),1)
        verify_bundle_restore(bundles[0])
        with patch('sys.argv',['backup.py','--verify',str(bundles[0])]): backup.main()

    def test_inline_upload_returns_receipt_without_posting_and_reuses_it_on_validation_error(self):
        fixtures.BoardAuthTests.login(self)
        with patch.dict(module.app.config,{'BILAG_DIR':str(self.root)}):
            response=self.client.post('/okonomi/bilag',data={'csrf_token':self.token(),'file':(BytesIO(b'%PDF-1.4 fiktivt bilag'),'kvittering.pdf')},headers={'Accept':'application/json'})
            self.assertEqual(response.status_code,201)
            rid=response.json['id'];self.assertEqual(response.json['name'],'kvittering.pdf')
            with managed_db(module.get_db) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM ledger_journals').fetchone()[0],0)
            fields=dict(csrf_token=self.token(),year='2026',action='post',request_key='inline-test-post',kind='expense',day='2026-06-01',amount='feil',category='domain',account='bank',receipt_id=str(rid),public_text='Fiktiv nettside')
            response=self.client.post('/okonomi',data=fields)
            self.assertEqual(response.status_code,400)
            self.assertIn(f'value="{rid}" selected',response.data.decode())
            with managed_db(module.get_db) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM ledger_receipts').fetchone()[0],1)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM ledger_journals').fetchone()[0],0)

    def test_post_status_explains_missing_opening_and_updates_after_setup(self):
        self.assertEqual(self.client.get('/okonomi/foringsstatus?year=2026').status_code,302)
        fixtures.BoardAuthTests.login(self)
        response=self.client.get('/okonomi/foringsstatus?year=2026')
        self.assertFalse(response.json['ready']);self.assertIn('inngåande balanse',response.json['reason'])
        raw=self.client.get('/okonomi?year=2026&del=registrer').data.decode()
        self.assertIn('Før du kan bokføre: Stadfest inngåande balanse.',raw)
        self.opening()
        self.assertTrue(self.client.get('/okonomi/foringsstatus?year=2026').json['ready'])
        self.assertFalse(self.client.get('/okonomi/foringsstatus?year=2025').json['ready'])
        self.assertEqual(self.client.get('/okonomi/foringsstatus?year=feil').status_code,400)

    def test_post_stays_in_registration_with_confirmation_and_fresh_form(self):
        self.opening();fixtures.BoardAuthTests.login(self)
        fields=dict(csrf_token=self.token(),year='2026',action='post',request_key='stay-registration',kind='income',day='2026-06-01',amount='100',category='membership',account='bank',public_text='Fiktive medlemspengar',evidence_note='Fiktiv rapport')
        response=self.client.post('/okonomi?year=2026&del=registrer',data=fields)
        self.assertEqual(response.status_code,302)
        self.assertTrue(response.location.endswith('year=2026&del=registrer#registrer-post'))
        raw=self.client.get(response.location).data.decode()
        self.assertIn('er bokført. Du kan registrere ein ny post.',raw)
        self.assertIn('name="amount" inputmode="decimal" value=""',raw)
        self.assertNotIn('stay-registration',raw)
        self.assertNotIn('id="bilag-panel"',raw)
        self.assertNotIn('id="periodisering-panel"',raw)
        for part,marker in [('oversikt','id="opningsbalanse"'),('bilag','id="bilag-panel"'),('postar','id="postar-panel"'),('kontroll','id="periodisering-panel"')]:
            response=self.client.get('/okonomi?year=2026&del='+part)
            self.assertEqual(response.status_code,200);self.assertIn(marker,response.data.decode())
        self.assertEqual(self.client.get('/okonomi?del=ukjend').status_code,400)

    def test_combined_vipps_income_gift_idempotency_and_group_reversal(self):
        self.opening()
        for category in ('membership','donations'):
            values=dict(kind='vipps_income_settled',category=category,day='2026-06-01',settlement_day='2026-06-03',amount='2000',fee='123',public_text='Fiktiv Vipps',evidence_note='Fiktiv rapport',vipps_not_booked='yes')
            key='combined-'+category
            first=self.service.post(values,'styret',key)
            self.assertEqual(self.service.post(values,'styret',key),first)
            self.assertEqual(self.totals()['vipps'],0)
            self.service.reverse(first,'2026-06-04','Fiktiv retting','styret','reverse-'+key)
            self.assertEqual(self.totals()['bank'],0)
            self.assertEqual(self.totals()[category],0)
            self.assertEqual(self.totals()['fees'],0)

    def test_combined_vipps_failure_is_atomic(self):
        self.opening()
        values=dict(kind='vipps_income_settled',category='donations',day='2026-06-01',settlement_day='2026-06-03',amount='2000',fee='123',public_text='Fiktiv gåve',evidence_note='Fiktiv rapport',vipps_not_booked='yes')
        original=self.service._post
        def fail_second(*args,**kwargs):
            if kwargs.get('source_kind')=='vipps_income_settlement':raise ValueError('Simulert feil')
            return original(*args,**kwargs)
        with patch.object(self.service,'_post',side_effect=fail_second):
            with self.assertRaises(ValueError):self.service.post(values,'styret','combined-failed')
        self.assertEqual(self.totals().get('donations',0),0)
        self.assertEqual(self.totals().get('vipps',0),0)
        with self.assertRaises(ValueError):self.service.post(dict(values,category='other_income'),'styret','combined-invalid')
