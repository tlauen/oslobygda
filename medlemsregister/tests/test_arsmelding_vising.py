import unittest
from pathlib import Path
from jinja2 import Environment,FileSystemLoader,select_autoescape

class ReportPresentationTests(unittest.TestCase):
    def test_only_included_completed_events_contribute_to_statistics(self):
        env=Environment(loader=FileSystemLoader(Path(__file__).resolve().parents[1]/'malar'),autoescape=select_autoescape())
        def activity(title,status,number,included=True):
            return dict(included=included,status=status,participants=number,comment='',source=dict(dato='2026-09-01',tittel=title,stad='',merknad=''))
        report=dict(membership=None,intro='<script>unsafe</script>',organization='',conclusion='',activities=[activity('Gjennomført','completed',42),activity('Avlyst','cancelled',99),activity('Utelaten','completed',50,False)])
        html=env.get_template('_arsmelding_vising.html').render(report=report,report_year=2026)
        self.assertIn('<strong>42</strong>',html)
        self.assertIn('<strong>1</strong>',html)
        self.assertNotIn('Utelaten',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertIn('Betalingstal er ikkje henta enno.',html)
        report['activities']=[]
        html=env.get_template('_arsmelding_vising.html').render(report=report,report_year=2026)
        self.assertIn('Ingen deltakartal er registrerte',html)
