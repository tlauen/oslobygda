import unittest
from arsmelding_offentleg import presentation,validate_presentation
class PublicReportTests(unittest.TestCase):
 def test_allowlist_excludes_internal_sources_and_unselected_events(self):
  event=dict(included=True,source=dict(dato='2026-10-21',tittel='Pøbb',stad='Kaffistova',merknad='Omtale'),status='completed',participants=40,comment='Offentleg kommentar',origin='calendar',source_revision='internal',key='internal')
  report=dict(intro='Hei',organization='',conclusion='',activities=[event,dict(event,included=False)],membership=dict(count=3,checked_at='internal',source='payments'),source_revision='internal')
  result=presentation(report)
  self.assertEqual(len(result['activities']),1)
  self.assertEqual(result['activities'][0]['guests'],40)
  self.assertNotIn('source_revision',str(result));self.assertNotIn('checked_at',str(result))
  result['internal_note']='privat'
  with self.assertRaises(ValueError):validate_presentation(result)
