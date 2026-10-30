import os,re,io,zipfile
from pathlib import Path
from unittest.mock import patch
from test_styre_auth import BoardAuthTests
from styremodul import load_board
import unittest

class BoardEditorTests(unittest.TestCase):
    token=BoardAuthTests.token
    login=BoardAuthTests.login
    def setUp(self):
        BoardAuthTests.setUp(self)
        self.env=patch.dict(os.environ,{'BYGDELISTA_STYRE_FILE':str(Path(self.tmp.name)/'styre.yml')});self.env.start()
    def tearDown(self):
        self.env.stop();BoardAuthTests.tearDown(self)
    def test_auth_save_year_snapshot_and_stale_form(self):
        self.assertEqual(self.client.get('/styret').status_code,302)
        self.login();page=self.client.get('/styret?year=2027');self.assertEqual(page.status_code,200)
        revision=re.search(rb'name="revision" value="([a-f0-9]+)"',page.data)[1].decode()
        form=dict(csrf_token=self.token(),year='2027',revision=revision,index='-1',name='Døme Person',role='Leiar')
        self.assertEqual(self.client.post('/styret',data=form).status_code,302)
        self.assertEqual(load_board(2027)['people'][0]['namn'],'Døme Person')
        self.assertEqual(len(load_board(2026)['people']),3)
        self.assertEqual(self.client.post('/styret',data=form).status_code,400)
        self.assertEqual(len(load_board(2027)['people']),1)
        response=self.client.get('/styret/nettsidepakke');self.assertEqual(response.status_code,200)
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:self.assertIn('_data/styre.yml',archive.namelist())
        self.assertEqual(self.client.post('/styret',data={}).status_code,400)
