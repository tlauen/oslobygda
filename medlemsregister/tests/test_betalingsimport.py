from datetime import datetime,timedelta,timezone
from io import BytesIO
import sqlite3
import unittest
from unittest.mock import Mock,patch

import app as module
import test_styre_auth as fixtures
from database import managed_db
from betalingsimport import inspect_vipps,init_payment_import
from vipps_client import VippsClient,VippsError

class ImportTests(unittest.TestCase):
    setUp=fixtures.BoardAuthTests.setUp
    tearDown=fixtures.BoardAuthTests.tearDown
    token=fixtures.BoardAuthTests.token
    @property
    def service(self): return module.app.extensions['payment_import']
    @property
    def ledger(self): return module.app.extensions['ledger']
    def payment(self,order=False,environment='production',amount=10000):
        with managed_db(module.get_db) as db:
            mid=db.execute("INSERT INTO members(full_name,email,membership_type,payment_status,consent_at,created_at,updated_at) VALUES ('Fiktiv','fake@example.invalid','vanleg','betalt','x','x','x')").lastrowid
            pid=db.execute("INSERT INTO payments(member_id,amount_ore,paid_at,created_at,for_year) VALUES (?,?,'2026-01-05','2026-01-05',2027)",(mid,amount)).lastrowid
            if order:
                db.execute('''INSERT INTO signup_orders(reference,browser_key,email,details,amount_ore,for_year,environment,msn,create_key,capture_key,newsletter,created_at,status,member_id,payment_id,consent_at)
                    VALUES (?,?,?,?,?,2027,?,'123456','create','capture',0,0,'complete',?,?,'x')''',('test-ref-'+str(pid),'fake','fake@example.invalid','{}',amount,environment,mid,pid))
        return pid,mid
    def opening(self): self.ledger.opening(2026,{},'','Kontrollert oppstart','styret','opening')
    def provider(self,pid,refunded=0,timestamp='2025-12-31T23:30:00Z'):
        ref='test-ref-'+str(pid);client=Mock()
        client.get.return_value=dict(reference=ref,amount=dict(currency='NOK',value=10000),state='AUTHORIZED',aggregate={key:dict(currency='NOK',value=value) for key,value in [('authorizedAmount',10000),('capturedAmount',10000),('cancelledAmount',0),('refundedAmount',refunded)]})
        events=[dict(reference=ref,name='CAPTURED',success=True,timestamp=timestamp,amount=dict(currency='NOK',value=10000),idempotencyKey='capture-key')]
        if refunded: events.append(dict(reference=ref,name='REFUNDED',success=True,timestamp='2026-01-02T10:00:00Z',amount=dict(currency='NOK',value=refunded),idempotencyKey='refund-key'))
        client.events.return_value=events
        return client
    def eid(self,pid):
        with managed_db(module.get_db) as db: return db.execute('SELECT id FROM payment_evidence WHERE payment_id=? ORDER BY revision DESC LIMIT 1',(pid,)).fetchone()[0]

    def test_manual_date_idempotency_and_anonymous_accounting(self):
        self.opening();pid,_=self.payment()
        eid=self.service.attest(pid,'2026-01-01','bank','Bankrapport kontrollert','styret')
        jid=self.service.book(pid,eid,'styret')
        self.assertEqual(self.service.book(pid,eid,'styret'),jid)
        with managed_db(module.get_db) as db:
            row=db.execute('SELECT * FROM ledger_journals WHERE id=?',(jid,)).fetchone()
            self.assertEqual(row['day'],'2026-01-01');self.assertEqual(row['public_text'],'Medlemskontingent')
            self.assertEqual(db.execute("SELECT COUNT(*) FROM ledger_journals WHERE source_kind='membership_payment'").fetchone()[0],1)

    def test_source_date_timezone_and_get_only(self):
        self.opening();pid,_=self.payment(True);client=self.provider(pid)
        eid=self.service.fetch(pid,'styret',lambda *args:client)
        with managed_db(module.get_db) as db:
            row=db.execute('SELECT * FROM payment_evidence WHERE id=?',(eid,)).fetchone();self.assertEqual(row['day'],'2026-01-01')
        self.service.book(pid,eid,'styret');client.capture.assert_not_called();client.create.assert_not_called()
        with self.assertRaises(ValueError): self.service.attest(pid,'2026-01-01','bank','Overstyr','styret')
        api=VippsClient('id','secret','sub','123456')
        with patch.object(api,'_authenticated',return_value=[]) as call:
            api.events('test-ref-1');self.assertEqual(call.call_args.args,('GET','/epayment/v1/payments/test-ref-1/events'))

    def test_test_mode_and_refund_never_auto_booked(self):
        self.opening();pid,_=self.payment(True,environment='test')
        client=self.provider(pid)
        with self.assertRaises(ValueError): self.service.fetch(pid,'styret',lambda *a:client)
        client.get.assert_not_called()
        pid,_=self.payment(True);client=self.provider(pid,refunded=2000)
        eid=self.service.fetch(pid,'styret',lambda *a:client)
        with self.assertRaises(ValueError): self.service.book(pid,eid,'styret')
        with managed_db(module.get_db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM ledger_journals WHERE source_kind='membership_payment'").fetchone()[0],0)

    def test_existing_manual_post_links_without_new_income_and_guard_delete(self):
        self.opening();pid,mid=self.payment()
        eid=self.service.attest(pid,'2026-01-01','bank','Bankrapport','styret')
        jid=self.ledger.post(dict(kind='income',day='2026-01-01',amount='100',account='bank',category='membership',public_text='Kontingent',evidence_note='Bankrapport'),'styret','existing')
        with self.assertRaises(ValueError): self.service.book(pid,eid,'styret')
        self.service.link(pid,eid,jid,'styret');self.assertEqual(self.service.book(pid,eid,'styret'),jid)
        fixtures.BoardAuthTests.login(self)
        self.assertEqual(self.client.delete(f'/api/members/{mid}/payments/{pid}',headers={'X-CSRF-Token':self.token()}).status_code,409)
        with managed_db(module.get_db) as db:
            with self.assertRaises(sqlite3.IntegrityError): db.execute('DELETE FROM payment_ledger_links')

    def test_source_changes_missing_dates_and_duplicate_events(self):
        self.opening();pid,_=self.payment(True);client=self.provider(pid)
        client.events.return_value*=2
        self.service.fetch(pid,'styret',lambda *a:client)
        client.events.return_value[0]['timestamp']='2026-01-01T12:00:00'
        with self.assertRaises(VippsError): self.service.fetch(pid,'styret',lambda *a:client)
        manual,_=self.payment();eid=self.service.attest(manual,'2026-01-01','bank','Dokumentert','styret')
        with managed_db(module.get_db) as db: db.execute('UPDATE payments SET amount_ore=11000 WHERE id=?',(manual,))
        with self.assertRaises(ValueError): self.service.book(manual,eid,'styret')

    def test_auto_is_opt_in_and_requires_fresh_eligible_evidence(self):
        self.opening();pid,_=self.payment(True)
        self.assertEqual(self.service.run(fetch=True,client_factory=lambda *a:self.fail('Must not fetch'))['checked'],0)
        today=datetime.now(timezone.utc).astimezone(__import__('zoneinfo').ZoneInfo('Europe/Oslo')).date().isoformat()
        self.service.configure(True,today,'styret')
        client=self.provider(pid,timestamp=datetime.now(timezone.utc).isoformat())
        counts=self.service.run(fetch=True,client_factory=lambda *a:client)
        self.assertEqual(counts['booked'],1)
        self.assertEqual(self.service.run(fetch=True,client_factory=lambda *a:client)['booked'],0)
        client.get.side_effect=VippsError('Nettverk')
        self.assertEqual(self.service.run(fetch=True,client_factory=lambda *a:client)['review'],1)

    def test_routes_auth_csrf_and_attestation(self):
        self.payment();self.assertEqual(self.client.get('/okonomi/betalingar').status_code,302)
        fixtures.BoardAuthTests.login(self)
        self.assertEqual(self.client.get('/okonomi/betalingar').status_code,200)
        form=dict(action='attest',payment_id=1,day='2026-01-01',account='bank',note='Bankrapport',confirmed='yes')
        self.assertEqual(self.client.post('/okonomi/betalingar',data=form).status_code,400)
        form['csrf_token']=self.token()
        self.assertEqual(self.client.post('/okonomi/betalingar',data=form).status_code,302)

    def test_new_evidence_invalidates_preview_and_reversed_links_require_review(self):
        self.opening();pid,_=self.payment()
        first=self.service.attest(pid,'2026-01-01','bank','Bankrapport','styret')
        latest=self.service.attest(pid,'2026-01-02','bank','Retta bankrapport','styret')
        with self.assertRaises(ValueError): self.service.book(pid,first,'styret')
        jid=self.service.book(pid,latest,'styret')
        self.ledger.reverse(jid,'2026-01-03','Feilført','styret','reverse-import')
        with self.assertRaises(ValueError): self.service.book(pid,latest,'styret')

    def test_unlinked_test_payment_is_filtered_before_recording_evidence(self):
        self.opening();pid,_=self.payment(True,environment='test')
        with self.assertRaises(ValueError): self.service.attest(pid,'2026-01-01','bank','Bankrapport','styret')
        with managed_db(module.get_db) as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM payment_evidence').fetchone()[0],0)

    def test_internal_payment_list_shows_linked_member_name(self):
        pid,mid=self.payment()
        with managed_db(module.get_db) as db:db.execute('UPDATE members SET full_name=? WHERE id=?',('Intern Namneprøve',mid))
        self.assertEqual(self.client.get('/okonomi/betalingar').status_code,302)
        fixtures.BoardAuthTests.login(self)
        response=self.client.get('/okonomi/betalingar')
        self.assertEqual(response.status_code,200)
        self.assertIn('Intern Namneprøve',response.get_data(as_text=True))
        self.assertIn('Betaling '+str(pid),response.get_data(as_text=True))
