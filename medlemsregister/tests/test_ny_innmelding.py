import base64
from contextlib import closing
from email.utils import formatdate
import hashlib
import hmac
import unittest
from unittest.mock import Mock, patch
import app as module
import test_styre_auth as fixtures
from ny_innmelding import validate, webhook_valid
from vipps_client import VippsError

class SignupTests(unittest.TestCase):
    setUp=fixtures.BoardAuthTests.setUp
    tearDown=fixtures.BoardAuthTests.tearDown
    token=fixtures.BoardAuthTests.token
    def fields(self,**changes):
        return {**dict(fornamn='Test',etternamn='Medlem',email='test@example.org',phone='99999999',adresse='Testvegen 1',postnummer='0001',poststad='Oslo',amount='100',terms='1',newsletter='1'),**changes}
    @property
    def service(self): return module.app.extensions['signup_service']
    def new(self,environment='production'):
        with patch('ny_innmelding.credentials',return_value={'VIPPS_MSN':'123456'}):
            return self.service.new(self.fields(),'browser-key',environment,'127.0.0.1')
    def details(self,ref,captured=0):
        return dict(reference=ref,amount={'currency':'NOK','value':10000},state='AUTHORIZED',aggregate={key:{'currency':'NOK','value':value} for key,value in dict(authorizedAmount=10000,capturedAmount=captured,cancelledAmount=0,refundedAmount=0).items()})
    def reset_check(self):
        with closing(module.get_db()) as db:
            db.execute('UPDATE signup_orders SET checked_at=0');db.commit()
    def count(self,table):
        with closing(module.get_db()) as db: return db.execute('SELECT count(*) FROM '+table).fetchone()[0]
    def test_validation(self):
        self.assertEqual(validate(self.fields())[1],10000)
        for change in ({'amount':'4.99'},{'amount':'nan'},{'terms':''},{'email':'bad'},{'postnummer':'1'},{'birth_date':'3000-01-01'},{'phone':'bad'}):
            with self.assertRaises(ValueError): validate(self.fields(**change))
    def test_order_idempotence_and_duplicate_email(self):
        ref=self.new();self.assertEqual(self.new(),ref)
        with patch('ny_innmelding.credentials',return_value={'VIPPS_MSN':'123456'}):
            with self.assertRaises(ValueError): self.service.new(self.fields(),'other-browser','production','127.0.0.1')
        self.assertEqual(self.count('members'),0);self.assertEqual(self.count('signup_orders'),1)
    def test_capture_book_once_and_brevo_retry(self):
        ref=self.new();client=Mock();client.get.side_effect=[self.details(ref),self.details(ref,10000),self.details(ref,10000)]
        with patch('ny_innmelding.client_for',return_value=client):
            self.service.reconcile(ref);self.service.reconcile(ref)
        order=self.service.order(ref);self.assertEqual(order['status'],'complete')
        client.capture.assert_called_once_with(ref,10000,order['capture_key'])
        self.assertEqual(self.count('members'),1);self.assertEqual(self.count('payments'),1)
        with closing(module.get_db()) as db:
            member=db.execute('SELECT * FROM members').fetchone()
            self.assertEqual(member['email'],'test@example.org');self.assertEqual(member['membership_type'],'kul');self.assertEqual(member['payment_status'],'betalt')
            self.assertEqual(db.execute('SELECT for_year FROM payments').fetchone()[0],order['for_year'])
        with patch.object(self.service,'newsletter',side_effect=[False,True]) as news:
            self.assertFalse(self.service.sync_newsletter(ref));self.assertTrue(self.service.sync_newsletter(ref));self.assertFalse(self.service.sync_newsletter(ref));self.assertEqual(news.call_count,2)
        with closing(module.get_db()) as db:
            db.execute('UPDATE signup_orders SET newsletter=0,newsletter_done=0');db.commit()
        with patch.object(self.service,'newsletter') as news:
            self.assertFalse(self.service.sync_newsletter(ref));news.assert_not_called()
    def test_test_mode_isolation(self):
        ref=self.new('test');client=Mock();client.get.return_value=self.details(ref,10000)
        with patch('ny_innmelding.client_for',return_value=client): self.service.reconcile(ref)
        self.assertEqual(self.service.order(ref)['status'],'complete');self.assertEqual(self.count('members'),0);self.assertEqual(self.count('payments'),0)
        with patch.object(self.service,'newsletter') as news:
            self.assertFalse(self.service.sync_newsletter(ref));news.assert_not_called()
    def test_mismatched_and_refunded_payment_not_booked(self):
        ref=self.new();client=Mock();invalid=self.details(ref,10000);invalid['amount']['value']=999;client.get.return_value=invalid
        with patch('ny_innmelding.client_for',return_value=client):
            with self.assertRaises(VippsError): self.service.reconcile(ref)
        self.reset_check();refunded=self.details(ref,10000);refunded['aggregate']['refundedAmount']['value']=10000;client.get.return_value=refunded
        with patch('ny_innmelding.client_for',return_value=client): self.service.reconcile(ref)
        self.assertEqual(self.count('payments'),0);client.capture.assert_not_called()
    def test_lost_capture_response_recovered(self):
        ref=self.new();client=Mock();client.get.return_value=self.details(ref);client.capture.side_effect=VippsError('lost')
        with patch('ny_innmelding.client_for',return_value=client):
            with self.assertRaises(VippsError): self.service.reconcile(ref)
            self.reset_check();client.get.return_value=self.details(ref,10000);self.service.reconcile(ref)
        self.assertEqual(self.service.order(ref)['status'],'complete');self.assertEqual(client.capture.call_count,1)
    def test_create_retry_same_reference_and_key(self):
        ref=self.new();client=Mock();client.create.side_effect=[VippsError('lost'),{'redirectUrl':'https://api.vipps.no/test-payment'}]
        with patch('ny_innmelding.client_for',return_value=client):
            with self.assertRaises(VippsError): self.service.create(ref,'https://example.org/status')
            self.service.create(ref,'https://example.org/status')
        self.assertEqual(client.create.call_args_list[0],client.create.call_args_list[1])
    def test_closed_default_csrf_and_status_ownership(self):
        with patch.dict('os.environ',{'VIPPS_SIGNUP_MODE':'disabled'}): self.assertEqual(self.client.get('/bli-medlem').status_code,503)
        with patch.dict('os.environ',{'VIPPS_SIGNUP_MODE':'test'}):
            self.assertEqual(self.client.get('/bli-medlem').status_code,200);self.assertEqual(self.client.post('/bli-medlem',data=self.fields()).status_code,400);self.assertEqual(self.client.get('/bli-medlem/status').status_code,404)
            self.assertEqual(self.client.post('/vipps/webhook/test',json={}).status_code,401)
            with patch('ny_innmelding.credentials',return_value={'VIPPS_MSN':'123456'}): response=self.client.post('/bli-medlem',data={**self.fields(),'csrf_token':self.token()})
            self.assertEqual(response.status_code,303)
            with patch('ny_innmelding.client_for') as client:
                self.assertEqual(self.client.get('/bli-medlem/status').status_code,200);client.assert_not_called()
            self.assertEqual(module.app.test_client().get('/bli-medlem/status').status_code,404)
    def test_webhook_signature_tamper_and_replay(self):
        secret='test-secret';body=b'{"reference":"ny-test"}';now=1800000000;stamp=formatdate(now,usegmt=True)
        digest=base64.b64encode(hashlib.sha256(body).digest()).decode();signed=f'POST\n/vipps/webhook/test\n{stamp};localhost;{digest}'
        sig=base64.b64encode(hmac.new(secret.encode(),signed.encode(),hashlib.sha256).digest()).decode()
        headers={'x-ms-date':stamp,'x-ms-content-sha256':digest,'Authorization':'HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256&Signature='+sig}
        from flask import request
        with module.app.test_request_context('/vipps/webhook/test',method='POST',data=body,headers=headers):
            with patch('ny_innmelding.time.time',return_value=now): self.assertTrue(webhook_valid(request,secret))
            with patch('ny_innmelding.time.time',return_value=now+301): self.assertFalse(webhook_valid(request,secret))
        with module.app.test_request_context('/vipps/webhook/test',method='POST',data=body+b' ',headers=headers):
            with patch('ny_innmelding.time.time',return_value=now): self.assertFalse(webhook_valid(request,secret))

    def test_active_lease_prevents_second_worker(self):
        ref=self.new()
        with closing(module.get_db()) as db:
            db.execute('UPDATE signup_orders SET lease_until=9999999999');db.commit()
        with patch('ny_innmelding.client_for') as client:
            self.service.reconcile(ref);client.assert_not_called()

    def test_existing_member_never_overwritten(self):
        ref=self.new();client=Mock();client.get.return_value=self.details(ref,10000)
        with patch('ny_innmelding.client_for',return_value=client): self.service.reconcile(ref)
        with patch('ny_innmelding.credentials',return_value={'VIPPS_MSN':'123456'}):
            with self.assertRaises(ValueError): self.service.new(self.fields(fornamn='Someone else'),'other-key','production','127.0.0.1')
        with closing(module.get_db()) as db:
            self.assertEqual(db.execute('SELECT fornamn FROM members').fetchone()[0],'Test')

    def test_refund_after_completion_flagged_for_board(self):
        ref=self.new();client=Mock();client.get.return_value=self.details(ref,10000)
        with patch('ny_innmelding.client_for',return_value=client):
            self.service.reconcile(ref)
            refund=self.details(ref,10000);refund['aggregate']['refundedAmount']['value']=10000;client.get.return_value=refund
            self.service.reconcile(ref)
        self.assertEqual(self.service.order(ref)['status'],'review')
        self.assertIn('Refusjon',self.service.order(ref)['problem'])
        self.assertEqual(self.count('payments'),1) # Ingen stille sletting av bokført historikk.

    def test_terminated_with_cancelled_amount_is_unpaid_not_review(self):
        ref=self.new('test');client=Mock();result=self.details(ref)
        result['state']='TERMINATED'
        result['aggregate']['authorizedAmount']['value']=0
        result['aggregate']['cancelledAmount']['value']=10000
        client.get.return_value=result
        with patch('ny_innmelding.client_for',return_value=client): self.service.reconcile(ref)
        self.assertEqual(self.service.order(ref)['status'],'TERMINATED')
        self.assertEqual(self.count('members'),0)
        self.assertEqual(self.count('payments'),0)
        client.capture.assert_not_called()
