import unittest
from unittest.mock import patch

from betalingsreglar import manual_amount_ore, vipps_amount_ore, member_kind
from vipps_client import VippsClient


class AmountRuleTests(unittest.TestCase):
    def test_manual_amounts_keep_the_existing_range_and_optional_zero(self):
        for value, expected in [
            ("0.01", 1),
            ("5,50", 550),
            (5.5, 550),
            ("1e3", 100000),
            ("1000000000", 100000000000),
        ]:
            with self.subTest(value=value):
                self.assertEqual(manual_amount_ore(value), expected)
        self.assertEqual(manual_amount_ore("0", allow_zero=True), 0)
        for value in ("0", "-1", "1000000000.01", "NaN", "Infinity", True, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                manual_amount_ore(value)

    def test_subcent_values_are_never_rounded_into_valid_payments(self):
        for value in (
            "0.001",
            "1.001",
            "1.000000000000000000000000000001",
            "999999999.9999999999999999999999",
            "1e-1000",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                manual_amount_ore(value)
            with self.subTest(value=value, zero=True), self.assertRaises(ValueError):
                manual_amount_ore(value, allow_zero=True)

    def test_vipps_text_and_api_share_boundaries_and_reject_before_network(self):
        for text, ore in [("1", 100), ("5,50", 550), ("1000000", 100000000)]:
            with self.subTest(text=text):
                self.assertEqual(vipps_amount_ore(text), ore)
                client = VippsClient("fake-id", "fake-secret", "fake-key", "123456")
                with patch.object(client, "_authenticated") as api:
                    client.create(
                        "test-reference-123",
                        ore,
                        "https://example.invalid/return",
                        "create-key",
                    )
                    client.capture("test-reference-123", ore, "capture-key")
                    self.assertEqual(api.call_count, 2)
        for value in (True, 99, 100000001, 100.0, "100"):
            client = VippsClient("fake-id", "fake-secret", "fake-key", "123456")
            with (
                self.subTest(value=value),
                patch.object(client, "_authenticated") as api,
            ):
                with self.assertRaises(ValueError):
                    client.create(
                        "test-reference-123",
                        value,
                        "https://example.invalid/return",
                        "key",
                    )
                with self.assertRaises(ValueError):
                    client.capture("test-reference-123", value, "key")
                api.assert_not_called()
        for value in ("0.99", "1000000.01", "1e3", "1.001", 100, True):
            with self.subTest(text=value), self.assertRaises(ValueError):
                vipps_amount_ore(value)

    def test_strict_threshold_and_manual_board_role(self):
        self.assertEqual(member_kind(499, 500), "vanleg")
        self.assertEqual(member_kind(500, 500, "kul"), "vanleg")
        self.assertEqual(member_kind(501, 500), "kul")
        for role in ("styret", "Styret", " styret "):
            for total in (0, 500, 501):
                with self.subTest(role=role, total=total):
                    self.assertEqual(member_kind(total, 500, role), role)
