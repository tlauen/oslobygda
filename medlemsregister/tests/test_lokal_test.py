"""Testmiljøet må prøvast i eigen prosess fordi sperrene ikkje kan avinstallerast."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

class LocalEnvironmentTests(unittest.TestCase):
    def test_isolation_and_real_login_with_inherited_production_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            env=dict(os.environ,SMTP_HOST='must-not-be-used.invalid',GITHUB_DOCUMENTS_TOKEN='fake-inherited-token',
                     MEDLEMSREGISTER_SECRET_KEY='must-not-be-used',MEDLEMSREGISTER_DB_KEY='must-not-be-used')
            result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'lokal_test.py'),
                                   '--data-dir',folder,'--check'],capture_output=True,text=True,env=env,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('separat database og sperra nettverk: OK',result.stdout)
            self.assertTrue((Path(folder)/'nidarosbygda.db').exists())
            self.assertEqual((Path(folder)/'testkonto.json').stat().st_mode & 0o777,0o600)

    def test_refuses_existing_unmarked_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            sentinel=Path(folder)/'existing.txt';sentinel.write_text('preserve')
            result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'lokal_test.py'),
                                   '--data-dir',folder,'--check'],capture_output=True,text=True,timeout=30)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(sentinel.read_text(),'preserve')
            self.assertFalse((Path(folder)/'nidarosbygda.db').exists())
