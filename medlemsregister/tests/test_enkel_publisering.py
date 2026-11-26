import json
import unittest
from unittest.mock import patch

import app as module
import test_styre_auth as fixtures
from budsjett import CATEGORIES
from database import managed_db


class SimplePublicationTests(unittest.TestCase):
    setUp = fixtures.BoardAuthTests.setUp
    tearDown = fixtures.BoardAuthTests.tearDown
    token = fixtures.BoardAuthTests.token

    def test_unchanged_annual_report_reuses_revision_and_snapshot(self):
        service = module.app.extensions.get("annual_documents", None)
        from arsdokument import Documents

        service = Documents(module.get_db)
        doc = service.create("arsmelding", 2026, 2027, "styret")
        with managed_db(module.get_db) as db:
            db.execute(
                "UPDATE annual_documents SET report_json='{}',body='Året vårt' WHERE id=?",
                (doc,),
            )
        service.save(doc, 1, "Årsmelding 2026", "Året vårt", 2027, "styret")
        with managed_db(module.get_db) as db:
            revision = db.execute(
                "SELECT revision FROM annual_documents WHERE id=?", (doc,)
            ).fetchone()[0]
        vid = service.freeze(doc, revision, "meeting", "", "styret")
        service.save(doc, revision, "Årsmelding 2026", "Året vårt", 2027, "styret")
        self.assertEqual(service.freeze(doc, revision, "meeting", "", "styret"), vid)

    def test_unchanged_budget_and_other_year_ledger_do_not_create_versions(self):
        service = module.app.extensions["budgets"]
        service.create(2027, "styret")
        with managed_db(module.get_db) as db:
            row = db.execute("SELECT * FROM budgets WHERE year=2027").fetchone()
            content = json.loads(row["content"])
        form = dict(
            title=content["title"],
            note=content["note"],
            meeting_year=content["meeting_year"],
            **{"amount_" + code: "0" for code in CATEGORIES},
        )
        service.update(2027, 1, "styret", "save", form)
        with managed_db(module.get_db) as db:
            self.assertEqual(
                db.execute("SELECT revision FROM budgets WHERE year=2027").fetchone()[
                    0
                ],
                1,
            )
        ledger = module.app.extensions["ledger"]
        public = module.app.extensions["public_ledger"]
        ledger.opening(2026, {}, "", "Kontrollert", "styret", "opening")
        report = public.preview(2026)
        public.activate(2026, "styret", report["source_revision"])
        with managed_db(module.get_db) as db:
            before = db.execute(
                "SELECT COUNT(*) FROM public_ledger_versions"
            ).fetchone()[0]
        ledger.post(
            {
                "kind": "income",
                "day": "2027-01-01",
                "amount": "100",
                "account": "bank",
                "category": "donations",
                "public_text": "Gåve",
                "evidence_note": "Kontrollert bank",
            },
            "styret",
            "future-gift",
        )
        public.refresh_enabled()
        with managed_db(module.get_db) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM public_ledger_versions").fetchone()[0],
                before,
            )

    def test_budget_can_save_and_publish_from_editor_without_intermediate_page(self):
        fixtures.BoardAuthTests.login(self)
        service = module.app.extensions["budgets"]
        service.create(2027, "styret")
        with managed_db(module.get_db) as db:
            json.loads(
                db.execute("SELECT content FROM budgets WHERE year=2027").fetchone()[0]
            )
        form = dict(
            action="publish_current",
            revision=1,
            csrf_token=self.token(),
            title="Nytt budsjett",
            note="",
            meeting_year=2027,
            **{"amount_" + code: "0" for code in CATEGORIES},
        )
        with patch("publisering.publish_from_button") as publish:
            self.assertEqual(
                self.client.post("/budsjett/2027", data=form).status_code, 302
            )
            publish.assert_called_once()
        with managed_db(module.get_db) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM budget_versions").fetchone()[0], 1
            )
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM budget_publication_queue").fetchone()[
                    0
                ],
                1,
            )
