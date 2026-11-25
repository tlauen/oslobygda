"""Køyr: python -m unittest discover -s tests (frå medlemsregister/)."""
import unittest

import app as module


class SecurityHeaderTests(unittest.TestCase):
    def setUp(self):
        self.previous = module.app.config.get("SESSION_COOKIE_SECURE")
        self.client = module.app.test_client()

    def tearDown(self):
        module.app.config["SESSION_COOKIE_SECURE"] = self.previous

    def test_secret_key_is_never_the_old_default(self):
        self.assertNotEqual(module.app.secret_key, "endre-meg-i-produksjon")

    def test_referrer_policy_is_always_set(self):
        response = self.client.get("/login")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")

    def test_hsts_only_when_cookies_are_secure(self):
        module.app.config["SESSION_COOKIE_SECURE"] = False
        self.assertNotIn("Strict-Transport-Security", self.client.get("/login").headers)
        module.app.config["SESSION_COOKIE_SECURE"] = True
        self.assertEqual(
            self.client.get("/login").headers["Strict-Transport-Security"],
            "max-age=31536000",
        )


if __name__ == "__main__":
    unittest.main()
