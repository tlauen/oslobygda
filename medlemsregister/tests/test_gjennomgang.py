"""Regresjonar frå den uavhengige kodegjennomgangen, med berre fiktive data."""

import unittest
from contextlib import contextmanager
from unittest.mock import Mock, patch

from database import managed_db
import app as module
import ny_innmelding
from kontingent import member_paid
import test_ny_innmelding as signup_fixtures


class ReviewRegressionTests(unittest.TestCase):
    setUp = signup_fixtures.SignupTests.setUp
    tearDown = signup_fixtures.SignupTests.tearDown
    token = signup_fixtures.SignupTests.token
    fields = signup_fixtures.SignupTests.fields
    new = signup_fixtures.SignupTests.new
    service = signup_fixtures.SignupTests.service
    details = signup_fixtures.SignupTests.details

    def test_payment_uses_edit_committed_before_write_lock(self):
        reference = self.new()
        original = ny_innmelding.managed_db
        interleaved = False

        @contextmanager
        def edit_before_lock(*args, **kwargs):
            nonlocal interleaved
            if not interleaved:
                interleaved = True
                self.service.edit(reference, self.fields(amount="200"))
            with original(*args, **kwargs) as db:
                yield db

        client = Mock()

        def create(*args):
            with self.assertRaises(ValueError):
                self.service.edit(reference, self.fields(amount="300"))
            return {"redirectUrl": "https://api.vipps.no/payment"}

        client.create.side_effect = create
        with (
            patch("ny_innmelding.managed_db", edit_before_lock),
            patch("ny_innmelding.client_for", return_value=client),
        ):
            self.service.create(reference, "https://example.org/status")
        self.assertEqual(client.create.call_args.args[1], 20000)
        self.assertEqual(self.service.order(reference)["amount_ore"], 20000)

    def paid(self):
        reference = self.new()
        client = Mock()
        client.get.return_value = self.details(reference, 10000)
        with patch("ny_innmelding.client_for", return_value=client):
            self.service.reconcile(reference)
        return self.service.order(reference)

    def admin_update(self, mid, values):
        from test_styre_auth import BoardAuthTests

        self.assertEqual(BoardAuthTests.login(self).status_code, 302)
        return self.client.put(
            f"/api/members/{mid}", json=values, headers={"X-CSRF-Token": self.token()}
        )

    def test_admin_email_updates_pending_confirmation(self):
        order = self.paid()
        response = self.admin_update(
            order["member_id"], {"email": "corrected@example.org"}
        )
        self.assertEqual(response.status_code, 200)
        with patch.object(self.service, "confirmation", return_value=True) as sender:
            self.service.send_confirmation(order["reference"])
        self.assertEqual(sender.call_args.args[0]["email"], "corrected@example.org")

    def test_admin_email_cannot_change_during_or_after_uncertain_sending(self):
        order = self.paid()
        from test_styre_auth import BoardAuthTests

        self.assertEqual(BoardAuthTests.login(self).status_code, 302)
        for state in ("sending", "review"):
            with managed_db(module.get_db) as db:
                db.execute("UPDATE signup_orders SET confirmation_status=?", (state,))
            response = self.client.put(
                f"/api/members/{order['member_id']}",
                json={"email": "corrected@example.org"},
                headers={"X-CSRF-Token": self.token()},
            )
            self.assertEqual(response.status_code, 409)
            with managed_db(module.get_db) as db:
                self.assertEqual(
                    db.execute("SELECT email FROM members").fetchone()[0],
                    "test@example.org",
                )

    def test_profile_save_does_not_create_paid_year(self):
        # The real UI submits a full member payload even when only a phone changes.
        from test_styre_auth import BoardAuthTests

        self.assertEqual(BoardAuthTests.login(self).status_code, 302)
        headers = {"X-CSRF-Token": self.token()}
        response = self.client.post(
            "/api/members",
            json=dict(fornamn="Test", etternamn="Medlem", email="manual@example.org"),
            headers=headers,
        )
        mid = response.json["id"]
        payment = self.client.post(
            f"/api/members/{mid}/payments", json={"amount_nok": "10"}, headers=headers
        )
        self.assertEqual(payment.status_code, 201)
        member = self.client.get(f"/api/members/{mid}").json
        payload = {
            key: member[key]
            for key in (
                "fornamn",
                "etternamn",
                "email",
                "membership_type",
                "payment_status",
            )
        }
        payload["phone"] = "99999999"
        self.assertEqual(
            self.client.put(
                f"/api/members/{mid}", json=payload, headers=headers
            ).status_code,
            200,
        )
        with managed_db(module.get_db) as db:
            pid = db.execute(
                "SELECT id FROM payments WHERE member_id=?", (mid,)
            ).fetchone()[0]
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM paid_membership_years WHERE member_id=?",
                    (mid,),
                ).fetchone()[0],
                0,
            )
        self.assertEqual(
            self.client.delete(
                f"/api/members/{mid}/payments/{pid}", headers=headers
            ).status_code,
            200,
        )
        with managed_db(module.get_db) as db:
            self.assertFalse(member_paid(db, mid, module._get_medlemsbetalingsar(db)))
        self.assertEqual(
            self.client.get(f"/api/members/{mid}").json["payment_status"],
            "ikkje betalt",
        )
        # An explicit approval of an unchanged status is still available.
        payload.update(payment_status="betalt", approve_payment_status=True)
        self.assertEqual(
            self.client.put(
                f"/api/members/{mid}", json=payload, headers=headers
            ).status_code,
            200,
        )
        with managed_db(module.get_db) as db:
            self.assertTrue(member_paid(db, mid, module._get_medlemsbetalingsar(db)))

    def test_verified_address_must_match_locked_order(self):
        reference = self.new()
        self.service.edit(reference, self.fields(email="changed@example.org"))
        with patch("ny_innmelding.client_for") as provider:
            with self.assertRaises(ny_innmelding.VippsError):
                self.service.create(
                    reference,
                    "https://example.org/status",
                    verified_email="test@example.org",
                )
            provider.assert_not_called()
        self.assertEqual(self.service.order(reference)["create_attempted"], 0)
