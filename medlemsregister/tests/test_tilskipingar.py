import base64
import unittest
from unittest.mock import patch
import yaml
import app as module
import test_styre_auth as fixtures
from tilskipingar import GithubCalendar, CalendarError, Conflict, validate_event, fingerprint, editable


class CalendarTests(unittest.TestCase):
    def event(self, **overrides):
        fields={'kind':'pobb','dato':'2026-11-18','start':'21:00','slutt':'23:45','tittel':'Jam, song & dans','stad':'Kaffistova, kjellaren'}
        fields.update(overrides)
        return validate_event(fields,'a'*32)

    def test_validation_and_midnight(self):
        self.assertEqual(self.event(slutt='01:00')['sluttdato'],'2026-11-19')
        for change in ({'kind':'styret'},{'dato':'2026-02-30'},{'tittel':''},{'lenkje':'javascript:alert(1)'},{'lenkje':'//bad.example'},{'bilete':'https://bad.example/x.png'},{'sluttdato':'2026-11-17'}):
            with self.assertRaises(ValueError): self.event(**change)

    def test_append_preserves_source_and_retries_concurrent_update(self):
        client=GithubCalendar('test-token')
        original='# original comment\n- uid: old\n  dato: "2026-01-01"\n'
        event=self.event()
        payload={'content':base64.b64encode(original.encode()).decode(),'sha':'old-sha'}
        updated=original+'\n# another comment\n- uid: concurrent\n  dato: "2026-02-01"\n'
        second={'content':base64.b64encode(updated.encode()).decode(),'sha':'new-sha'}
        with patch.object(client,'api',side_effect=[payload,Conflict('test'),second,{}]) as api:
            self.assertTrue(client.create(event))
            write=api.call_args.args[1]
            raw=base64.b64decode(write['content']).decode()
            self.assertTrue(raw.startswith(updated.rstrip()))
            self.assertEqual(write['sha'],'new-sha')
            self.assertEqual(len(yaml.safe_load(raw)),3)

    def test_retry_after_lost_response_does_not_duplicate(self):
        client=GithubCalendar('test-token')
        event=self.event()
        with patch.object(client,'read',return_value=('','sha',[event])), patch.object(client,'api') as api:
            self.assertFalse(client.create(event))
            api.assert_not_called()
        changed={**event,'tittel':'Changed'}
        with patch.object(client,'read',return_value=('','sha',[changed])):
            with self.assertRaises(Conflict): client.create(event)


    def test_update_preserves_identity_and_rejects_conflicts(self):
        client=GithubCalendar('test-token')
        old=self.event(dato='2099-11-18')
        old.update(uid='pobb-2099-09',avlyst=False)
        other={'uid':'other','dato':'2099-12-01'}
        raw='# heading\n'+yaml.safe_dump([old,other],allow_unicode=True,sort_keys=False)
        changed=self.event(dato='2099-11-19',tittel='Ny tittel')
        with patch.object(client,'read',return_value=(raw,'sha',[old,other])), patch.object(client,'api') as api:
            self.assertTrue(client.update(old['uid'],changed,fingerprint(old)))
            written=yaml.safe_load(base64.b64decode(api.call_args.args[1]['content']))
            self.assertEqual(written[0]['uid'],'pobb-2099-09')
            self.assertEqual(written[0]['registrering_id'],old['registrering_id'])
            self.assertFalse(written[0]['avlyst'])
            self.assertEqual(written[0]['tittel'],'Ny tittel')
            self.assertEqual(written[1],other)
            with self.assertRaises(Conflict): client.update(old['uid'],changed,'outdated')
        past=self.event(dato='2000-01-01')
        self.assertFalse(editable(past))
        with patch.object(client,'read',return_value=('', 'sha', [past])), patch.object(client,'api') as api:
            with self.assertRaises(Conflict): client.update(past['uid'],changed,fingerprint(past))
            api.assert_not_called()

    def test_edit_retry_after_lost_response(self):
        client=GithubCalendar('test-token')
        event=self.event(dato='2099-01-01')
        with patch.object(client,'read',return_value=('', 'sha', [event])), patch.object(client,'api') as api:
            self.assertFalse(client.update(event['uid'],event,'old-revision'))
            api.assert_not_called()


class CalendarRouteTests(unittest.TestCase):
    token=fixtures.BoardAuthTests.token
    setUp=fixtures.BoardAuthTests.setUp
    tearDown=fixtures.BoardAuthTests.tearDown

    def test_requires_login_and_csrf_and_can_publish(self):
        self.assertEqual(self.client.get('/tilskipingar').status_code,302)
        fixtures.BoardAuthTests.login(self)
        self.assertEqual(self.client.post('/tilskipingar',data={}).status_code,400)
        with patch.dict('os.environ',{'GITHUB_EVENTS_TOKEN':'test-token'}), patch.object(GithubCalendar,'read',return_value=('', 'sha', [])):
            page=self.client.get('/tilskipingar')
            self.assertEqual(page.status_code,200)
            with self.client.session_transaction() as session:
                key=session['calendar_submission']
            fields={'submission':key,'csrf_token':self.token(),'kind':'pobb','dato':'2026-11-18','start':'21:00','slutt':'23:45','tittel':'Test','stad':'Test'}
            with patch.object(GithubCalendar,'create',return_value=True) as create:
                response=self.client.post('/tilskipingar',data=fields)
                self.assertEqual(response.status_code,200)
                self.assertEqual(create.call_args.args[0]['registrering_id'],key)
            with patch.object(GithubCalendar,'create',side_effect=CalendarError('Could not save')):
                response=self.client.post('/tilskipingar',data=fields)
                self.assertEqual(response.status_code,503)
                self.assertIn(b'Could not save',response.data)
                self.assertIn(b'value="Test"',response.data)


    def test_open_and_save_existing_event(self):
        fixtures.BoardAuthTests.login(self)
        old=validate_event({'kind':'pobb','dato':'2099-11-18','start':'21:00','slutt':'23:45','tittel':'Original','stad':'Kaffistova'},'b'*32)
        old['uid']='pobb-2099-09'
        with patch.dict('os.environ',{'GITHUB_EVENTS_TOKEN':'test-token'}), patch.object(GithubCalendar,'read',return_value=('', 'sha', [old])):
            page=self.client.get('/tilskipingar?uid=pobb-2099-09')
            self.assertEqual(page.status_code,200)
            self.assertIn(b'value="Original"',page.data)
            with self.client.session_transaction() as session:
                key=session['calendar_submission']
            fields={**old,'kind':'pobb','submission':key,'csrf_token':self.token(),'revision':fingerprint(old),'tittel':'Endra'}
            with patch.object(GithubCalendar,'update',return_value=True) as update:
                response=self.client.post('/tilskipingar',data=fields)
                self.assertEqual(response.status_code,200)
                self.assertEqual(update.call_args.args[0],old['uid'])
                self.assertEqual(update.call_args.args[1]['tittel'],'Endra')
                self.assertEqual(update.call_args.args[2],fingerprint(old))
