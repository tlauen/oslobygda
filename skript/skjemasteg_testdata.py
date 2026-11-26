"""Render ekte skjema mot mellombels testdatabase; ingen produksjonsdata/nettverk."""
import json
from unittest.mock import patch

import app as module
from arsdokument import Documents
from sakliste import Meetings, default_agenda
from test_styre_auth import BoardAuthTests

case = BoardAuthTests()
with patch.dict('os.environ', {'GITHUB_DOCUMENTS_TOKEN': '', 'GITHUB_CALENDAR_TOKEN': ''}):
    case.setUp()
    try:
        case.login()
        module.app.extensions['ledger'].opening(2026, {}, '', 'Testgrunnlag', 'styret', 'test-opening')
        module.app.extensions['budgets'].create(2027, 'styret')
        doc = Documents(module.get_db).create('arsmelding', 2026, 2027, 'styret')
        Meetings(module.get_db).save('sakliste', 2027, 0, default_agenda(2027))
        paths = ['/', '/okonomi?year=2026&del=registrer', '/okonomi?year=2026&del=oversikt',
                 '/okonomi?year=2026&del=kontroll', '/budsjett/2027', f'/arsmote/{doc}',
                 '/sakliste/2027', '/sakliste/2027/protokoll', '/kontingent', '/styret',
                 '/tilskipingar', '/nettsida/tekst', '/nettsida/tekst/om', '/nettsida/tekst/pub',
                 '/nettsida/pobb/galleri']
        data = {}
        for path in paths:
            response = case.client.get(path)
            assert response.status_code == 200, (path, response.status_code)
            data[path] = response.text
        print(json.dumps(data))
    finally:
        case.tearDown()
