from contextlib import closing
from datetime import date
import json
import os
import time
import unittest
from unittest.mock import Mock, patch

import app as module
from database import managed_db
from epost import DeliveryUncertain
from personvern_vedlikehald import (approve_deletion, approve_free, candidates,
                                  init_retention, prepare, send_pending)
import test_ny_innmelding as signup_fixtures
import test_styre_auth as auth_fixtures


class RetentionTests(unittest.TestCase):
    setUp = auth_fixtures.BoardAuthTests.setUp
    tearDown = auth_fixtures.BoardAuthTests.tearDown
    token = auth_fixtures.BoardAuthTests.token
    login = auth_fixtures.BoardAuthTests.login
    fields = signup_fixtures.SignupTests.fields
    service = signup_fixtures.SignupTests.service
    new = signup_fixtures.SignupTests.new
    details = signup_fixtures.SignupTests.details
    NOW = 1900000000
    TODAY = date(2029, 1, 1)

    def member(self):
        ref = self.new()
        client = Mock()
        client.get.return_value = self.details(ref, 10000)
        with patch('ny_innmelding.client_for', return_value=client):
            self.service.reconcile(ref)
        return self.service.order(ref)['member_id']

    def notify(self, sender=None):
        with patch.dict(os.environ, {'SMTP_HOST':'fake','SMTP_USER':'fake','SMTP_PASSWORD':'fake'}):
            return send_pending(module.get_db, self.TODAY, sender=sender or Mock())

    def test_two_full_years_free_approval_and_no_automatic_deletion(self):
        mid = self.member()
        with managed_db(module.get_db) as db:
            self.assertFalse(candidates(db, date(2028,12,31)))
            self.assertEqual([m['id'] for m in candidates(db, self.TODAY)], [mid])
            approve_free(db, mid, 2028)
            self.assertFalse(candidates(db, self.TODAY))
            self.assertEqual(len(candidates(db, date(2031,1,1))), 1)
        prepare(module.get_db, date(2031,1,1), self.NOW)
        with managed_db(module.get_db) as db:
            self.assertEqual(db.execute('SELECT privacy_deleted FROM members WHERE id=?',(mid,)).fetchone()[0],0)

    def test_email_contains_names_and_approval_requires_sent_snapshot(self):
        mid = self.member()
        prepare(module.get_db, self.TODAY, self.NOW)
        with managed_db(module.get_db) as db:
            fingerprint = candidates(db, self.TODAY)[0]['fingerprint']
            with self.assertRaises(ValueError):
                approve_deletion(db, mid, fingerprint, self.TODAY)
        sender = Mock()
        self.assertEqual(self.notify(sender), 1)
        message = sender.call_args.args[0]
        self.assertEqual(message['To'], 'folk@oslobygda.no')
        self.assertIn('Test Medlem', message.get_content())
        self.assertIn('/personvern-oppfolging', message.get_content())
        prepare(module.get_db, self.TODAY, self.NOW+3600)
        self.assertEqual(self.notify(), 0)
        with managed_db(module.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            approve_deletion(db, mid, fingerprint, self.TODAY)
        with managed_db(module.get_db) as db:
            self.assertEqual(db.execute('SELECT privacy_deleted FROM members WHERE id=?',(mid,)).fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM payments').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT email FROM signup_orders').fetchone()[0],'')
            self.assertEqual(db.execute('SELECT count(*) FROM privacy_jobs').fetchone()[0],1)

    def test_new_payment_or_free_year_stops_old_approval(self):
        mid = self.member()
        prepare(module.get_db, self.TODAY, self.NOW)
        self.notify()
        with managed_db(module.get_db) as db:
            fingerprint = candidates(db, self.TODAY)[0]['fingerprint']
            db.execute('UPDATE payments SET for_year=2028')
            with self.assertRaises(ValueError):
                approve_deletion(db, mid, fingerprint, self.TODAY)
            db.execute('UPDATE payments SET for_year=2026')
            approve_free(db, mid, 2028)
            with self.assertRaises(ValueError):
                approve_deletion(db, mid, fingerprint, self.TODAY)

    def test_terminal_order_cleanup_boundary_and_unknown_payment_preserved(self):
        ref = self.new()
        with managed_db(module.get_db) as db:
            db.execute("UPDATE signup_orders SET status='EXPIRED',created_at=?", (self.NOW-30*86400+1,))
        self.assertEqual(prepare(module.get_db, date(2026,11,25), self.NOW),0)
        self.assertEqual(prepare(module.get_db, date(2026,11,25), self.NOW+2),1)
        order = self.service.order(ref)
        self.assertEqual(order['status'],'redacted')
        self.assertEqual(json.loads(order['details']),{})
        self.assertEqual(order['email'],'')
        self.assertEqual(order['amount_ore'],10000)
        with managed_db(module.get_db) as db:
            db.execute("UPDATE signup_orders SET status='new',create_attempted=1,created_at=?", (self.NOW-40*86400,))
        self.assertEqual(prepare(module.get_db, date(2026,11,25), self.NOW),0)
        self.assertEqual(self.service.order(ref)['status'],'new')

    def test_review_alert_deduplicated_and_uncertain_delivery_not_retried(self):
        ref = self.new()
        with managed_db(module.get_db) as db:
            db.execute("UPDATE signup_orders SET status='review',problem='Kontroller refusjon'")
        prepare(module.get_db, self.TODAY, self.NOW)
        sender=Mock(side_effect=DeliveryUncertain())
        self.assertEqual(self.notify(sender),0)
        self.assertEqual(self.notify(sender),0)
        self.assertEqual(sender.call_count,1)
        self.assertIn(ref,sender.call_args.args[0].get_content())
        prepare(module.get_db,self.TODAY,self.NOW+3600)
        with managed_db(module.get_db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM board_notifications').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT state FROM board_notifications').fetchone()[0],'uncertain')

    def test_rejected_email_retries_and_parallel_worker_cannot_claim_it(self):
        self.member()
        prepare(module.get_db,self.TODAY,self.NOW)
        self.assertEqual(self.notify(Mock(side_effect=OSError())),0)
        def send(message):
            self.assertEqual(self.notify(),0)
        self.assertEqual(self.notify(send),1)

    def test_unpaid_member_grace_and_active_board_account_protected(self):
        mid=self.member()
        with managed_db(module.get_db) as db:
            db.execute('DELETE FROM payments')
            self.assertFalse(candidates(db,date(2028,12,31)))
            self.assertEqual(len(candidates(db,self.TODAY)),1)
            db.execute('UPDATE board_users SET member_id=?',(mid,))
            self.assertFalse(candidates(db,self.TODAY))

    def test_legacy_paid_without_payment_row_is_covered_for_known_year(self):
        mid=self.member()
        with managed_db(module.get_db) as db:
            db.execute('DELETE FROM payments')
            db.execute("UPDATE members SET payment_status='betalt',created_at='2020-01-01'")
            db.execute("DELETE FROM app_settings WHERE key='free_years_migrated'")
        init_retention(module.get_db,lambda db:2026)
        with managed_db(module.get_db) as db:
            self.assertFalse(candidates(db,date(2028,12,31)))
            self.assertEqual(candidates(db,self.TODAY)[0]['last_covered'],2026)
        self.login()
        self.assertEqual(self.client.put(f'/api/members/{mid}',json={'payment_status':'betalt'},headers={'X-CSRF-Token':self.token()}).status_code,200)
        with managed_db(module.get_db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM payments').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT for_year FROM paid_membership_years').fetchone()[0],2026)

    def test_legacy_gratis_migrated_once(self):
        mid=self.member()
        with managed_db(module.get_db) as db:
            db.execute("UPDATE members SET payment_status='gratis'")
            db.execute("DELETE FROM app_settings WHERE key='free_years_migrated'")
        init_retention(module.get_db,lambda db:2026)
        init_retention(module.get_db,lambda db:2029)
        with managed_db(module.get_db) as db:
            self.assertEqual([r[0] for r in db.execute('SELECT for_year FROM free_membership_years WHERE member_id=?',(mid,))],[2026])

    def test_free_approval_via_member_form_is_annual_and_year_close_does_not_renew_it(self):
        mid=self.member()
        self.login()
        headers={'X-CSRF-Token':self.token()}
        self.assertEqual(self.client.put(f'/api/members/{mid}', json={'payment_status':'gratis'}, headers=headers).status_code,200)
        with managed_db(module.get_db) as db:
            self.assertEqual(db.execute('SELECT for_year FROM free_membership_years WHERE member_id=?',(mid,)).fetchone()[0],2026)
        response=self.client.post('/api/medlemsar/lukk', json={'bekreft_ar':2026}, headers=headers)
        self.assertEqual(response.status_code,200)
        with managed_db(module.get_db) as db:
            self.assertEqual(db.execute('SELECT payment_status FROM members WHERE id=?',(mid,)).fetchone()[0],'ikkje betalt')
            self.assertEqual(db.execute('SELECT count(*) FROM free_membership_years WHERE for_year=2027').fetchone()[0],0)

    def test_review_lock_and_recorded_payment_prevent_order_cleanup(self):
        ref=self.new()
        for changes in [dict(status='review'), dict(status='EXPIRED',lease_until=self.NOW+100),
                        dict(status='TERMINATED',payment_id=123),dict(status='EXPIRED',confirmation_status='review')]:
            with managed_db(module.get_db) as db:
                db.execute("UPDATE signup_orders SET status='EXPIRED',lease_until=0,payment_id=NULL,confirmation_status='pending',created_at=?",(self.NOW-40*86400,))
                for key,value in changes.items():db.execute(f'UPDATE signup_orders SET {key}=?',(value,))
            self.assertEqual(prepare(module.get_db,self.TODAY,self.NOW),0)
            self.assertNotEqual(self.service.order(ref)['status'],'redacted')

    def test_approval_route_requires_login_csrf_and_explicit_confirmation(self):
        self.assertEqual(self.client.get('/personvern-oppfolging').status_code,302)
        self.login()
        self.assertEqual(self.client.get('/personvern-oppfolging').status_code,200)
        self.assertEqual(self.client.post('/personvern-oppfolging',data={'action':'delete'}).status_code,400)
        self.assertEqual(self.client.post('/personvern-oppfolging',data={'action':'delete','csrf_token':self.token()}).status_code,400)
