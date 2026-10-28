from pathlib import Path
import unittest
import app as module


class SharedFooterTests(unittest.TestCase):
    def test_css_reads_canonical_source(self):
        response=module.app.test_client().get('/felles/kolofon.css')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data,(Path(module.APP_DIR).parent/'lutar/kolofon.css').read_bytes())
        response.close()

    def test_footer_renders_from_shared_source_for_all_signup_states(self):
        with module.app.test_request_context():
            for state in ('CREATED','complete','TERMINATED','review'):
                html=module.render_template('innmelding_status.html',order=dict(status=state,for_year=2026,amount_ore=500,reference='test-only'),error=None,environment='test')
                self.assertIn('frilynt-forklaring',html)
                self.assertIn('/felles/kolofon.css',html)
                self.assertNotIn('/fast/kolofon.css',html)
        self.assertFalse((Path(module.APP_DIR)/'fast/kolofon.css').exists())
        self.assertFalse((Path(module.APP_DIR)/'malar/felles_kolofon.html').exists())
