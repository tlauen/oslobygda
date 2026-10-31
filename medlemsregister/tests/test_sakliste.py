import json
import sqlite3
import unittest
from unittest.mock import patch
import app as module
import test_styre_auth as fixtures
from arsdokument import DocumentConflict
from sakliste import validate_meeting, init_agendas, rule_blocks, default_agenda, validate_content
from publisering import validate_document, GithubDocuments, validate_envelope


class MeetingTests(unittest.TestCase):
    setUp=fixtures.BoardAuthTests.setUp
    tearDown=fixtures.BoardAuthTests.tearDown
    token=fixtures.BoardAuthTests.token

    @property
    def service(self): return module.app.extensions['meetings']

    def agenda(self):
        return dict(title='Årsmøte 2027',details='Kaffistova',items=[dict(title='Årsmelding',body='Til godkjenning',document='arsmelding:2026'),dict(title='Budsjett',body='',document='budsjett:2027')])

    def test_standard_agenda_years_subitems_and_links(self):
        agenda=default_agenda(2027)
        items=agenda['items']
        self.assertEqual(len(items),8)
        self.assertEqual(items[1]['title'],'Årsmelding for 2026')
        self.assertEqual(items[1]['document'],'arsmelding:2026')
        self.assertEqual(items[2]['document'],'rekneskap:2026')
        self.assertEqual(items[3]['title'],'Medlemspengar for 2028')
        self.assertEqual(items[4]['title'],'Planar for 2027')
        self.assertEqual(items[5]['document'],'budsjett:2027')
        self.assertEqual(len(items[0]['subitems']),6)
        self.assertEqual(items[-1]['subitems'],['Val av leiar','Val av styremedlemmar'])
        self.assertNotIn('Lovendringar',[item['title'] for item in items])
        validate_content('sakliste',agenda)
        self.assertEqual(default_agenda(2029)['items'][1]['title'],'Årsmelding for 2028')
        self.assertEqual(default_agenda(2029)['items'][1]['document'],'')
        self.service.save('sakliste',2027,0,agenda)
        fixtures.BoardAuthTests.login(self)
        page=self.client.get('/sakliste/2027')
        self.assertIn('1.6 Val av protokollunderskrivarar'.encode(),page.data)
        self.assertIn('8.2 Val av styremedlemmar'.encode(),page.data)
        self.assertIn('Sak 7: Ymse'.encode(),page.data)
        self.assertEqual(self.service.enqueue('sakliste',2027,1)['content'],agenda)

    def test_revisions_publication_and_validation(self):
        self.service.save('sakliste',2027,0,self.agenda())
        with self.assertRaises(DocumentConflict): self.service.save('sakliste',2027,0,self.agenda())
        p=self.service.enqueue('sakliste',2027,1)
        self.assertEqual(p,self.service.enqueue('sakliste',2027,1))
        validate_document(p)
        self.service.save('sakliste',2027,1,dict(self.agenda(),title='Endra'))
        self.assertEqual(p['content']['title'],'Årsmøte 2027')
        with self.assertRaises(DocumentConflict): self.service.enqueue('sakliste',2027,1)
        with self.assertRaises(ValueError): self.service.save('sakliste',2027,2,dict(self.agenda(),items=[]))
        bad=self.agenda();bad['items'][0]['document']='javascript:alert(1)'
        with self.assertRaises(ValueError): self.service.save('sakliste',2027,2,bad)
        with module.get_db() as db:
            with self.assertRaises(sqlite3.IntegrityError): db.execute("UPDATE meeting_publication_queue SET payload='{}'")
        init_agendas(module.get_db)

    def test_auth_csrf_saved_preview_and_conflict(self):
        self.assertEqual(self.client.get('/sakliste').status_code,302)
        fixtures.BoardAuthTests.login(self)
        self.assertEqual(self.client.post('/sakliste',data={}).status_code,400)
        response=self.client.get('/sakliste');self.assertIn('Til saksfyrehavingi'.encode(),response.data)
        self.assertIn('teljekorps'.encode(),response.data)
        self.assertEqual(self.client.get('/sakliste/2027').status_code,200)
        data=dict(csrf_token=self.token(),action='save',revision=0,title='<script>Test</script>',details='Stad',item_title=['Årsmelding'],item_body=['Omtale'],item_document=['arsmelding:2026'])
        self.assertEqual(self.client.post('/sakliste/2027',data=data).status_code,302)
        page=self.client.get('/sakliste/2027')
        self.assertIn(b'&lt;script&gt;Test&lt;/script&gt;',page.data)
        self.assertNotIn(b'<script>Test</script>',page.data)
        data['title']='Bevar denne teksten'
        response=self.client.post('/sakliste/2027',data=data)
        self.assertEqual(response.status_code,409);self.assertIn(b'Bevar denne teksten',response.data)
        data=dict(csrf_token=self.token(),action='publish',revision=1)
        self.assertEqual(self.client.post('/sakliste/2027',data=data).status_code,400)
        data['confirmed']='yes'
        with patch('publisering.publish_from_button') as publish:
            self.assertEqual(self.client.post('/sakliste/2027',data=data).status_code,302)
            self.assertEqual(publish.call_args.args[1][0],'meeting')

    def test_rules_seed_survives_restart_and_heading_preview(self):
        self.service.save('motereglar',0,1,dict(body='## Nye reglar\nBevar denne teksten.'))
        init_agendas(module.get_db)
        with module.get_db() as db:
            row=db.execute("SELECT * FROM meeting_drafts WHERE kind='motereglar'").fetchone()
            self.assertEqual(row['revision'],2)
            self.assertEqual(json.loads(row['content'])['body'],'## Nye reglar\nBevar denne teksten.')
        self.assertEqual(rule_blocks('## Nye reglar\nBevar denne teksten.'),[('heading','Nye reglar'),('text','Bevar denne teksten.')])

    def test_rules_and_publisher_worker(self):
        self.service.save('motereglar',0,1,dict(body='## Reglar\nTekst'))
        payload=self.service.enqueue('motereglar',0,2)
        self.assertEqual(payload,self.service.enqueue('motereglar',0,2))
        class Client:
            def store(self,payload,guard): guard();validate_meeting(payload);return 'sha'
            def visible(self,payload): return True
        result=module.app.extensions['document_publisher'].run(client=Client(),target=('meeting',payload['version_id']))
        self.assertEqual(result['visible'],1)
        with module.get_db() as db:
            self.assertEqual(db.execute('SELECT status FROM meeting_publication_queue').fetchone()[0],'visible')
        envelope=dict(schema_version=1,year=payload['report_year'],versions=[payload],ledger_latest=None)
        validate_envelope(envelope,payload['report_year'])
        self.assertTrue(GithubDocuments.contains(envelope,payload))
