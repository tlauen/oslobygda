import csv
import io
from pathlib import Path
from contextlib import closing
from unittest import TestCase
from unittest.mock import patch, Mock
import app as module
import test_styre_auth as fixtures
from ny_innmelding import SignupService
from personvern import process_privacy_jobs
from database import managed_db


class CleanupTests(TestCase):
    setUp = fixtures.BoardAuthTests.setUp
    tearDown = fixtures.BoardAuthTests.tearDown
    token = fixtures.BoardAuthTests.token

    def login(self):
        self.assertEqual(fixtures.BoardAuthTests.login(self).status_code, 302)

    def paid(self):
        service = module.app.extensions["signup_service"]
        values = dict(
            fornamn="Test",
            etternamn="Person",
            email="test@example.invalid",
            phone="99999999",
            adresse="Testvegen",
            postnummer="0001",
            poststad="Oslo",
            amount="10",
            terms="1",
            newsletter="1",
        )
        with patch("ny_innmelding.credentials", return_value={"VIPPS_MSN": "123456"}):
            ref = service.new(values, "browser-key", "production", "127.0.0.1")
        provider = Mock()
        provider.get.return_value = dict(
            reference=ref,
            amount=dict(currency="NOK", value=1000),
            state="AUTHORIZED",
            aggregate={
                k: dict(currency="NOK", value=v)
                for k, v in dict(
                    authorizedAmount=1000,
                    capturedAmount=1000,
                    cancelledAmount=0,
                    refundedAmount=0,
                ).items()
            },
        )
        with patch("ny_innmelding.client_for", return_value=provider):
            service.reconcile(ref)
        return service.order(ref)

    def test_optional_fields_clear_and_required_fields_reject_empty(self):
        self.login()
        o = self.paid()
        url = f"/api/members/{o['member_id']}"
        response = self.client.put(
            url,
            json={"phone": "", "birth_date": "", "mellomnamn": ""},
            headers={"X-CSRF-Token": self.token()},
        )
        self.assertEqual(response.status_code, 200)
        result = self.client.get(url).json
        self.assertEqual(result["phone"], "")
        self.assertIsNone(result["birth_date"])
        self.assertEqual(
            self.client.put(
                url, json={"fornamn": ""}, headers={"X-CSRF-Token": self.token()}
            ).status_code,
            400,
        )

    def test_csv_formula_is_literal(self):
        self.login()
        o = self.paid()
        self.client.put(
            f"/api/members/{o['member_id']}",
            json={"fornamn": "=1+1", "phone": "+4799999999"},
            headers={"X-CSRF-Token": self.token()},
        )
        response = self.client.get("/api/export/excel")
        rows = list(
            csv.reader(io.StringIO(response.data.decode("utf-8-sig")), delimiter=";")
        )
        self.assertEqual(rows[1][0], "'=1+1")
        self.assertEqual(rows[1][4], "'+4799999999")

    def test_legacy_endpoint_has_no_side_effects(self):
        with patch.object(module, "_brevo_request") as provider:
            self.assertEqual(
                self.client.post("/api/innmelding", json={}).status_code, 410
            )
            provider.assert_not_called()
        self.assertEqual(self.client.get("/innmelding").location, "/bli-medlem")

    def test_vipps_payment_cannot_be_deleted(self):
        self.login()
        o = self.paid()
        response = self.client.delete(
            f"/api/members/{o['member_id']}/payments/{o['payment_id']}",
            headers={"X-CSRF-Token": self.token()},
        )
        self.assertEqual(response.status_code, 409)
        with managed_db(module.get_db) as db:
            self.assertEqual(
                db.execute("SELECT amount_ore FROM payments").fetchone()[0], 1000
            )

    def test_erasure_removes_personal_data_but_preserves_anonymous_totals(self):
        self.login()
        o = self.paid()
        mid = o["member_id"]
        ref = o["reference"]
        result = self.client.post(
            f"/api/gdpr/delete/{mid}", headers={"X-CSRF-Token": self.token()}
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.client.get(f"/api/members/{mid}").status_code, 404)
        self.assertEqual(self.client.get("/api/members").json, [])
        self.assertEqual(
            self.client.get("/api/medlemsoversikt").json["totalt_innbetalt_ore"], 1000
        )
        self.assertEqual(
            self.client.get("/api/medlemsoversikt").json["antall_medlemer_totalt"], 0
        )
        with managed_db(module.get_db) as db:
            member = dict(
                db.execute("SELECT * FROM members WHERE id=?", (mid,)).fetchone()
            )
            for field in ("email", "phone", "adresse", "fornamn", "etternamn"):
                self.assertEqual(member[field], "")
        order = module.app.extensions["signup_service"].order(ref)
        self.assertEqual(order["email"], "")
        self.assertEqual(order["details"], "{}")
        self.assertEqual(order["status"], "redacted")
        with patch("ny_innmelding.client_for") as provider:
            module.app.extensions["signup_service"].reconcile(ref)
            provider.assert_not_called()
        delete = Mock(side_effect=[False, True])
        self.assertEqual(process_privacy_jobs(module.get_db, delete), 0)
        self.assertEqual(process_privacy_jobs(module.get_db, delete), 1)
        self.assertEqual(process_privacy_jobs(module.get_db, delete), 0)

    def test_newsletter_list_is_not_imported_as_members(self):
        self.login()
        with (
            patch.dict(
                "os.environ",
                {
                    "BREVO_API_KEY": "test",
                    "BREVO_INNMELDING_LIST_ID": "6",
                    "BREVO_MEDLEMMAR_LIST_ID": "",
                },
            ),
            patch.object(module, "_brevo_fetch_list_contacts") as provider,
        ):
            response = self.client.post(
                "/api/sync-contacts", headers={"X-CSRF-Token": self.token()}
            )
            self.assertEqual(response.status_code, 400)
            provider.assert_not_called()

    def test_database_is_closed_on_commit_and_exception(self):
        for fails in (False, True):
            connection = Mock()
            connection.__enter__ = Mock(return_value=connection)
            connection.__exit__ = Mock(return_value=False)
            try:
                with managed_db(lambda: connection):
                    if fails:
                        raise ValueError("test")
            except ValueError:
                pass
            connection.close.assert_called_once()

    def test_unsafe_crypto_migration_is_blocked_without_altering_source(self):
        module.DB_PATH.write_bytes(b"SQLite format 3\x00" + b"x" * 100)
        original = module.DB_PATH.read_bytes()
        with patch.object(module, "_use_sqlcipher", True):
            with self.assertRaises(RuntimeError):
                module._migrate_plain_to_encrypted()
        self.assertEqual(module.DB_PATH.read_bytes(), original)

    def test_pending_payment_blocks_erasure(self):
        self.login()
        o = self.paid()
        with managed_db(module.get_db) as db:
            db.execute(
                "UPDATE signup_orders SET status='AUTHORIZED' WHERE reference=?",
                (o["reference"],),
            )
        result = self.client.post(
            f"/api/gdpr/delete/{o['member_id']}", headers={"X-CSRF-Token": self.token()}
        )
        self.assertEqual(result.status_code, 409)
        self.assertEqual(
            self.client.get(f"/api/members/{o['member_id']}").status_code, 200
        )

    def test_production_preview_is_closed_to_public(self):
        with patch.dict("os.environ", {"VIPPS_SIGNUP_MODE": "production-preview"}):
            self.assertEqual(self.client.get("/bli-medlem").status_code, 503)
            self.login()
            self.assertEqual(self.client.get("/bli-medlem").status_code, 200)

    def test_oversize_request_is_rejected(self):
        self.assertEqual(
            self.client.post("/bli-medlem", data={"fornamn": "x" * 70000}).status_code,
            413,
        )

    def test_monthly_api_healthcheck_is_read_only_and_not_repeated(self):
        with (
            patch.dict(
                "os.environ", {"BREVO_API_KEY": "fake", "BREVO_INNMELDING_LIST_ID": "6"}
            ),
            patch.object(module, "_brevo_request", return_value=(200, {})) as api,
        ):
            module._privacy_maintenance()
            module._privacy_maintenance()
        api.assert_called_once_with("GET", "/contacts/lists/6", "fake")
