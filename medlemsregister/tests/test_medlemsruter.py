from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from flask import Flask
from medlemsruter import install_members


class MemberRouteIsolationTests(unittest.TestCase):
    def test_two_apps_keep_separate_databases_without_importing_global_app(self):
        with tempfile.TemporaryDirectory() as folder:
            apps = []
            for index in (1, 2):
                path = Path(folder) / f"members-{index}.db"
                with closing(sqlite3.connect(path)) as db:
                    db.execute(
                        "CREATE TABLE members(id INTEGER PRIMARY KEY, full_name TEXT, privacy_deleted INTEGER)"
                    )
                    db.execute(
                        "INSERT INTO members VALUES (1,?,0)", (f"Fiktiv {index}",)
                    )
                    db.commit()

                def database(path=path):
                    db = sqlite3.connect(path)
                    db.row_factory = sqlite3.Row
                    return db

                app = Flask(f"isolated-members-{index}")
                install_members(
                    app,
                    database,
                    lambda view: view,
                    lambda db: 2026,
                    lambda db: 500,
                    lambda *args, **kwargs: None,
                    lambda db: None,
                )
                apps.append(app)
            for index in (0, 1, 0):
                response = apps[index].test_client().get("/api/members/1")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["full_name"], f"Fiktiv {index + 1}")
