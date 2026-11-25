from datetime import date
import unittest
from unittest.mock import patch
from database import managed_db
import app as module
import test_styre_auth as fixtures


class PublicRatesTests(unittest.TestCase):
    setUp = fixtures.BoardAuthTests.setUp
    tearDown = fixtures.BoardAuthTests.tearDown

    def rates(self, when, mode="production"):
        with (
            patch("kontingent.today", return_value=when),
            patch("offentleg_kontingent.today", return_value=when),
            patch.dict("os.environ", {"VIPPS_SIGNUP_MODE": mode}),
        ):
            return self.client.get(
                "/api/kontingent", headers={"Origin": "https://oslobygda.no"}
            )

    def test_public_exact_values_no_credentials_or_member_data(self):
        with managed_db(module.get_db) as db:
            db.execute(
                "UPDATE membership_periods SET minimum_ore=750, superkul_ore=1250 WHERE year=2026"
            )
        response = self.rates(date(2026, 11, 25))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json,
            {
                "year": 2026,
                "open": True,
                "currency": "NOK",
                "minimum_ore": 750,
                "superkul_ore": 1250,
            },
        )
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "*")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertNotIn("Set-Cookie", response.headers)
        self.assertNotIn("Access-Control-Allow-Credentials", response.headers)

    def test_draft_new_year_does_not_fall_back_to_last_year(self):
        with managed_db(module.get_db) as db:
            db.execute(
                "UPDATE membership_periods SET minimum_ore=12300, superkul_ore=45600 WHERE year=2027"
            )
        self.assertEqual(
            self.rates(date(2027, 1, 1)).json,
            {"year": 2027, "open": False, "currency": "NOK"},
        )

    def test_opening_date_and_disabled_payment(self):
        with managed_db(module.get_db) as db:
            db.execute(
                "UPDATE membership_periods SET opens_on='2026-12-01' WHERE year=2026"
            )
        self.assertFalse(self.rates(date(2026, 11, 25)).json["open"])
        self.assertTrue(self.rates(date(2026, 12, 1)).json["open"])
        self.assertEqual(
            self.rates(date(2026, 12, 1), "test").json,
            {"year": 2026, "open": False, "currency": "NOK"},
        )
