import unittest
import test_styre_auth as fixtures

class MemberHelpTests(unittest.TestCase):
    setUp=fixtures.BoardAuthTests.setUp
    tearDown=fixtures.BoardAuthTests.tearDown
    token=fixtures.BoardAuthTests.token
    def test_separate_private_help_and_correct_menu(self):
        self.assertEqual(self.client.get('/medlemsliste/hjelp').status_code,302)
        fixtures.BoardAuthTests.login(self)
        response=self.client.get('/medlemsliste/hjelp');self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        raw=response.data.decode()
        self.assertIn('aria-label="Medlemsadministrasjon"',raw)
        self.assertIn('href="/medlemsliste/hjelp" aria-current="page">Hjelp',raw)
        for section in ('medlem','betaling','innmelding','fornying','arsskifte','personvern','kalender'):
            self.assertIn('id="'+section+'"',raw)
        self.assertIn('href="/medlemsliste/hjelp"',self.client.get('/').data.decode())
        self.assertIn('href="/arsmote/hjelp" aria-current="page">Hjelp',self.client.get('/arsmote/hjelp').data.decode())
