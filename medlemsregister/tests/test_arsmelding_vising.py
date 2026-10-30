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

    def test_intro_precedes_statistics_and_age_graph_handles_empty_register(self):
        env=Environment(loader=FileSystemLoader(Path(__file__).resolve().parents[1]/'malar'),autoescape=select_autoescape())
        report=dict(membership=dict(count=0,year=2026,ages=dict(age_0_14=0,age_15_25=0,age_26_plus=0,unknown=0,as_of='2026-12-31')),intro='Innleiing først',organization='',conclusion='',activities=[])
        html=env.get_template('_arsmelding_vising.html').render(report=report,report_year=2026)
        self.assertLess(html.index('Innleiing først'),html.index('Nøkkeltal for året'))
        self.assertEqual(html.count('class="aldersgraf-rad"'),4)
        self.assertIn('width:0%',html)
        self.assertNotIn('Aktivitetane, menneska og augneblikka',html)
