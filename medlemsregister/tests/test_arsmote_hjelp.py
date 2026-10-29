import unittest
import test_styre_auth as fixtures

class HelpTests(unittest.TestCase):
    setUp=fixtures.BoardAuthTests.setUp
    tearDown=fixtures.BoardAuthTests.tearDown
    token=fixtures.BoardAuthTests.token

    def test_help_requires_login_is_read_only_and_contains_workflows(self):
        self.assertEqual(self.client.get('/arsmote/hjelp').status_code,302)
        fixtures.BoardAuthTests.login(self)
        response=self.client.get('/arsmote/hjelp')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        raw=response.data.decode()
        for section in ('forste-gong','vanleg-foring','medlemspengar','kontroll','budsjett','arsmelding','publisering','arsmote','retting','backup'):
            self.assertIn(f'id="{section}"',raw)
        self.assertIn('aria-current="page">Hjelp',raw)
        self.assertEqual(raw.count('<form'),1)
        self.assertIn('action="/logout"',raw)
        self.assertEqual(self.client.post('/arsmote/hjelp',data={'csrf_token':self.token()}).status_code,405)
