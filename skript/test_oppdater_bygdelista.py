import subprocess
import tempfile
import unittest
from pathlib import Path

from oppdater_bygdelista import allowed, install, SHARED


class DeploymentTests(unittest.TestCase):
    def test_only_code_is_copied_and_old_code_is_backed_up(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, target, backups = root / 'source', root / 'active', root / 'backup'
            source.mkdir(); target.mkdir()
            for name in SHARED | {'medlemsregister/app.py', 'medlemsregister/wsgi.py', 'medlemsregister/requirements-pythonanywhere.txt'}:
                p = source / name; p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('pass\n' if p.suffix == '.py' else 'new code\n')
            for name in ('medlemsregister/.env', 'medlemsregister/member.db', 'medlemsregister/_site/old.py'):
                p = source / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('must never deploy')
            active = target / 'medlemsregister'; active.mkdir()
            (active / '.env').write_text('runtime secret sentinel')
            (active / 'member.db').write_text('runtime data sentinel')
            (active / 'app.py').write_text('# old code\n')
            subprocess.run(['git', 'init', '-q', str(source)], check=True)
            subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(source), '-c', 'user.name=Test', '-c', 'user.email=test@example.org', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'test'], check=True)
            install(source, target, backups, dry_run=True)
            self.assertEqual((active / 'app.py').read_text(), '# old code\n')
            install(source, target, backups)
            self.assertEqual((active / 'app.py').read_text(), 'pass\n')
            self.assertEqual((active / '.env').read_text(), 'runtime secret sentinel')
            self.assertEqual((active / 'member.db').read_text(), 'runtime data sentinel')
            self.assertFalse((active / '_site').exists())
            import tarfile
            archives = list(backups.glob('*.tar.gz'))
            self.assertEqual(len(archives), 1)
            with tarfile.open(archives[0]) as archive:
                self.assertEqual(archive.extractfile('medlemsregister/app.py').read(), b'# old code\n')
            install(source, target, backups)
            self.assertEqual(len(list(backups.glob('*.tar.gz'))), 1)
            (active / 'app.py').unlink()
            (active / 'app.py').symlink_to(active / 'member.db')
            with self.assertRaises(RuntimeError):
                install(source, target, backups)

    def test_disallows_runtime_and_unsafe_paths(self):
        for name in ('/medlemsregister/app.py', 'medlemsregister/../app.py', 'medlemsregister/.env', 'medlemsregister/.env.vipps-test', 'medlemsregister/member.db-wal', 'medlemsregister/_site/app.py', 'medlemsregister/backups/export.json'):
            self.assertFalse(allowed(name), name)
        self.assertTrue(allowed('medlemsregister/malar/ny_innmelding.html'))


if __name__ == '__main__':
    unittest.main()
