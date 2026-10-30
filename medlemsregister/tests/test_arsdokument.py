import json
import sqlite3
import unittest
import app as module
import test_styre_auth as fixtures
from arsdokument import DocumentConflict, init_documents, validate_public

class DocumentTests(unittest.TestCase):
    setUp = fixtures.BoardAuthTests.setUp
    tearDown = fixtures.BoardAuthTests.tearDown
    token = fixtures.BoardAuthTests.token

    @property
    def service(self): return module.app.extensions['annual_documents']

    def draft(self):
        doc = self.service.create('arsmelding',2026,2027,'styret')
        self.service.save(doc,1,'Året','Offentleg tekst',2027,'intern-brukar')
        return doc

    def test_snapshot_and_queue_immutable_idempotent(self):
        doc=self.draft()
        init_documents(module.get_db)
        vid=self.service.freeze(doc,2,'meeting','','styret')
        self.assertEqual(self.service.freeze(doc,2,'meeting','','styret'),vid)
        self.service.save(doc,2,'Endra','Ny tekst',2027,'styret')
        self.service.enqueue(vid,'styret'); self.service.enqueue(vid,'styret')
        with module.get_db() as db:
            row=db.execute('SELECT * FROM annual_publication_queue').fetchone()
            payload=json.loads(row['payload'])
            self.assertEqual(payload['body'],'Offentleg tekst')
            self.assertNotIn('intern-brukar',row['payload'])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM annual_publication_queue').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM board_users').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM annual_document_edits').fetchone()[0],3)
            for sql in ("UPDATE annual_versions SET snapshot='{}'",'DELETE FROM annual_versions',"UPDATE annual_publication_queue SET payload='{}'"):
                with self.assertRaises(sqlite3.IntegrityError): db.execute(sql)
        payload['email']='private@example.test'
        with self.assertRaises(ValueError): validate_public(payload)

    def test_conflicts_and_approval(self):
        doc=self.draft()
        with self.assertRaises(DocumentConflict): self.service.save(doc,1,'Tittel','Tapt',2027,'styret')
        with self.assertRaises(DocumentConflict): self.service.freeze(doc,1,'meeting','','styret')
        proposal=self.service.freeze(doc,2,'meeting','','styret')
        for value in ('','2026-02-30','2199-01-01'):
            with self.assertRaises(ValueError): self.service.freeze(doc,2,'approved',value,'styret')
        approved=self.service.freeze(doc,2,'approved','2026-01-01','styret')
        self.assertNotEqual(proposal,approved)
        with self.assertRaises(DocumentConflict): self.service.freeze(doc,2,'approved','2026-01-02','styret')
        with self.assertRaises(DocumentConflict): self.service.create('arsmelding',2026,2027,'styret')
        with self.assertRaises(ValueError): self.service.create('rekneskap',2026,2027,'styret')
        with self.assertRaises(ValueError): self.service.create('arsmelding',9999,2027,'styret')

    def test_routes_auth_csrf_conflict_preview_and_queue(self):
        for path in ('/arsmote','/arsmote/1','/arsmote/versjon/1'):
            self.assertEqual(self.client.get(path).status_code,302)
        fixtures.BoardAuthTests.login(self)
        self.assertEqual(self.client.post('/arsmote',data={}).status_code,400)
        csrf=self.token()
        response=self.client.post('/arsmote',data=dict(csrf_token=csrf,kind='arsmelding',report_year=2026,meeting_year=2027))
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.get(response.location).status_code,200)
        data=dict(csrf_token=csrf,action='save',revision=1,title='Test',body='<script>alert(1)</script>',meeting_year=2027)
        self.assertEqual(self.client.post('/arsmote/1',data=data).status_code,302)
        data['body']='Bevar teksten'
        stale=self.client.post('/arsmote/1',data=data)
        self.assertEqual(stale.status_code,409); self.assertIn(b'Bevar teksten',stale.data)
        vid=self.service.freeze(1,2,'meeting','','styret')
        page=self.client.get(f'/arsmote/versjon/{vid}')
        self.assertEqual(page.status_code,200)
        self.assertNotIn(b'<script>alert(1)</script>',page.data)
        self.assertIn(b'&lt;script&gt;',page.data)
        self.assertEqual(self.client.post(f'/arsmote/versjon/{vid}',data={'csrf_token':csrf}).status_code,400)
        self.assertEqual(self.client.post(f'/arsmote/versjon/{vid}',data={'csrf_token':csrf,'confirmed':'yes'}).status_code,302)
        self.assertEqual(self.client.get('/arsmote/99999').status_code,404)
        self.assertEqual(self.client.get('/arsmote/versjon/99999').status_code,404)

    def test_long_norwegian_report_survives_form_encoding_and_keeps_request_cap(self):
        doc=self.draft();fixtures.BoardAuthTests.login(self)
        text='æøå '*7000
        response=self.client.post(f'/arsmote/{doc}',data=dict(csrf_token=self.token(),action='save',revision='2',title='Året',body=text,meeting_year='2027'))
        self.assertEqual(response.status_code,302)
        with module.get_db() as db:
            self.assertEqual(db.execute('SELECT body FROM annual_documents WHERE id=?',(doc,)).fetchone()[0],text.strip())
        response=self.client.post(f'/arsmote/{doc}',data=b'x'*(1024*1024+1),content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code,413)

    def test_publish_button_sends_only_selected_version(self):
        from unittest.mock import Mock
        from database import managed_db
        doc=self.draft();vid=self.service.freeze(doc,2,'meeting','','styret')
        self.service.save(doc,2,'Ny versjon','Ny offentleg tekst',2027,'styret')
        other=self.service.freeze(doc,3,'meeting','','styret');self.service.enqueue(other,'styret')
        fixtures.BoardAuthTests.login(self)
        publisher=module.app.extensions['document_publisher']
        client=Mock();client.store.return_value='commit';client.visible.return_value=False
        from unittest.mock import patch
        with patch('publisering.GithubDocuments',return_value=client):
            response=self.client.post(f'/arsmote/versjon/{vid}',data=dict(csrf_token=self.token(),confirmed='yes'))
        self.assertEqual(response.status_code,302)
        client.store.assert_called_once()
        self.assertEqual(client.store.call_args.args[0]['version_id'],vid)
        with managed_db(module.get_db) as db:
            self.assertEqual(db.execute('SELECT status FROM annual_publication_queue WHERE version_id=?',(vid,)).fetchone()[0],'stored')
            self.assertEqual(db.execute('SELECT status FROM annual_publication_queue WHERE version_id=?',(other,)).fetchone()[0],'pending')
