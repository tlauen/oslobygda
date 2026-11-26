"""Køarbeidaren sender kodar utan at offentlege HTTP-svar ventar på SMTP."""

import unittest
from unittest.mock import Mock, patch
from database import managed_db
import app as module
import test_mi_side as portal
import test_ny_innmelding as signup


class AuthMailTests(unittest.TestCase):
    setUp = portal.PortalTests.setUp
    tearDown = portal.PortalTests.tearDown
    add_member = portal.PortalTests.add_member
    token = portal.PortalTests.token
    fields = signup.SignupTests.fields

    def test_member_http_never_calls_smtp_and_worker_sends_once(self):
        self.assertEqual(
            self.client.post(
                "/mi-side/logg-inn",
                data={"email": "first@example.org", "csrf_token": self.token()},
            ).status_code,
            303,
        )
        self.mail.assert_not_called()
        with managed_db(module.get_db) as db:
            row = db.execute("SELECT * FROM auth_mail_jobs").fetchone()
            self.assertNotIn("first@example.org", row["payload"])
        worker = module.app.extensions["auth_mail"]

        def sending(*args):
            self.assertEqual(worker.process(), 0)  # A parallel worker cannot claim it.

        self.mail.side_effect = sending
        self.assertEqual(worker.process(), 1)
        self.assertEqual(worker.process(), 0)
        self.mail.assert_called_once()

    def test_expired_or_revoked_member_jobs_are_not_sent(self):
        auth = module.app.extensions["member_auth"]
        auth.start("first@example.org", "192.0.2.1")
        with managed_db(module.get_db) as db:
            db.execute("UPDATE member_access SET version='revoked'")
        self.assertEqual(module.app.extensions["auth_mail"].process(), 0)
        self.mail.assert_not_called()
        with managed_db(module.get_db) as db:
            db.execute("DELETE FROM login_limits")
        auth.start("first@example.org", "192.0.2.1")
        with managed_db(module.get_db) as db:
            db.execute("UPDATE auth_mail_jobs SET expires=0")
        self.assertEqual(module.app.extensions["auth_mail"].process(), 0)
        self.mail.assert_not_called()

    def test_signup_known_and_unknown_addresses_have_same_public_flow(self):
        locations = []
        worker = module.app.extensions["auth_mail"]
        for email in ("first@example.org", "new@example.org"):
            client = module.app.test_client()
            with patch(
                "ny_innmelding.credentials", return_value={"VIPPS_MSN": "123456"}
            ):
                response = client.post(
                    "/bli-medlem",
                    data={**self.fields(email=email), "csrf_token": self.token(client)},
                )
            self.assertEqual(response.status_code, 303)
            locations.append(response.location)
            self.mail.assert_not_called()
            page = client.get(response.location)
            self.assertIn("Stadfest e-postadressa".encode(), page.data)
            with patch("ny_innmelding.client_for") as provider:
                response = client.post(
                    "/bli-medlem/status",
                    data={"action": "pay", "csrf_token": self.token(client)},
                )
                self.assertEqual(response.status_code, 400)
                provider.assert_not_called()
        self.assertEqual(locations[0], locations[1])
        self.assertEqual(worker.process(), 2)
        self.assertEqual(self.mail.call_count, 2)

    def test_signup_code_browser_binding_attempts_and_address_change(self):
        with patch("ny_innmelding.credentials", return_value={"VIPPS_MSN": "123456"}):
            self.client.post(
                "/bli-medlem",
                data={
                    **self.fields(email="new@example.org"),
                    "csrf_token": self.token(),
                },
            )
        module.app.extensions["auth_mail"].process()
        code = self.mail.call_args.args[1]
        other = module.app.test_client()
        self.assertEqual(
            other.post(
                "/bli-medlem/status",
                data={
                    "action": "verify",
                    "code": code,
                    "csrf_token": self.token(other),
                },
            ).status_code,
            404,
        )
        response = self.client.post(
            "/bli-medlem/status",
            data={"action": "verify", "code": code, "csrf_token": self.token()},
        )
        self.assertEqual(response.status_code, 303)
        with patch("ny_innmelding.client_for") as provider:
            provider.return_value.create.return_value = {
                "redirectUrl": "https://api.vipps.no/payment"
            }
            self.assertEqual(
                self.client.post(
                    "/bli-medlem/status",
                    data={"action": "pay", "csrf_token": self.token()},
                ).status_code,
                303,
            )
            provider.return_value.create.assert_called_once()

    def test_invalid_codes_are_limited_and_do_not_unlock_payment(self):
        with patch("ny_innmelding.credentials", return_value={"VIPPS_MSN": "123456"}):
            self.client.post(
                "/bli-medlem",
                data={
                    **self.fields(email="new@example.org"),
                    "csrf_token": self.token(),
                },
            )
        module.app.extensions["auth_mail"].process()
        code = self.mail.call_args.args[1]
        for _ in range(5):
            self.assertEqual(
                self.client.post(
                    "/bli-medlem/status",
                    data={
                        "action": "verify",
                        "code": "wrong",
                        "csrf_token": self.token(),
                    },
                ).status_code,
                400,
            )
        self.assertEqual(
            self.client.post(
                "/bli-medlem/status",
                data={"action": "verify", "code": code, "csrf_token": self.token()},
            ).status_code,
            400,
        )

    def test_worker_cli_initializes_and_processes_queue(self):
        module.app.extensions["member_auth"].start("first@example.org", "192.0.2.1")
        result = module.app.test_cli_runner().invoke(args=["auth-epost"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.mail.assert_called_once()
        with managed_db(module.get_db) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM auth_mail_jobs").fetchone()[0], 0
            )

    def test_index_supplies_escaped_prefix_and_external_script(self):
        from test_styre_auth import BoardAuthTests

        self.assertEqual(BoardAuthTests.login(self).status_code, 302)
        with (
            patch.object(module, "URL_PREFIX", "/test-prefix"),
            patch.dict(module.app.jinja_env.globals, {"url_prefix": "/test-prefix"}),
        ):
            response = self.client.get("/")
        self.assertIn(b'<meta name="api-prefix" content="/test-prefix">', response.data)
        self.assertIn(b"/test-prefix/fast/medlemsliste.js", response.data)

    def test_correct_email_after_back_or_edit_sends_new_code(self):
        service = module.app.extensions["signup_service"]
        worker = module.app.extensions["auth_mail"]
        for path in ("/bli-medlem", "/bli-medlem/rediger"):
            with self.subTest(path=path):
                client = module.app.test_client()
                with (
                    patch(
                        "ny_innmelding.credentials",
                        return_value={"VIPPS_MSN": "123456"},
                    ),
                    patch(
                        "signup_stadfesting.secrets.randbelow", return_value=11111111
                    ),
                ):
                    client.post(
                        "/bli-medlem",
                        data={
                            **self.fields(email="typo@example.org"),
                            "csrf_token": self.token(client),
                        },
                    )
                with client.session_transaction() as state:
                    reference = state["signup_reference"]
                worker.process()
                old_code = self.mail.call_args.args[1]
                self.assertEqual(
                    client.post(
                        "/bli-medlem/status",
                        data={
                            "action": "verify",
                            "code": old_code,
                            "csrf_token": self.token(client),
                        },
                    ).status_code,
                    303,
                )
                self.mail.reset_mock()
                if path == "/bli-medlem":
                    response = client.get(path)
                    self.assertEqual(response.status_code, 303)
                    self.assertTrue(response.location.endswith("/bli-medlem/rediger"))
                    self.assertIn(
                        b"typo@example.org", client.get(response.location).data
                    )
                with (
                    patch(
                        "ny_innmelding.credentials",
                        return_value={"VIPPS_MSN": "123456"},
                    ),
                    patch(
                        "signup_stadfesting.secrets.randbelow", return_value=22222222
                    ),
                ):
                    response = client.post(
                        path,
                        data={
                            **self.fields(email="corrected@example.org"),
                            "csrf_token": self.token(client),
                        },
                    )
                self.assertEqual(response.status_code, 303)
                self.assertEqual(
                    service.order(reference)["email"], "corrected@example.org"
                )
                page = client.get("/bli-medlem/status")
                self.assertIn(b"corrected@example.org", page.data)
                self.assertNotIn(b"typo@example.org", page.data)
                worker.process()
                self.mail.assert_called_once()
                self.assertEqual(self.mail.call_args.args[0], "corrected@example.org")
                code = self.mail.call_args.args[1]
                self.assertEqual(
                    client.post(
                        "/bli-medlem/status",
                        data={
                            "action": "verify",
                            "code": old_code,
                            "csrf_token": self.token(client),
                        },
                    ).status_code,
                    400,
                )
                self.assertEqual(
                    client.post(
                        "/bli-medlem/status",
                        data={
                            "action": "verify",
                            "code": code,
                            "csrf_token": self.token(client),
                        },
                    ).status_code,
                    303,
                )

    def test_resubmitting_initial_form_cannot_edit_started_payment(self):
        service = module.app.extensions["signup_service"]
        with patch("ny_innmelding.credentials", return_value={"VIPPS_MSN": "123456"}):
            self.client.post(
                "/bli-medlem",
                data={
                    **self.fields(email="original@example.org"),
                    "csrf_token": self.token(),
                },
            )
            with self.client.session_transaction() as state:
                reference = state["signup_reference"]
            with managed_db(module.get_db) as db:
                db.execute(
                    "UPDATE signup_orders SET create_attempted=1 WHERE reference=?",
                    (reference,),
                )
            response = self.client.post(
                "/bli-medlem",
                data={
                    **self.fields(email="changed@example.org", amount="200"),
                    "csrf_token": self.token(),
                },
            )
        self.assertEqual(response.status_code, 303)
        order = service.order(reference)
        self.assertEqual(order["email"], "original@example.org")
        self.assertEqual(order["amount_ore"], 10000)
        self.assertEqual(
            self.client.post(
                "/bli-medlem/rediger",
                data={**self.fields(), "csrf_token": self.token()},
            ).status_code,
            409,
        )
