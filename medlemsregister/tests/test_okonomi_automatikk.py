import csv
import io
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import app as module
import test_betalingsimport as fixtures
from database import managed_db
from okonomi_automatikk import finance_lock
from vipps_client import VippsError
from vipps_rapport import ReportImport, parse_report
from vipps_rapport_api import fetch_reports


class AutomationTests(unittest.TestCase):
    setUp = fixtures.ImportTests.setUp
    tearDown = fixtures.ImportTests.tearDown
    service = fixtures.ImportTests.service
    ledger = fixtures.ImportTests.ledger
    payment = fixtures.ImportTests.payment
    opening = fixtures.ImportTests.opening
    provider = fixtures.ImportTests.provider

    # Reuse setup/helpers, not inherited test cases in the extra suite.
    def test_failed_first_batch_does_not_starve_later_payments(self):
        self.opening()
        pids = [self.payment(True)[0] for _ in range(51)]
        good = self.provider(pids[-1], timestamp=datetime.now(timezone.utc).isoformat())
        self.service.fetch(pids[-1], "styret", lambda *a: good)
        from arsdokument import today

        self.service.configure(True, today().isoformat(), "styret")
        bad = Mock()
        bad.get.side_effect = VippsError("Nettverk")
        self.assertEqual(self.service.run(True, 50, lambda *a: bad)["review"], 50)
        self.assertEqual(self.service.run(True, 50, lambda *a: good)["booked"], 1)
        self.assertEqual(
            self.service.run(True, 50, lambda *a: self.fail("Backoff ignored"))[
                "checked"
            ],
            0,
        )

    def test_batch_approval_atomic_idempotent_and_evidence_history_compact(self):
        self.opening()
        pid, _ = self.payment(True)
        client = self.provider(pid, timestamp=datetime.now(timezone.utc).isoformat())
        token, rows = self.service.preview("styret", client_factory=lambda *a: client)
        self.assertEqual(rows[0]["status"], "ready")
        first = self.service.approve(token, "styret")
        self.assertEqual(first, self.service.approve(token, "styret"))
        for _ in range(3):
            self.service.fetch(pid, "styret", lambda *a: client)
        with managed_db(module.get_db) as db:
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM payment_evidence WHERE payment_id=?", (pid,)
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM ledger_journals WHERE source_kind='membership_payment'"
                ).fetchone()[0],
                1,
            )
        other, _ = self.payment(True)
        other_client = self.provider(
            other, timestamp=datetime.now(timezone.utc).isoformat()
        )
        token, _ = self.service.preview(
            "styret", client_factory=lambda *a: other_client
        )
        with managed_db(module.get_db) as db:
            db.execute("UPDATE payments SET amount_ore=11000 WHERE id=?", (other,))
        with self.assertRaises(ValueError):
            self.service.approve(token, "styret")

    def test_lease_and_disable_after_original_start_date(self):
        self.opening()
        pid, _ = self.payment(True)
        client = self.provider(pid)
        self.service.fetch(pid, "styret", lambda *a: client)
        self.service.configure(False, "2026-01-01", "styret")
        with managed_db(module.get_db) as db:
            self.assertEqual(
                db.execute("SELECT enabled FROM payment_import_settings").fetchone()[0],
                0,
            )
        with (
            finance_lock(module.get_db, "payments"),
            self.assertRaises(ValueError),
            finance_lock(module.get_db, "payments"),
        ):
            pass


class ReportTests(unittest.TestCase):
    setUp = fixtures.ImportTests.setUp
    tearDown = fixtures.ImportTests.tearDown

    def csv(self, rows):
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(
            [
                "MSN/Vippsnummer",
                "Bokføringsdato",
                "Tidspunkt",
                "Type",
                "Beløp",
                "Valuta",
                "PSP-referanse",
                "Ordre-ID/Referanse",
                "Utbetalingsnummer",
            ]
        )
        for kind, amount, psp, ref, payout in rows:
            writer.writerow(
                [
                    "123456",
                    "2026-01-05",
                    "2026-01-05 12:00:00",
                    kind,
                    amount,
                    "NOK",
                    psp,
                    ref,
                    payout,
                ]
            )
        return out.getvalue().encode()

    @property
    def service(self):
        return ReportImport(module.get_db, module._oppdater_fra_innbetalingar)

    def opening(self):
        module.app.extensions["ledger"].opening(
            2026, {}, "", "Kontrollert", "styret", "opening"
        )

    def identity(self, kind):
        with managed_db(module.get_db) as db:
            return db.execute(
                "SELECT identity FROM vipps_report_entries WHERE kind=?", (kind,)
            ).fetchone()[0]

    def test_overlapping_reports_fees_and_actual_bank_payout(self):
        self.opening()
        raw = self.csv(
            [
                ("Belastning", "100", "c1", "direct-1", ""),
                ("Gebyrer fratrukket", "-2", "f1", "", ""),
                ("Utbetaling planlagt", "-98", "1-2000001", "", "2000001"),
            ]
        )
        self.assertEqual(self.service.ingest(raw, "123456")["new"], 3)
        self.assertEqual(self.service.ingest(raw, "123456")["known"], 3)
        capture = self.identity("capture")
        choices = {capture: {"category": "donations"}}
        token, rows = self.service.preview(choices, "styret")
        self.assertEqual(
            next(r for r in rows if r["kind"] == "payout")["plan"]["status"], "review"
        )
        result = self.service.approve(token, "styret")
        self.assertEqual(len(result), 2)
        self.assertEqual(result, self.service.approve(token, "styret"))
        count = self.service.bank_csv(
            b"Dato;Bel\xc3\xb8p;Referanse\n2026-01-06;98;Vipps 2000001\n", "styret"
        )
        self.assertEqual(count, 1)
        token, _ = self.service.preview({}, "styret")
        self.assertEqual(len(self.service.approve(token, "styret")), 1)
        with managed_db(module.get_db) as db:
            totals = dict(
                db.execute(
                    "SELECT account,SUM(amount_ore) FROM ledger_lines GROUP BY account"
                )
            )
            self.assertEqual(totals["vipps"], 0)
            self.assertEqual(totals["bank"], 9800)
            self.assertEqual(totals["fees"], 200)
        changed = self.csv([("Belastning", "101", "c1", "direct-1", "")])
        with self.assertRaises(ValueError):
            self.service.ingest(changed, "123456")

    def test_fee_credit_and_manual_bank_confirmation_are_checked(self):
        self.opening()
        self.service.ingest(
            self.csv(
                [
                    ("Gebyrer fratrukket", "2", "credit-1", "", ""),
                    ("Utbetaling planlagt", "-98", "1-2000002", "", "2000002"),
                ]
            ),
            "123456",
        )
        payout = self.identity("payout")
        with self.assertRaises(ValueError):
            self.service.confirm_bank(payout, "2026-01-06", "97", "Bankref", "styret")
        self.service.confirm_bank(payout, "2026-01-06", "98", "Bankref", "styret")
        self.service.confirm_bank(payout, "2026-01-06", "98", "Bankref", "styret")
        with self.assertRaises(ValueError):
            self.service.confirm_bank(payout, "2026-01-07", "98", "Anna", "styret")
        token, rows = self.service.preview({}, "styret")
        self.assertTrue(all(row["plan"]["status"] == "ready" for row in rows))
        self.assertEqual(len(self.service.approve(token, "styret")), 2)
        with managed_db(module.get_db) as db:
            self.assertEqual(
                db.execute(
                    "SELECT SUM(amount_ore) FROM ledger_lines WHERE account='fees'"
                ).fetchone()[0],
                -200,
            )

    def test_unknown_types_and_missing_stable_identifiers_never_auto_book(self):
        self.service.ingest(
            self.csv([("Ny ukjend type", "10", "new1", "", "")]), "123456"
        )
        _, rows = self.service.preview({}, "styret")
        self.assertEqual(rows[0]["plan"]["status"], "review")
        with self.assertRaises(ValueError):
            parse_report(self.csv([("Belastning", "10", "", "", "")]), "123456")
        with self.assertRaises(ValueError):
            parse_report(self.csv([("Belastning", "-10", "c1", "", "")]), "123456")
        with self.assertRaises(ValueError):
            parse_report(self.csv([("Belastning", "10", "c1", "", "")]), "999")

    @patch.dict(
        os.environ, {"VIPPS_REPORT_FETCH_ENABLED": "1", "VIPPS_REPORT_LEDGER_ID": "123"}
    )
    def test_report_api_get_only_pagination_cursor_and_no_gdpr(self):
        client = Mock()
        client.headers = {"Merchant-Serial-Number": "123456"}
        ledger = {
            "items": [
                {
                    "ledgerId": "123",
                    "currency": "NOK",
                    "settlesForRecipientHandles": ["api:123456"],
                }
            ]
        }
        item = {
            "pspReference": "c1",
            "time": "2026-01-05T12:00:00Z",
            "ledgerDate": "2026-01-05",
            "entryType": "capture",
            "currency": "NOK",
            "amount": 500,
            "recipientHandle": "api:123456",
            "reference": "x",
        }
        client._authenticated.side_effect = [
            ledger,
            {
                "items": [item, {**item, "pspReference": "c2", "reference": "y"}],
                "cursor": "a",
                "tryLater": False,
            },
            {"items": [], "cursor": "a", "tryLater": True},
        ]
        self.assertEqual(fetch_reports(self.service, lambda: client)["new"], 2)
        calls = client._authenticated.call_args_list
        self.assertTrue(all(call.args[0] == "GET" for call in calls))
        self.assertNotIn("includeGDPRSensitiveData", str(calls))
        self.assertIn("cursor=a", calls[-1].args[1])
        with managed_db(module.get_db) as db:
            self.assertEqual(
                db.execute("SELECT cursor FROM vipps_report_cursors").fetchone()[0], "a"
            )

    def test_refund_limits_and_manual_member_choice(self):
        self.opening()
        raw = self.csv([("Belastning", "100", "original", "x", "")])
        self.service.ingest(raw, "123456")
        identity = self.identity("capture")
        token, rows = self.service.preview({}, "styret")
        self.assertEqual(rows[0]["plan"]["status"], "review")
        token, _ = self.service.preview({identity: {"category": "donations"}}, "styret")
        original = self.service.approve(token, "styret")[0]
        self.service.ingest(
            self.csv([("Refusjon", "-20", "refund1", "x", "")]), "123456"
        )
        refund = self.identity("refund")
        token, _ = self.service.preview(
            {refund: {"original_journal": str(original)}}, "styret"
        )
        self.assertEqual(len(self.service.approve(token, "styret")), 1)
        self.service.ingest(
            self.csv([("Refusjon", "-90", "refund2", "x", "")]), "123456"
        )
        with managed_db(module.get_db) as db:
            last = db.execute(
                "SELECT identity FROM vipps_report_entries WHERE psp_reference='refund2'"
            ).fetchone()[0]
        _, rows = self.service.preview(
            {last: {"original_journal": str(original)}}, "styret"
        )
        self.assertEqual(rows[0]["plan"]["status"], "review")

    @patch.dict(
        os.environ, {"VIPPS_REPORT_FETCH_ENABLED": "0", "VIPPS_REPORT_LEDGER_ID": ""}
    )
    def test_only_verified_api_fees_are_automatic_not_uploaded_csv(self):
        from okonomi_automatikk import fingerprint
        from vipps_rapport_api import automate_reports

        self.opening()
        payload = {
            "msn": "123456",
            "kind": "fee",
            "reference": "",
            "psp_reference": "api-fee",
            "day": "2026-01-05",
            "booking_day": "2026-01-05",
            "amount_ore": -200,
            "payout": "",
            "origin": "api",
        }
        self.service.ingest_entries(
            [(fingerprint(["123456", "fee", "api-fee"]), payload)]
        )
        self.service.ingest(
            self.csv([("Gebyrer fratrukket", "-3", "csv-fee", "", "")]), "123456"
        )
        with managed_db(module.get_db) as db:
            db.execute(
                "INSERT INTO payment_import_settings VALUES (1,1,'2026-01-01','styret','x')"
            )
        self.assertEqual(automate_reports(self.service)["booked"], 1)
        self.assertEqual(automate_reports(self.service)["booked"], 0)
        with managed_db(module.get_db) as db:
            row = db.execute(
                "SELECT journal_id FROM vipps_report_entries WHERE psp_reference='csv-fee'"
            ).fetchone()
            self.assertIsNone(row[0])
