"""Kontroller delte ressursar og plassering utan produksjonsdatabase."""
import unittest
import test_styre_auth as fixtures


class DesignSystemTests(unittest.TestCase):
    setUp = fixtures.BoardAuthTests.setUp
    tearDown = fixtures.BoardAuthTests.tearDown
    token = fixtures.BoardAuthTests.token

    def test_settings_belong_to_economy_and_members_are_readable(self):
        fixtures.BoardAuthTests.login(self)
        members = self.client.get('/').get_data(as_text=True)
        fees = self.client.get('/kontingent').get_data(as_text=True)
        self.assertNotIn('id="kontingent-innstillingar"', members)
        self.assertIn('id="kontingent-innstillingar"', fees)
        self.assertIn('href="/okonomi" aria-current="page"', fees)
        for name in ('medlem-sok', 'medlem-status', 'medlem-type', 'medlem-sortering', 'medlem-detalj'):
            self.assertIn('id="'+name+'"', members)
        self.assertNotIn('data-col="fødselsdato" checked', members)
        self.assertIn('scope="col"', members)

    def test_shared_tokens_and_step_styles_are_css(self):
        for url in ('/felles/designsystem.css','/fast/skjemasteg.css'):
            with self.client.get(url) as response:
                self.assertEqual(response.status_code, 200)
                self.assertIn('text/css', response.content_type)
                self.assertNotIn('<html',response.get_data(as_text=True).lower())
        fixtures.BoardAuthTests.login(self)
        self.assertIn('/felles/fonts/fraunces.css',self.client.get('/okonomi').get_data(as_text=True))
