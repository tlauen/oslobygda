import unittest
from pathlib import Path
from io import BytesIO
from werkzeug.datastructures import FileStorage
import app as module
import test_styre_auth as fixtures
from bilag import store_receipt
from okonomi_backup import create_bundle
from kryptert_backup import encrypt_bundle,verified_archive

class EncryptedBackupTests(unittest.TestCase):
    setUp=fixtures.BoardAuthTests.setUp
    tearDown=fixtures.BoardAuthTests.tearDown
    password='fiktiv-testpassfrase-minst-16-teikn'
    def bundle(self):
        root=Path(self.tmp.name)
        store_receipt(module.get_db,root/'bilag',FileStorage(stream=BytesIO(b'%PDF-1.4 FIKTIV-KVITTERING'),filename='receipt.pdf'),'styret')
        return create_bundle(module.DB_PATH,root/'bilag',root/'backup')
    def test_real_roundtrip_permissions_randomness_and_no_overwrite(self):
        bundle=self.bundle();root=Path(self.tmp.name)
        one=encrypt_bundle(bundle,root/'one.bkp',self.password)
        two=encrypt_bundle(bundle,root/'two.bkp',self.password)
        self.assertNotEqual(one.read_bytes(),two.read_bytes())
        self.assertNotIn(b'FIKTIV-KVITTERING',one.read_bytes())
        self.assertEqual(one.stat().st_mode&0o777,0o600)
        with verified_archive(one,self.password) as restored:
            self.assertEqual((restored/'database.db').read_bytes(),(bundle/'database.db').read_bytes())
            self.assertEqual(len(list((restored/'bilag').iterdir())),1)
        self.assertFalse(restored.exists())
        with self.assertRaises(ValueError): encrypt_bundle(bundle,one,self.password)
    def test_wrong_password_corruption_and_truncation_fail_closed(self):
        bundle=self.bundle();root=Path(self.tmp.name)
        output=encrypt_bundle(bundle,root/'original.bkp',self.password)
        with self.assertRaises(ValueError):
            with verified_archive(output,'anna-fiktiv-testpassfrase'): self.fail('Must not expose data')
        changed=bytearray(output.read_bytes());changed[-25]^=1
        (root/'corrupt.bkp').write_bytes(changed)
        with self.assertRaises(ValueError):
            with verified_archive(root/'corrupt.bkp',self.password): self.fail('Must not expose data')
        (root/'short.bkp').write_bytes(output.read_bytes()[:30])
        with self.assertRaises(ValueError):
            with verified_archive(root/'short.bkp',self.password): self.fail('Must not expose data')
        with self.assertRaises(ValueError): encrypt_bundle(bundle,root/'weak.bkp','short')
        self.assertEqual(list(root.glob('.kryptert-*')),[])
    def test_cli_hidden_prompt_and_restore(self):
        bundle=self.bundle();out=Path(self.tmp.name)/'cli.bkp'
        runner=module.app.test_cli_runner()
        result=runner.invoke(args=['okonomi-krypter-backup',str(bundle),'--output',str(out)],input=self.password+'\n'+self.password+'\n')
        self.assertEqual(result.exit_code,0,result.output)
        self.assertNotIn(self.password,result.output)
        result=runner.invoke(args=['okonomi-prove-kryptert-backup',str(out)],input=self.password+'\n')
        self.assertEqual(result.exit_code,0,result.output)
