from contextlib import closing
from unittest.mock import Mock, patch
import smtplib

import test_ny_innmelding as signup_fixtures
from epost import DeliveryUncertain, send_message
from innmelding_epost import send_confirmation
from email.message import EmailMessage
import unittest
import app as module


class SignupReceiptTests(unittest.TestCase):
    setUp = signup_fixtures.SignupTests.setUp
    tearDown = signup_fixtures.SignupTests.tearDown
    fields = signup_fixtures.SignupTests.fields
    new = signup_fixtures.SignupTests.new
    details = signup_fixtures.SignupTests.details
    service = signup_fixtures.SignupTests.service
    # Bruk same isolerte database og Vipps-fixture, inga ekte e-postsending.
    def paid(self, newsletter='1', environment='production', details=None):
        ref = self.new(environment)
        client = Mock()
        result = self.details(ref, 10000)
        if details is not None:
            result['userDetails'] = details
        client.get.return_value = result
        with patch('ny_innmelding.client_for', return_value=client):
            self.service.reconcile(ref)
        with closing(module.get_db()) as db:
            db.execute('UPDATE signup_orders SET newsletter=? WHERE reference=?', (int(newsletter), ref))
            db.commit()
        return ref

    def test_receipt_once_even_without_newsletter_and_only_after_paid(self):
        ref = self.new()
        with patch.object(self.service, 'confirmation', return_value=True) as sender:
            self.assertFalse(self.service.send_confirmation(ref))
            sender.assert_not_called()
        client = Mock()
        client.get.return_value = self.details(ref, 10000)
        with patch('ny_innmelding.client_for', return_value=client):
            self.service.reconcile(ref)
        with closing(module.get_db()) as db:
            db.execute('UPDATE signup_orders SET newsletter=0'); db.commit()
        with patch.object(self.service, 'confirmation', return_value=True) as sender:
            self.assertTrue(self.service.send_confirmation(ref))
            self.assertFalse(self.service.send_confirmation(ref))
            sender.assert_called_once()
        self.assertEqual(self.service.order(ref)['confirmation_status'], 'sent')

    def test_failed_delivery_retries_but_uncertain_requires_review(self):
        ref = self.paid()
        with patch.object(self.service, 'confirmation', side_effect=[smtplib.SMTPAuthenticationError(535,b'no'), DeliveryUncertain('unknown'), True]) as sender:
            self.assertFalse(self.service.send_confirmation(ref))
            self.assertEqual(self.service.order(ref)['confirmation_status'], 'pending')
            self.assertFalse(self.service.send_confirmation(ref))
            self.assertEqual(self.service.order(ref)['confirmation_status'], 'review')
            self.assertFalse(self.service.send_confirmation(ref))
            self.assertEqual(sender.call_count, 2)

    def test_test_mode_never_sends_or_stores_payer(self):
        ref = self.paid(environment='test', details={'firstName':'Payer','mobileNumber':'99999999'})
        with patch.object(self.service, 'confirmation') as sender:
            self.assertFalse(self.service.send_confirmation(ref))
            sender.assert_not_called()
        self.assertEqual(self.service.order(ref)['payer_name'], '')

    def test_payer_separate_from_member_and_erased(self):
        ref = self.paid(details={'firstName':'Different','lastName':'Payer','mobileNumber':'4799999999','email':'ignored@example.org'})
        order = self.service.order(ref)
        self.assertEqual(order['payer_name'], 'Different Payer')
        self.assertEqual(order['payer_phone'], '4799999999')
        with closing(module.get_db()) as db:
            member = db.execute('SELECT full_name FROM members').fetchone()
            self.assertEqual(member[0], 'Test Medlem')
            from personvern import erase_member
            self.assertEqual(erase_member(db, order['member_id'])[1], 200)
            db.commit()
        order = self.service.order(ref)
        self.assertEqual(order['payer_name'], '')
        self.assertEqual(order['payer_phone'], '')
        self.assertEqual(order['confirmation_status'], 'skipped')


class ReceiptTransportTests(unittest.TestCase):
    def test_content_amount_reference_reply_to_and_no_newsletter_dependency(self):
        with patch('innmelding_epost.mail_ready', return_value=True), patch.dict('os.environ', {'STYRE_EPOST_FRA':'noreply@example.org'}), patch('innmelding_epost.send_message') as send:
            self.assertTrue(send_confirmation({'email':'member@example.org','amount_ore':678,'for_year':2026,'reference':'ny-example123'}))
        msg = send.call_args.args[0]
        self.assertEqual(msg['To'], 'member@example.org')
        self.assertEqual(msg['Reply-To'], 'folk@oslobygda.no')
        self.assertIn('6,78 kr', msg.get_content())
        self.assertIn('ny-example123', msg.get_content())
        self.assertIn('2026', msg.get_content())
        self.assertNotIn('nyhendebrev', msg.get_content())

    def test_smtp_known_rejection_and_unknown_outcome(self):
        msg = EmailMessage(); msg.set_content('test')
        with patch.dict('os.environ', {'SMTP_HOST':'example.org','SMTP_USER':'test','SMTP_PASSWORD':'test','SMTP_PORT':'587'}), patch('epost.smtplib.SMTP') as smtp:
            smtp.return_value.send_message.side_effect = smtplib.SMTPDataError(450,b'rejected')
            with self.assertRaises(smtplib.SMTPDataError): send_message(msg)
            smtp.return_value.send_message.side_effect = smtplib.SMTPServerDisconnected('unknown')
            with self.assertRaises(DeliveryUncertain): send_message(msg)
            smtp.return_value.send_message.side_effect = None
            smtp.return_value.quit.side_effect = smtplib.SMTPServerDisconnected('after accepted')
            send_message(msg)  # QUIT-feil skal ikkje føre til ny utsending.
