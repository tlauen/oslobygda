import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from okonomi_backup import create_bundle
from proton_backup import perform, ProtonBackupError


class FakeProton:
    def __init__(self): self.files={};self.uploads=0;self.downloads=0;self.corrupt=False;self.wrong_account=False
    def check_account(self,remote,account):
        if self.wrong_account: raise ProtonBackupError('Feil konto')
    def upload(self,source,destination): self.files[destination]=Path(source).read_bytes();self.uploads+=1
    def download(self,source,destination):
        data=self.files[source];self.downloads+=1
        Path(destination).write_bytes(data+b'corrupt' if self.corrupt else data)


class ProtonBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        db=self.root/'source.db'
        with sqlite3.connect(db) as conn:
            conn.executescript('CREATE TABLE members(id INTEGER PRIMARY KEY,name TEXT);CREATE TABLE payments(id INTEGER PRIMARY KEY);CREATE TABLE board_users(id INTEGER PRIMARY KEY);INSERT INTO members(name) VALUES (\'FIKTIV-MEDLEMSDATA\');')
        self.bundle=create_bundle(db,self.root/'receipts',self.root/'backups')
        key=self.root/'key';key.write_text('ei fiktiv og lang testpassfrase');key.chmod(0o600)
        self.settings=dict(account='laget@example.test',remote='proton:Tryggleikskopiar',rclone_binary='/unused/rclone',rclone_config=str(self.root/'config'),key_file=str(key),backup_directory=str(self.root/'backups'),export_directory=str(self.root/'exports'))
        self.client=FakeProton()
    def tearDown(self): self.tmp.cleanup()

    def test_encrypted_roundtrip_and_idempotence(self):
        result=perform(self.settings,self.client)
        self.assertEqual(result['status'],'verified')
        data=next(iter(self.client.files.values()))
        self.assertNotIn(b'FIKTIV-MEDLEMSDATA',data)
        self.assertTrue(data.startswith(b'BYGDELISTA-BACKUP-1\n'))
        self.assertEqual(perform(self.settings,self.client)['status'],'already_verified')
        self.assertEqual((self.client.uploads,self.client.downloads),(1,1))
        self.assertEqual((self.root/'exports/status.json').stat().st_mode&0o777,0o600)

    def test_corrupt_download_does_not_succeed_and_retry_resumes(self):
        self.client.corrupt=True
        with self.assertRaises(ProtonBackupError):perform(self.settings,self.client)
        self.assertNotIn('verified_at',(self.root/'exports/status.json').read_text())
        self.client.corrupt=False
        self.assertEqual(perform(self.settings,self.client)['status'],'verified')
        self.assertEqual((self.client.uploads,self.client.downloads),(1,2))

    def test_wrong_account_stops_before_upload(self):
        self.client.wrong_account=True
        with self.assertRaises(ProtonBackupError):perform(self.settings,self.client)
        self.assertEqual(self.client.uploads,0)

    def test_stale_source_or_public_key_file_stops_upload(self):
        old=time.time()-40*3600;os.utime(self.bundle,(old,old))
        with self.assertRaises(ProtonBackupError):perform(self.settings,self.client)
        os.utime(self.bundle,None)
        Path(self.settings['key_file']).chmod(0o644)
        with self.assertRaises(ProtonBackupError):perform(self.settings,self.client)
        self.assertEqual(self.client.uploads,0)
