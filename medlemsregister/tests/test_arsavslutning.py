import sqlite3,unittest
from arsavslutning import closing_checklist
from rekneskap import init_ledger,Ledger
from pathlib import Path
from tempfile import TemporaryDirectory
class ChecklistTests(unittest.TestCase):
 def test_latest_difference_and_changed_journal_cannot_look_complete(self):
  with TemporaryDirectory() as temp:
   path=Path(temp)/'test.db'
   def db():
    c=sqlite3.connect(path);c.row_factory=sqlite3.Row;return c
   init_ledger(db);ledger=Ledger(db);ledger.opening(2026,{'bank':'100'},'','Test','test','opening')
   for account,value in [('bank','100'),('vipps','0'),('private','0')]:ledger.reconcile(2026,'2026-12-31',account,value,'','Test','test')
   with db() as c:self.assertTrue(closing_checklist(c,2026)['ready'])
   ledger.reconcile(2026,'2026-12-31','bank','99','','Test','test')
   with db() as c:
    state=closing_checklist(c,2026);self.assertFalse(state['ready']);self.assertEqual(state['rows'][0]['state'],'difference')
   ledger.reconcile(2026,'2026-12-31','bank','100','','Test','test')
   ledger.post(dict(kind='income',day='2026-02-01',amount='1',account='bank',category='membership',public_text='Test',evidence_note='Test'),'test','post')
   with db() as c:
    state=closing_checklist(c,2026);self.assertFalse(state['ready']);self.assertEqual(state['rows'][0]['state'],'stale')
