from contextlib import closing
from datetime import date
import json
import unittest
from unittest.mock import patch,Mock
import app as module
import test_styre_auth as fixtures
from kontingent import payable,save_period,period
from vipps_client import VippsError

class RenewalTests(unittest.TestCase):
    setUp=fixtures.BoardAuthTests.setUp
    tearDown=fixtures.BoardAuthTests.tearDown
    token=fixtures.BoardAuthTests.token
    @property
    def service(self):return module.app.extensions['signup_service']
    @property
    def links(self):return module.app.extensions['renewals']
    def member(self,kind='vanleg'):
        with closing(module.get_db()) as db:
            mid=db.execute("INSERT INTO members(full_name,fornamn,email,membership_type,payment_status,consent_at,created_at,updated_at) VALUES ('Medlem','Test','member@example.org',?,'ikkje betalt','now','now','now')",(kind,)).lastrowid;db.commit();return mid
    def policy(self,year=2027,minimum='50',threshold='100'):
        with closing(module.get_db()) as db:
            save_period(db,dict(year=str(year),minimum=minimum,threshold=threshold,opens_on=f'{year}-02-20',approved='1',approved_on=f'{year}-02-20'));db.commit()
    def issue(self,mid,year=2026,environment='production'):
        _,token,_=self.links.issue(mid,year,environment);return token,self.links.resolve(token)
    def result(self,ref,ore):
        return dict(reference=ref,state='AUTHORIZED',amount={'currency':'NOK','value':ore},aggregate={k:{'currency':'NOK','value':v} for k,v in dict(authorizedAmount=ore,capturedAmount=ore,cancelledAmount=0,refundedAmount=0).items()})
    def renew(self,link,amount='50'):
        with patch('ny_innmelding.credentials',return_value={'VIPPS_MSN':'123456'}):return self.service.renew(link,{'amount':amount,'terms':'1'})
    def test_2027_closed_until_meeting_and_future_year_never_prepayable(self):
        with closing(module.get_db()) as db:
            with patch('kontingent.today',return_value=date(2027,1,5)):
                with self.assertRaises(ValueError):payable(db,2027)
            with patch('kontingent.today',return_value=date(2026,10,28)):
                with self.assertRaises(ValueError):save_period(db,dict(year='2027',minimum='50',threshold='100',opens_on='2027-02-20',approved='1',approved_on='2026-10-28'))
            with patch('kontingent.today',return_value=date(2027,2,20)):
                save_period(db,dict(year='2027',minimum='50',threshold='100',opens_on='2027-02-20',approved='1',approved_on='2027-02-20'))
                save_period(db,dict(year='2028',minimum='75',threshold='100',opens_on='2028-01-01',approved='1',approved_on='2027-02-20'))
                self.assertEqual(payable(db,2027)['minimum_ore'],5000)
                with self.assertRaises(ValueError):payable(db,2028)
            with patch('kontingent.today',return_value=date(2028,1,1)):
                self.assertEqual(payable(db,2028)['minimum_ore'],7500)
    def test_renewal_existing_member_and_styret_preserved(self):
        mid=self.member('styret');_,link=self.issue(mid)
        ref=self.renew(link,'6');client=Mock();client.get.return_value=self.result(ref,600)
        with patch('ny_innmelding.client_for',return_value=client):self.service.reconcile(ref);self.service.reconcile(ref)
        with closing(module.get_db()) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM members').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM payments').fetchone()[0],1)
            m=db.execute('SELECT * FROM members WHERE id=?',(mid,)).fetchone()
            self.assertEqual(m['membership_type'],'styret');self.assertEqual(m['payment_status'],'betalt')
        with self.assertRaises(ValueError):self.renew(link,'7')
    def test_each_year_can_change_type_and_link_is_year_bound(self):
        mid=self.member('kul')
        with patch('kontingent.today',return_value=date(2027,2,20)):
            self.policy();_,link=self.issue(mid,2027)
            with self.assertRaises(ValueError):self.renew(link,'49.99')
            ref=self.renew(link,'50');client=Mock();client.get.return_value=self.result(ref,5000)
            with closing(module.get_db()) as db:
                db.execute("UPDATE app_settings SET value='2027' WHERE key='medlemsbetalingsar'");db.commit()
            with patch('ny_innmelding.client_for',return_value=client):self.service.reconcile(ref)
            with closing(module.get_db()) as db:
                self.assertEqual(db.execute('SELECT membership_type FROM members WHERE id=?',(mid,)).fetchone()[0],'vanleg')
        with patch('kontingent.today',return_value=date(2028,1,1)):
            with self.assertRaises(ValueError):self.renew(link,'150')
    def test_reissue_revokes_token_but_reuses_pending_order(self):
        mid=self.member();old_token,old=self.issue(mid);ref=self.renew(old,'5')
        new_token,new=self.issue(mid);self.assertIsNone(self.links.resolve(old_token))
        self.assertIsNotNone(self.links.resolve(new_token));self.assertIsNone(self.links.resolve('x'*43))
        self.assertEqual(self.renew(new,'20'),ref)
        self.assertEqual(self.service.order(ref)['amount_ore'],2000)
    def test_stale_form_gate_checked_again_before_vipps(self):
        mid=self.member();_,link=self.issue(mid);ref=self.renew(link,'5')
        with closing(module.get_db()) as db:
            db.execute('UPDATE membership_periods SET approved=0 WHERE year=2026');db.commit()
        with patch('ny_innmelding.client_for') as client:
            with self.assertRaises(VippsError):self.service.create(ref,'https://example.org/status')
            client.assert_not_called()
    def test_test_renewal_never_updates_real_member(self):
        mid=self.member();_,link=self.issue(mid,environment='test');ref=self.renew(link,'100')
        client=Mock();client.get.return_value=self.result(ref,10000)
        with patch('ny_innmelding.client_for',return_value=client):self.service.reconcile(ref)
        with closing(module.get_db()) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM payments').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT payment_status FROM members').fetchone()[0],'ikkje betalt')
    def test_token_exchange_no_pii_and_requires_csrf(self):
        mid=self.member();token,link=self.issue(mid,environment='test')
        with patch.dict('os.environ',{'VIPPS_SIGNUP_MODE':'test'}):
            self.assertEqual(self.client.get('/forny/'+token).status_code,303)
            response=self.client.get('/forny');self.assertEqual(response.status_code,200)
            self.assertNotIn(b'member@example.org',response.data)
            self.assertEqual(self.client.post('/forny',data={'amount':'5','terms':'1'}).status_code,400)
            with patch('ny_innmelding.credentials',return_value={'VIPPS_MSN':'123456'}):
                self.assertEqual(self.client.post('/forny',data={'amount':'5','terms':'1','csrf_token':self.token()}).status_code,303)
            self.assertEqual(module.app.test_client().get('/bli-medlem/status').status_code,404)
        self.assertEqual(self.client.get('/kontingent').status_code,302)
    def test_new_signup_closed_in_january_and_dynamic_minimum(self):
        with patch('kontingent.today',return_value=date(2027,1,1)),patch.dict('os.environ',{'VIPPS_SIGNUP_MODE':'test'}):
            page=self.client.get('/bli-medlem');self.assertIn('ikkje open',page.data.decode())
            with patch('ny_innmelding.credentials',return_value={'VIPPS_MSN':'123456'}):
                with self.assertRaises(ValueError):self.service.new({},'key','test','ip')

    def test_admin_page_and_aborted_renewal_restart(self):
        fixtures.BoardAuthTests.login(self)
        self.assertEqual(self.client.get('/kontingent').status_code,200)
        mid=self.member();token,link=self.issue(mid,environment='test')
        with patch.dict('os.environ',{'VIPPS_SIGNUP_MODE':'test'}):
            self.client.get('/forny/'+token)
            ref=self.renew(link,'5')
            with closing(module.get_db()) as db:
                db.execute("UPDATE signup_orders SET status='ABORTED' WHERE reference=?",(ref,));db.commit()
            with self.client.session_transaction() as s:s['signup_reference']=ref
            response=self.client.post('/bli-medlem/prov-igjen',data={'csrf_token':self.token()})
            self.assertEqual(response.location,'/forny')
            next_ref=self.renew(link,'10');self.assertNotEqual(ref,next_ref)

    def test_policy_locked_after_production_creation_attempt(self):
        mid=self.member();_,link=self.issue(mid);ref=self.renew(link,'5')
        with closing(module.get_db()) as db:
            db.execute('UPDATE signup_orders SET create_attempted=1 WHERE reference=?',(ref,));db.commit()
            with self.assertRaises(ValueError):save_period(db,dict(year='2026',minimum='10',threshold='20',opens_on='2026-01-01',approved='1',approved_on='2026-01-01'))
