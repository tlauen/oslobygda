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

    def test_runner_blocks_dotenv_loading_without_a_test_branch_in_app(self):
        script = """
import sys, os
from unittest.mock import patch
from lokal_test import prepare
root, account = prepare(sys.argv[1])
assert os.environ['PYTHON_DOTENV_DISABLED'] == '1'
with patch('dotenv.main.DotEnv', side_effect=AssertionError('must not read dotenv')):
    import app as module
assert module.app.secret_key == account['session_key']
assert module.DB_KEY == ''
assert not os.environ.get('SMTP_HOST')
assert not os.environ.get('GITHUB_DOCUMENTS_TOKEN')
try:
    import wsgi
except RuntimeError as error:
    assert 'Lokal testmodus' in str(error)
else:
    raise AssertionError('WSGI accepted the local test runner')
print('dotenv blocked; WSGI rejected test runner')
"""
        with tempfile.TemporaryDirectory() as folder:
            env = dict(os.environ, PYTHON_DOTENV_DISABLED='0', SMTP_HOST='fake-production.invalid',
                       GITHUB_DOCUMENTS_TOKEN='fake-inherited-token', MEDLEMSREGISTER_SECRET_KEY='fake-inherited-key')
            result = subprocess.run([sys.executable, '-c', script, folder],
                                    cwd=Path(__file__).resolve().parents[1], env=env,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('dotenv blocked; WSGI rejected test runner', result.stdout)
