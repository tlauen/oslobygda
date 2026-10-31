import json
import sqlite3
import os
import re
import time
import unittest
from unittest.mock import patch
import app as module
import test_styre_auth as fixtures
from arsdokument import DocumentConflict, digest
from protokoll import validate_minutes, init_minutes, LINK_DAYS
from publisering import validate_document, PublicationError
from werkzeug.datastructures import MultiDict
from sakliste import default_agenda
from epost import DeliveryUncertain

MAIL_ENV={'SMTP_HOST':'smtp.test','SMTP_USER':'user','SMTP_PASSWORD':'test','STYRE_EPOST_FRA':'styret@example.test','BYGDELISTA_PUBLIC_ORIGIN':'https://bygdelista.example.test'}

def mail_token(send):
    return re.search(r'#([A-Za-z0-9_-]{43})',send.call_args.args[0].get_content()).group(1)

class MinutesTests(unittest.TestCase):
    setUp=fixtures.BoardAuthTests.setUp
    tearDown=fixtures.BoardAuthTests.tearDown
    token=fixtures.BoardAuthTests.token
    @property
    def service(self): return module.app.extensions['minutes']

    def draft(self):
        module.app.extensions['meetings'].save('sakliste',2027,0,default_agenda(2027))
        rev,content=self.service.load(2027)
        content.update(meeting_date='2026-01-01',secretary='Protokollskrivar')
        for item in content['items']: item['decision']='Samrøystes vedteke.'
        self.service.save(2027,rev,content,'styret')
        return content

    def review(self):
        self.draft()
        rid=self.service.start_review(2027,1,[('Underskrivar Ein','ein@example.test'),('Underskrivar To','to@example.test')],'styret')
        tokens=[]
        with patch.dict(os.environ,MAIL_ENV),patch('protokoll.send_message') as send:
            for slot in (1,2):
                self.assertEqual(self.service.send_link(rid,slot),'sent')
                tokens.append(mail_token(send))
        return rid,tokens

    def test_both_must_approve_same_snapshot_and_publish_once(self):
        rid,tokens=self.review()
        self.assertIsNone(self.service.decide(digest(tokens[0]),'approve'))
        with module.get_db() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM meeting_publication_queue').fetchone()[0],0)
        payload=self.service.decide(digest(tokens[1]),'approve');validate_document(payload)
        self.assertEqual(len(payload['approved_by']),2)
        self.assertNotIn('example.test',json.dumps(payload))
        for token in tokens: self.assertNotIn(token,json.dumps(payload))
        self.assertIsNone(self.service.decide(digest(tokens[1]),'approve'))
        with module.get_db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM meeting_publication_queue').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT state FROM minutes_reviews WHERE id=?',(rid,)).fetchone()[0],'approved')
            for sql in ("UPDATE minutes_reviews SET snapshot='{}'","UPDATE minutes_signers SET approved_at='endra' WHERE approved_at IS NOT NULL",'DELETE FROM minutes_signers'):
                with self.assertRaises(sqlite3.IntegrityError): db.execute(sql)
        with self.assertRaises(ValueError): validate_minutes(dict(payload,approved_by=payload['approved_by'][:1]))

    def test_edit_cancels_review_and_rejection_blocks_publication(self):
        rid,tokens=self.review()
        self.service.decide(digest(tokens[0]),'approve')
        rev,content=self.service.load(2027);content['items'][0]['decision']='Retta vedtak'
        self.service.save(2027,rev,content,'styret')
        with self.assertRaises(ValueError): self.service.decide(digest(tokens[1]),'approve')
        with self.assertRaises(DocumentConflict): self.service.save(2027,rev,content,'styret')
        rid=self.service.start_review(2027,2,[('Ein','ein@example.test'),('To','to@example.test')],'styret')
        with patch.dict(os.environ,MAIL_ENV),patch('protokoll.send_message') as send:
            self.service.send_link(rid,1);token=mail_token(send)
        self.service.decide(digest(token),'reject','Røystetalet må rettast.')
        with self.assertRaises(ValueError): self.service.decide(digest(token),'approve')
        with module.get_db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM meeting_publication_queue').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT state FROM minutes_reviews WHERE id=?',(rid,)).fetchone()[0],'rejected')

    def test_expiry_rotation_mail_uncertainty_and_restart(self):
        rid,tokens=self.review()
        with patch('protokoll.time.time',return_value=time.time()+(LINK_DAYS+1)*86400):
            with self.assertRaises(ValueError): self.service.resolve(digest(tokens[0]))
        with patch.dict(os.environ,MAIL_ENV),patch('protokoll.send_message',side_effect=DeliveryUncertain('test')):
            self.assertEqual(self.service.send_link(rid,1),'uncertain')
        with self.assertRaises(ValueError): self.service.resolve(digest(tokens[0]))
        self.assertEqual(self.service.resolve(digest(tokens[1]))['slot'],2)
        init_minutes(module.get_db)
        with module.get_db() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM minutes_signers').fetchone()[0],2)

    def test_validation_private_editor_and_csrf(self):
        self.assertEqual(self.client.get('/sakliste/2027/protokoll').status_code,302)
        self.draft()
        with self.assertRaises(ValueError): self.service.start_review(2027,1,[('Ein','same@example.test'),('To','SAME@example.test')],'styret')
        rev,content=self.service.load(2027);content['items'][0]['decision']=''
        self.service.save(2027,rev,content,'styret')
        with self.assertRaises(ValueError): self.service.start_review(2027,2,[('Ein','ein@example.test'),('To','to@example.test')],'styret')
        fixtures.BoardAuthTests.login(self)
        self.assertEqual(self.client.get('/sakliste/2027/protokoll').status_code,200)
        self.assertEqual(self.client.post('/sakliste/2027/protokoll',data={}).status_code,400)

    def test_approval_routes_get_does_not_sign_and_second_approval_publishes(self):
        rid,tokens=self.review();clients=[module.app.test_client(),module.app.test_client()]
        for client,token in zip(clients,tokens):
            response=client.get('/protokoll/godkjenn')
            self.assertEqual(response.headers['Referrer-Policy'],'no-referrer')
            with client.session_transaction() as s: csrf=s['csrf_token']
            self.assertEqual(client.post('/protokoll/godkjenn',data=dict(token=token,action='open')).status_code,400)
            self.assertEqual(client.post('/protokoll/godkjenn',data=dict(token=token,action='open',csrf_token=csrf)).status_code,302)
            page=client.get('/protokoll/godkjenn')
            self.assertIn('Samrøystes vedteke.'.encode(),page.data);self.assertNotIn(token.encode(),page.data)
        with clients[0].session_transaction() as s: csrf=s['csrf_token']
        self.assertEqual(clients[0].post('/protokoll/godkjenn',data=dict(csrf_token=csrf,approval_context='feil æ',decision='approve',confirmed='yes')).status_code,400)
        with module.get_db() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM minutes_signers WHERE approved_at IS NOT NULL').fetchone()[0],0)
        with patch.object(self.service,'publish_pending') as publish:
            for index,client in enumerate(clients):
                with client.session_transaction() as s: csrf=s['csrf_token'];context=s['minutes_approval']
                response=client.post('/protokoll/godkjenn',data=dict(csrf_token=csrf,approval_context=context,decision='approve',confirmed='yes'))
                self.assertEqual(response.status_code,200);self.assertEqual(publish.call_count,index)

    def test_guest_writer_scope_rotation_and_no_admin_access(self):
        self.draft()
        with patch.dict(os.environ,MAIL_ENV),patch('protokoll.send_message') as send:
            self.assertEqual(self.service.send_writer(2027,'Skrivar','skrivar@example.test'),'sent');token=mail_token(send)
        client=module.app.test_client();client.get('/protokoll/skriv')
        with client.session_transaction() as s: csrf=s['csrf_token']
        self.assertEqual(client.post('/protokoll/skriv',data=dict(token=token,csrf_token=csrf)).status_code,302)
        self.assertEqual(client.get('/sakliste/2027/protokoll').status_code,200)
        self.assertEqual(client.get('/sakliste/2026/protokoll').status_code,403)
        self.assertEqual(client.get('/').status_code,302);self.assertEqual(client.get('/okonomi').status_code,302)
        revision,content=self.service.load(2027)
        data=MultiDict([('csrf_token',csrf),('action','save'),('revision',str(revision))]+[(key,content[key]) for key in ('title','secretary','meeting_date','details')])
        for item in content['items']:
            data.add('case_title',item['title']);data.add('case_subitems','\n'.join(item['subitems']))
            for key in ('proposals','speakers','votes','decision'): data.add(key,item[key])
        self.assertEqual(client.post('/sakliste/2027/protokoll',data=data).status_code,302)
        self.assertEqual(self.service.load(2027)[0],2)
        with patch.dict(os.environ,MAIL_ENV),patch('protokoll.send_message') as send:
            response=client.post('/sakliste/2027/protokoll',data=dict(csrf_token=csrf,action='review',revision=2,confirmed='yes',name_1='Ein',email_1='ein@example.test',name_2='To',email_2='to@example.test'))
            self.assertEqual(response.status_code,302);self.assertEqual(send.call_count,2)
        self.assertEqual(client.post('/sakliste/2027/protokoll',data=dict(action='invite_writer',csrf_token=csrf)).status_code,403)
        with patch.dict(os.environ,MAIL_ENV),patch('protokoll.send_message'): self.service.send_writer(2027,'Skrivar','skrivar@example.test')
        self.assertEqual(client.get('/sakliste/2027/protokoll').status_code,302)

    def test_automatic_retry_endpoint_requires_secret(self):
        rid,tokens=self.review()
        self.service.decide(digest(tokens[0]),'approve');self.service.decide(digest(tokens[1]),'approve')
        secret='test-secret-'*4
        with patch.dict(os.environ,{'BYGDELISTA_PUBLICATION_TOKEN':secret}):
            self.assertEqual(self.client.post('/api/protokoll/publiser').status_code,403)
            self.assertEqual(self.client.post('/api/protokoll/publiser',headers={'Authorization':'Bearer wrong'}).status_code,403)
            class Client:
                attempts=0
                def store(self,payload,guard):
                    guard();self.attempts+=1
                    if self.attempts==1: raise PublicationError('Mellombels feil')
                    validate_minutes(payload);return 'sha'
                def visible(self,payload): return True
            remote=Client()
            with patch('publisering.GithubDocuments',return_value=remote):
                response=self.client.post('/api/protokoll/publiser',headers={'Authorization':'Bearer '+secret})
                self.assertEqual(response.status_code,200);self.assertEqual(response.json['failed'],1)
                with module.get_db() as db: self.assertEqual(db.execute('SELECT status FROM meeting_publication_queue').fetchone()[0],'failed')
                response=self.client.post('/api/protokoll/publiser',headers={'Authorization':'Bearer '+secret})
                self.assertEqual(response.status_code,200);self.assertEqual(response.json['visible'],1)
                with module.get_db() as db: self.assertEqual(db.execute('SELECT status FROM meeting_publication_queue').fetchone()[0],'visible')
