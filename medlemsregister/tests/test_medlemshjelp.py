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
        for section in ('medlem','betaling','innmelding','arsskifte','personvern'):
            self.assertIn('id="'+section+'"',raw)
        self.assertIn('href="/medlemsliste/hjelp"',self.client.get('/').data.decode())
        self.assertIn('href="/arsmote/hjelp" aria-current="page">Hjelp',self.client.get('/arsmote/hjelp').data.decode())

    def test_modules_own_their_pages_and_help(self):
        from html.parser import HTMLParser
        class Navigation(HTMLParser):
            def __init__(self):
                super().__init__(); self.kind=None; self.links={}; self.current={}
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs)
                if tag=='nav':
                    self.kind=attrs.get('class'); self.links.setdefault(self.kind,[])
                if tag=='a' and self.kind:
                    self.links[self.kind].append(attrs.get('href'))
                    if attrs.get('aria-current')=='page':
                        self.current.setdefault(self.kind,[]).append(attrs.get('href'))
            def handle_endtag(self,tag):
                if tag=='nav': self.kind=None
        help_pages=[('/medlemsliste/hjelp','/'),('/okonomi/hjelp','/okonomi'),('/arsmote/hjelp','/arsmote'),('/nettsida/hjelp','/tilskipingar')]
        for path,_ in help_pages:
            self.assertEqual(self.client.get(path).status_code,302)
        fixtures.BoardAuthTests.login(self)
        for path,module_path in help_pages:
            with self.subTest(path=path):
                response=self.client.get(path)
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.headers['Cache-Control'],'no-store')
                nav=Navigation(); nav.feed(response.get_data(as_text=True))
                self.assertEqual(nav.current['bygdelista-delar'],[module_path])
                self.assertEqual(nav.current['bygdelista-undermeny'],[path])
                self.assertEqual(len(nav.links['bygdelista-delar']),4)
                self.assertEqual(self.client.post(path,data={'csrf_token':self.token()}).status_code,405)
        for endpoint,module_path in [('annual_fees','/okonomi'),('board_editor','/tilskipingar'),('event_editor','/tilskipingar')]:
            with fixtures.module.app.test_request_context('/'):
                from flask import render_template,request
                request.url_rule=type('Rule',(),{'endpoint':endpoint})()
                raw=render_template('_bygdelista_topp.html')+render_template('_bygdelista_undermeny.html')
                nav=Navigation();nav.feed(raw)
                self.assertEqual(nav.current['bygdelista-delar'],[module_path])
                self.assertEqual(len(nav.current['bygdelista-undermeny']),1)
