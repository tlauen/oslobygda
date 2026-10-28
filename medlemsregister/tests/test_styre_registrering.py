import time
import base64
import re
import segno
import unittest
from unittest.mock import patch

import pyotp
import app as module
import test_styre_auth as fixtures


class RegistrationTests(unittest.TestCase):
    token = fixtures.BoardAuthTests.token

    def setUp(self):
        fixtures.BoardAuthTests.setUp(self)
        with module.get_db() as db:
            db.execute("""INSERT INTO members(full_name,email,membership_type,payment_status,consent_at,created_at,updated_at)
                          VALUES ('Test','board@example.org','styret','ikkje betalt','2026','2026','2026')""")
        self.ready = patch("styre_registrering.mail_ready", return_value=True)
        self.sender = patch("styre_registrering.send_code")
        self.ready.start()
        self.send = self.sender.start()

    def tearDown(self):
        self.sender.stop()
        self.ready.stop()
        fixtures.BoardAuthTests.tearDown(self)

    def start(self, email="board@example.org"):
        return self.client.post(
            "/registrer", data={"email": email, "csrf_token": self.token()}
        )

    def verify(self, code=None):
        return self.client.post(
            "/registrer/stadfest",
            data={
                "email_code": code or self.send.call_args.args[1],
                "csrf_token": self.token(),
            },
        )

    def finish(self, code=None):
        with module.get_db() as db:
            row = db.execute("SELECT totp_secret FROM board_enrollment").fetchone()
        return self.client.post(
            "/registrer/konto",
            data={
                "password": "a very long new password",
                "confirmation": "a very long new password",
                "code": code or pyotp.TOTP(row[0]).now(),
                "csrf_token": self.token(),
            },
        )

    def test_email_password_totp_and_login(self):
        self.assertEqual(self.start().status_code, 302)
        self.assertEqual(self.client.get("/registrer/konto").status_code, 400)
        self.assertEqual(self.verify().status_code, 302)
        response = self.client.get("/registrer/konto")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(self.finish().status_code, 200)
        with module.get_db() as db:
            user = db.execute(
                "SELECT * FROM board_users WHERE username='board@example.org'"
            ).fetchone()
            self.assertIsNotNone(user["member_id"])
            self.assertNotEqual(user["password_hash"], "a very long new password")
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM board_enrollment").fetchone()[0], 0
            )
        # Neste tidssteg: koden brukt ved oppretting kan ikkje brukast på nytt.
        now = int(time.time()) + 60
        with patch("styre_auth.time.time", return_value=now):
            response = self.client.post(
                "/login",
                data={
                    "username": "board@example.org",
                    "password": "a very long new password",
                    "code": pyotp.TOTP(user["totp_secret"]).at(now),
                    "csrf_token": self.token(),
                },
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(self.client.get("/api/members").status_code, 200)
            with module.get_db() as db:
                db.execute("UPDATE members SET membership_type='vanleg'")
            self.assertEqual(
                self.client.get(
                    "/api/members", headers={"Accept": "application/json"}
                ).status_code,
                401,
            )

    def test_qr_contains_matching_totp_and_is_only_shown_after_email_verification(self):
        self.start()
        self.assertNotIn(b"data:image/png", self.client.get("/registrer/stadfest").data)
        self.assertEqual(self.client.get("/registrer/konto").status_code, 400)
        self.verify()
        with module.get_db() as db:
            secret = db.execute("SELECT totp_secret FROM board_enrollment").fetchone()[
                0
            ]
        with patch("styre_registrering.segno.make_qr", wraps=segno.make_qr) as generate:
            response = self.client.get("/registrer/konto")
        uri = generate.call_args.args[0]
        authenticator = pyotp.parse_uri(uri)
        self.assertEqual(authenticator.secret, secret)
        self.assertEqual(authenticator.name, "board@example.org")
        self.assertEqual(authenticator.issuer, "Bygdelista")
        self.assertEqual(authenticator.now(), pyotp.TOTP(secret).now())
        encoded = re.search(
            rb'src="data:image/png;base64,([^"]+)"', response.data
        ).group(1)
        self.assertTrue(base64.b64decode(encoded).startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        # QR-koden er òg tilgjengeleg når brukaren må rette passord/kode.
        self.assertIn(b"data:image/png;base64,", self.finish("wrong").data)

    def test_no_membership_disclosure_or_nonboard_enrollment(self):
        expected = self.start("unknown@example.org")
        self.send.assert_not_called()
        with module.get_db() as db:
            db.execute("UPDATE members SET membership_type='vanleg'")
        response = self.start()
        self.assertEqual(response.status_code, expected.status_code)
        self.assertEqual(response.location, expected.location)
        self.send.assert_not_called()

    def test_duplicate_email_and_existing_account_denied(self):
        with module.get_db() as db:
            db.execute(
                "INSERT INTO members (id,full_name,fornamn,mellomnamn,etternamn,email,phone,adresse,postnummer,poststad,birth_date,membership_type,payment_status,consent_at,created_at,updated_at) SELECT id+100,full_name,fornamn,mellomnamn,etternamn,email,phone,adresse,postnummer,poststad,birth_date,membership_type,payment_status,consent_at,created_at,updated_at FROM members"
            )
        self.start()
        self.send.assert_not_called()
        with module.get_db() as db:
            db.execute("DELETE FROM members WHERE id>100")
            db.execute("UPDATE board_users SET username='board@example.org',active=0")
        self.start()
        self.send.assert_not_called()

    def test_attempt_limit_expiry_and_no_replay(self):
        self.start()
        for _ in range(5):
            self.assertEqual(self.verify("not-code").status_code, 400)
        self.assertEqual(self.verify().status_code, 400)
        self.start()
        with patch("styre_registrering.time.time", return_value=int(time.time()) + 901):
            self.assertEqual(self.verify().status_code, 400)
        self.start()
        self.assertEqual(self.verify().status_code, 302)
        self.assertEqual(self.verify().status_code, 400)

    def test_role_checked_again_at_completion(self):
        self.start()
        self.verify()
        with module.get_db() as db:
            db.execute("UPDATE members SET membership_type='vanleg'")
        self.assertEqual(self.finish().status_code, 400)
        with module.get_db() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM board_users").fetchone()[0], 1
            )

    def test_wrong_totp_and_missing_csrf_do_not_create_account(self):
        self.assertEqual(
            self.client.post(
                "/registrer", data={"email": "board@example.org"}
            ).status_code,
            400,
        )
        self.start()
        self.verify()
        self.assertEqual(self.finish("wrong").status_code, 400)
        with module.get_db() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM board_users").fetchone()[0], 1
            )

    def test_signup_rate_limited(self):
        for _ in range(3):
            self.assertEqual(self.start().status_code, 302)
        self.assertEqual(self.start().status_code, 429)

    def test_unconfigured_email_and_smtp_failure(self):
        with patch("styre_registrering.mail_ready", return_value=False):
            self.assertEqual(self.client.get("/registrer").status_code, 503)
        self.send.side_effect = RuntimeError("do not log this")
        with self.assertLogs(module.app.logger, level="ERROR") as logs:
            self.assertEqual(self.start().status_code, 302)
        self.assertNotIn("do not log this", str(logs.output))
        with module.get_db() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM board_enrollment").fetchone()[0], 0
            )

    def test_public_membership_cannot_grant_board(self):
        response = self.client.post(
            "/api/innmelding", json={"membership_type": "styret"}
        )
        self.assertEqual(response.status_code, 410)
        self.assertEqual(module._medlemstype_visning("styret"), "Styret")
