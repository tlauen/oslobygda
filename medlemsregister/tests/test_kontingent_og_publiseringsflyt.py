"""Samla satsar og presis publiseringsstatus utan eksterne sendingar."""
import unittest
from unittest.mock import patch

import app as module
from database import managed_db
import test_styre_auth as fixtures


class SettingsAndPublicationTests(unittest.TestCase):
    setUp = fixtures.BoardAuthTests.setUp
    tearDown = fixtures.BoardAuthTests.tearDown
    token = fixtures.BoardAuthTests.token

    def login(self):
        fixtures.BoardAuthTests.login(self)

    def create_report(self):
        service = module.app.extensions['annual_documents']
        doc = service.create('arsmelding', 2026, 2027, 'styret')
        service.save(doc, 1, 'Årsmelding 2026', 'Året vårt', 2027, 'styret')
        return service, doc

    def test_one_prefilled_form_and_validation_preserves_values(self):
        self.login()
        html = self.client.get('/kontingent?year=2026').get_data(as_text=True)
        self.assertEqual(html.count('name="threshold"'), 1)
        self.assertEqual(html.count('name="minimum"'), 1)
        self.assertIn('value="5.00"', html)
        self.assertNotIn('Lagre grense', html)
        response = self.client.post('/kontingent?year=2027', data={
            'csrf_token': self.token(), 'action': 'save', 'year': '2027',
            'minimum': '100', 'threshold': '50', 'opens_on': '2027-03-01',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('value="100"', response.get_data(as_text=True))
        self.assertIn('value="50"', response.get_data(as_text=True))
        with managed_db(module.get_db) as db:
            self.assertIsNone(db.execute('SELECT minimum_ore FROM membership_periods WHERE year=2027').fetchone()[0])

    def test_current_year_save_refreshes_existing_payments(self):
        self.login()
        with managed_db(module.get_db) as db:
            mid = db.execute("""INSERT INTO members(full_name,fornamn,etternamn,email,membership_type,payment_status,consent_at,created_at,updated_at)
                VALUES ('Fiktiv Medlem','Fiktiv','Medlem','fiktiv@example.org','vanleg','ikkje betalt','now','now','now')""").lastrowid
        response = self.client.post(f'/api/members/{mid}/payments', json={'amount_nok': '7'}, headers={'X-CSRF-Token': self.token()})
        self.assertEqual(response.status_code, 201)
        response = self.client.post('/kontingent', data={
            'csrf_token': self.token(), 'action': 'save', 'year': '2026',
            'minimum': '5', 'threshold': '10', 'opens_on': '2026-01-01',
            'approved': '1', 'approved_on': '2026-01-01',
        })
        self.assertEqual(response.status_code, 200)
        with managed_db(module.get_db) as db:
            self.assertEqual(db.execute('SELECT membership_type FROM members WHERE id=?', (mid,)).fetchone()[0], 'vanleg')
            self.assertEqual(db.execute('SELECT superkul_ore FROM membership_periods WHERE year=2026').fetchone()[0], 1000)

    def test_reads_do_not_publish_and_copy_is_not_confused_with_publication(self):
        self.login()
        service, doc = self.create_report()
        with patch.object(module.app.extensions['document_publisher'], 'run') as run:
            html = self.client.get(f'/arsmote/{doc}').get_data(as_text=True)
            self.assertIn('Ingen fast kopi er laga eller send', html)
            vid = service.freeze(doc, 2, 'meeting', '', 'styret')
            self.assertIn('Ikkje sendt til nettsida', self.client.get(f'/arsmote/{doc}').get_data(as_text=True))
            service.enqueue(vid, 'styret')
            self.assertIn('Ventar på sending', self.client.get(f'/arsmote/{doc}').get_data(as_text=True))
            run.assert_not_called()

    def test_stored_visible_and_changed_draft_are_distinct(self):
        self.login()
        service, doc = self.create_report()
        vid = service.freeze(doc, 2, 'meeting', '', 'styret')
        service.enqueue(vid, 'styret')
        with managed_db(module.get_db) as db:
            db.execute("UPDATE annual_publication_queue SET status='stored' WHERE version_id=?", (vid,))
        html = self.client.get(f'/arsmote/{doc}').get_data(as_text=True)
        self.assertIn('Sendt – ventar på nettsidebygg', html)
        self.assertNotIn('Sist stadfesta levert', html)
        with managed_db(module.get_db) as db:
            db.execute("UPDATE annual_publication_queue SET status='visible' WHERE version_id=?", (vid,))
        service.save(doc, 2, 'Årsmelding 2026', 'Ny tekst', 2027, 'styret')
        html = self.client.get(f'/arsmote/{doc}').get_data(as_text=True)
        self.assertIn('Sist stadfesta levert til nettsida', html)
        self.assertIn('Arbeidsutkastet har endringar', html)
        with managed_db(module.get_db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM annual_versions').fetchone()[0], 1)

    def test_publish_returns_exact_copy_and_displays_result(self):
        self.login()
        service, doc = self.create_report()
        with patch.object(module.app.extensions['document_publisher'], 'run', return_value=dict(busy=False, failed=0, stored=1, visible=0)) as run:
            response = self.client.post(f'/arsmote/{doc}', data={
                'csrf_token': self.token(), 'action': 'publish_text', 'revision': 2,
                'title': 'Årsmelding 2026', 'body': 'Året vårt', 'meeting_year': 2027,
            })
        self.assertEqual(response.status_code, 302)
        self.assertRegex(response.location, r'/arsmote/versjon/\d+$')
        self.assertIn('Dokumentet er sendt til GitHub', self.client.get(response.location).get_data(as_text=True))
        run.assert_called_once()
