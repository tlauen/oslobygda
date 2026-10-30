import json
import unittest
from unittest.mock import patch
from database import managed_db
import app as module
import test_styre_auth as fixtures
from arsdokument import DocumentConflict, init_documents
from arsmelding import merge_calendar

class ReportTests(unittest.TestCase):
    setUp = fixtures.BoardAuthTests.setUp
    tearDown = fixtures.BoardAuthTests.tearDown
    token = fixtures.BoardAuthTests.token

    @property
    def service(self): return module.app.extensions['annual_documents']

    def doc(self):
        with managed_db(module.get_db) as db:
            return dict(db.execute('SELECT * FROM annual_documents WHERE id=?',(self.doc_id,)).fetchone())

    def create(self):
        self.doc_id=self.service.create('arsmelding',2026,2027,'styret')

    def update(self, action, form=None, calendar=None):
        self.service.update_report(self.doc_id,self.doc()['revision'],'styret',action,form,calendar)

    def event(self, **changes):
        return dict(uid='event-a',dato='2026-06-01',tittel='Pøbb',stad='Kaffistova',merknad='Omtale',**changes)

    def import_events(self, events=None, revision='calendar-sha'):
        self.update('import_calendar', calendar=(revision,events if events is not None else [self.event()]))

    def report(self): return json.loads(self.doc()['report_json'])

    def form(self, **changes):
        report=self.report()
        values=dict(title='Årsmelding',meeting_year=2027,intro='Innleiing',organization='Styret arbeidde',conclusion='Takk')
        for item in report['activities']:
            prefix='activity_'+item['key']+'_'
            values.update({prefix+'included':'yes',prefix+'status':'completed',prefix+'comment':'Vår kommentar',prefix+'participants':'40'})
            if item['origin']=='manual':
                values.update({prefix+k:v for k,v in item['source'].items()})
        values.update(changes)
        return values

    def test_import_year_selection_dedup_comments_and_freeze(self):
        self.create()
        self.import_events([self.event(),dict(uid='old',dato='2025-12-31',tittel='Førre år')])
        self.assertEqual(len(self.report()['activities']),1)
        self.assertTrue(self.report()['activities'][0]['included'])
        self.update('save_report',self.form())
        version=self.service.freeze(self.doc_id,self.doc()['revision'],'meeting','','styret')
        self.import_events([dict(uid='event-a',dato='2026-06-02',tittel='Ny tittel',stad='Ny stad',merknad='Ny omtale')])
        self.import_events([dict(uid='event-a',dato='2026-06-02',tittel='Ny tittel',stad='Ny stad',merknad='Ny omtale')])
        item=self.report()['activities'][0]
        self.assertEqual(item['comment'],'Vår kommentar')
        self.assertEqual(item['participants'],40)
        self.assertTrue(item['included']); self.assertTrue(item['source_changed'])
        with self.assertRaises(ValueError): self.service.freeze(self.doc_id,self.doc()['revision'],'meeting','','styret')
        self.update('save_report',self.form(**{'activity_'+item['key']+'_acknowledge':'yes'}))
        self.service.freeze(self.doc_id,self.doc()['revision'],'meeting','','styret')
        self.service.enqueue(version,'styret')
        with managed_db(module.get_db) as db:
            payload=json.loads(db.execute('SELECT payload FROM annual_publication_queue').fetchone()[0])
            self.assertIn('Pøbb',payload['body']); self.assertNotIn('Ny tittel',payload['body'])
            self.assertNotIn('report_json',payload)
            history=json.loads(db.execute('SELECT report_json FROM annual_document_edits ORDER BY revision DESC LIMIT 1').fetchone()[0])
            self.assertEqual(history['activities'][0]['comment'],'Vår kommentar')

    def test_cancelled_unconfirmed_missing_and_stale_import(self):
        self.create()
        self.import_events([dict(uid='cancelled',dato='2026-01-01',tittel='Pøbb AVLYST'),self.event()])
        self.assertEqual(self.report()['activities'][0]['status'],'cancelled')
        form=self.form()
        key=self.report()['activities'][1]['key']
        form['activity_'+key+'_status']='unconfirmed'
        self.update('save_report',form)
        self.service.freeze(self.doc_id,self.doc()['revision'],'meeting','','styret')
        with self.assertRaises(ValueError): self.service.freeze(self.doc_id,self.doc()['revision'],'approved','2026-01-01','styret')
        self.import_events([])
        self.assertTrue(self.report()['activities'][0]['source_missing'])
        with self.assertRaises(DocumentConflict):
            self.service.update_report(self.doc_id,1,'styret','import_calendar',calendar=('x',[]))

    def test_manual_activity_and_validation_rollback(self):
        self.create()
        self.update('add_manual',dict(manual_dato='2026-04-01',manual_tittel='Dugnad',manual_stad='Oslo',manual_merknad='Arbeid'))
        self.import_events([])
        self.assertEqual(self.report()['activities'][0]['origin'],'manual')
        self.update('save_report',self.form())
        self.assertIn('Dugnad',self.doc()['body'])
        before=self.doc()['revision']
        item=self.report()['activities'][0]
        for changes in ({'activity_'+item['key']+'_participants':'-1'}, {'activity_'+item['key']+'_dato':'2025-01-01'}):
            with self.assertRaises(ValueError): self.update('save_report',self.form(**changes))
        with self.assertRaises(ValueError): self.import_events([self.event(),self.event()])
        with self.assertRaises(ValueError): self.update('add_manual',dict(manual_dato='2027-01-01',manual_tittel='Feil år'))
        self.assertEqual(self.doc()['revision'],before)

    def test_legacy_body_migration_and_statistics(self):
        self.create()
        self.service.save(self.doc_id,1,'Gamalt','Gamal tekst',2027,'styret')
        init_documents(module.get_db)
        self.import_events([])
        self.assertEqual(self.report()['intro'],'Gamal tekst')
        self.update('refresh_membership')
        self.assertEqual(self.report()['membership']['count'],0)
        self.assertEqual(self.report()['membership']['ages']['as_of'], '2026-12-31')
        self.assertEqual(self.report()['membership']['ages']['age_0_14'], 0)
        self.assertIn('ikkje medlemstal ved årsskiftet',self.doc()['body'])
        with managed_db(module.get_db) as db:
            db.execute('INSERT INTO medlemsar_arkiv(ar,totalt_ore,antall_medlemer_med_betaling,oppretta) VALUES (2026,10000,7,?)',('2026-01-01',))
        self.update('refresh_membership')
        self.assertEqual(self.report()['membership']['source'],'archive')
        self.assertEqual(self.report()['membership']['count'],7)
        self.update('remove_membership')
        self.assertIsNone(self.report()['membership'])
        with self.assertRaises(ValueError): self.service.save(self.doc_id,self.doc()['revision'],'T','Overskriv',2027,'styret')

    def test_routes_and_failed_calendar_leaves_draft_unchanged(self):
        self.create()
        fixtures.BoardAuthTests.login(self)
        csrf=self.token()
        with patch('arsdokument.GithubCalendar') as client:
            client.return_value.read.return_value=('', 'test-sha',[self.event()])
            response=self.client.post(f'/arsmote/{self.doc_id}',data=dict(action='import_calendar',revision=1,csrf_token=csrf))
        self.assertEqual(response.status_code,302)
        page=self.client.get(f'/arsmote/{self.doc_id}')
        self.assertEqual(page.status_code,200)
        self.assertIn('Kaffistova'.encode(),page.data)
        form=self.form();form.update(action='save_report',revision=self.doc()['revision'],csrf_token=csrf)
        self.assertEqual(self.client.post(f'/arsmote/{self.doc_id}',data=form).status_code,302)
        from tilskipingar import CalendarError
        before=self.doc()['revision']
        with patch('arsdokument.GithubCalendar',side_effect=CalendarError('Mellombels utilgjengeleg')):
            response=self.client.post(f'/arsmote/{self.doc_id}',data=dict(action='import_calendar',revision=before,csrf_token=csrf))
        self.assertEqual(response.status_code,503)
        self.assertEqual(self.doc()['revision'],before)

    def test_validation_error_keeps_editor_save_enabled(self):
        import re
        self.create();self.import_events([self.event()])
        fixtures.BoardAuthTests.login(self)
        response=self.client.post(f'/arsmote/{self.doc_id}',data=dict(csrf_token=self.token(),action='freeze',revision=self.doc()['revision'],status='approved',decision_date='2026-01-01'))
        self.assertEqual(response.status_code,400)
        self.assertIn('Lagre årsmeldinga',response.get_data(as_text=True))
        self.assertFalse(re.search(r'<button[^>]*\bdisabled',response.get_data(as_text=True)))
        form=self.form();form.update(csrf_token=self.token(),action='save_report',revision=self.doc()['revision'])
        self.assertEqual(self.client.post(f'/arsmote/{self.doc_id}',data=form).status_code,302)
