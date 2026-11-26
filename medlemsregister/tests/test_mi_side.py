import json
import os
import time
from datetime import date
import unittest
from unittest.mock import Mock, patch

import app as module
from database import managed_db
from medlem_auth import TTL, SESSION_TTL, revoke_access
from medlem_nyhendebrev import choose, process
import test_styre_auth as fixtures


class PortalTests(unittest.TestCase):
    token = fixtures.BoardAuthTests.token
    admin_login = fixtures.BoardAuthTests.login

    def setUp(self):
        fixtures.BoardAuthTests.setUp(self)
        self.mail_patch = patch("medlem_auth.send_code")
        self.mail = self.mail_patch.start()
        self.env_patch = patch.dict(
            os.environ,
            {
                "SMTP_HOST": "fake",
                "SMTP_USER": "fake",
                "SMTP_PASSWORD": "fake",
                "BREVO_API_KEY": "",
                "VIPPS_SIGNUP_MODE": "production",
            },
        )
        self.env_patch.start()
        self.mid = self.add_member("first@example.org", "Fyrste Medlem")
        self.other = self.add_member("second@example.org", "Andre Medlem")

    def tearDown(self):
        self.env_patch.stop()
        self.mail_patch.stop()
        fixtures.BoardAuthTests.tearDown(self)

    def add_member(self, email, name):
        first, last = name.split(" ", 1)
        with managed_db(module.get_db) as db:
            return db.execute(
                """INSERT INTO members(full_name,fornamn,mellomnamn,etternamn,email,phone,adresse,postnummer,poststad,birth_date,membership_type,payment_status,consent_at,created_at,updated_at)
                VALUES (?,?,'',?,?,'99999999','Testvegen 1','0001','Oslo','1990-01-01','vanleg','ikkje betalt','2026-01-01','2026-01-01','2026-01-01')""",
                (name, first, last, email),
            ).lastrowid

    @property
    def auth(self):
        return module.app.extensions["member_auth"]

    def start(self, email="first@example.org", client=None):
        client = client or self.client
        response = client.post(
            "/mi-side/logg-inn", data={"email": email, "csrf_token": self.token(client)}
        )
        module.app.extensions["auth_mail"].process()
        return response

    def finish(self, code=None, client=None):
        client = client or self.client
        return client.post(
            "/mi-side/kode",
            data={
                "code": code or self.mail.call_args.args[1],
                "csrf_token": self.token(client),
            },
        )

    def login(self, client=None, email="first@example.org"):
        client = client or self.client
        self.assertEqual(self.start(email, client).status_code, 303)
        self.assertEqual(self.finish(client=client).status_code, 303)

    def profile(self, **changes):
        return dict(
            action="profile",
            fornamn="Fyrste",
            mellomnamn="",
            etternamn="Medlem",
            phone="88888888",
            adresse="Nyvegen 2",
            postnummer="0002",
            poststad="Oslo",
            birth_date="1991-02-03",
            **changes,
        )

    def post(self, url, data, client=None):
        client = client or self.client
        return client.post(url, data={**data, "csrf_token": self.token(client)})

    def test_login_generic_unknown_and_browser_bound_codes(self):
        self.assertEqual(self.client.get("/mi-side").status_code, 302)
        unknown = self.start("unknown@example.org")
        self.mail.assert_not_called()
        known = self.start()
        self.assertEqual(known.location, unknown.location)
        self.assertNotIn(
            "Fyrste", self.client.get("/mi-side/kode").get_data(as_text=True)
        )
        code = self.mail.call_args.args[1]
        other = module.app.test_client()
        self.assertEqual(self.finish(code, other).status_code, 400)
        with managed_db(module.get_db) as db:
            stored = db.execute("SELECT code_hash FROM member_challenges").fetchone()[0]
            self.assertEqual(len(stored), 64)
            self.assertNotEqual(stored, code)
        self.assertEqual(self.finish(code).status_code, 303)
        self.assertEqual(self.finish(code).status_code, 400)
        self.assertIn(
            "first@example.org", self.client.get("/mi-side").get_data(as_text=True)
        )

    def test_five_attempts_expiry_and_rate_limit(self):
        self.start()
        correct = self.mail.call_args.args[1]
        wrong = "00000000" if correct != "00000000" else "11111111"
        for _ in range(5):
            self.assertEqual(self.finish(wrong).status_code, 400)
        self.assertEqual(self.finish(correct).status_code, 400)
        self.start()
        with patch("medlem_auth.time.time", return_value=time.time() + TTL + 1):
            self.assertEqual(self.finish().status_code, 400)
        self.assertEqual(self.start().status_code, 303)
        self.assertEqual(self.start().status_code, 400)

    def test_explicit_session_expiry_and_logout(self):
        self.login()
        with self.client.session_transaction() as s:
            s["member_logged_at"] = time.time() - SESSION_TTL - 1
        self.assertEqual(self.client.get("/mi-side").status_code, 302)
        self.login()
        self.assertEqual(self.client.post("/mi-side/logg-ut").status_code, 400)
        self.assertEqual(self.post("/mi-side/logg-ut", {}).status_code, 303)
        self.assertEqual(self.client.get("/mi-side").status_code, 302)

    def test_profile_and_export_only_own_data_and_no_admin_escalation(self):
        self.login()
        self.assertEqual(
            self.client.post("/mi-side", data=self.profile()).status_code, 400
        )
        response = self.post(
            "/mi-side",
            self.profile(
                id=self.other,
                member_id=self.other,
                membership_type="styret",
                payment_status="betalt",
                email="attacker@example.org",
            ),
        )
        self.assertEqual(response.status_code, 303)
        with managed_db(module.get_db) as db:
            first = dict(
                db.execute("SELECT * FROM members WHERE id=?", (self.mid,)).fetchone()
            )
            other = dict(
                db.execute("SELECT * FROM members WHERE id=?", (self.other,)).fetchone()
            )
        self.assertEqual(first["email"], "first@example.org")
        self.assertEqual(first["membership_type"], "vanleg")
        self.assertEqual(first["payment_status"], "ikkje betalt")
        self.assertEqual(first["phone"], "88888888")
        self.assertEqual(other["phone"], "99999999")
        for url in [
            "/api/members",
            f"/api/members/{self.other}",
            "/api/export/excel",
            f"/api/gdpr/export/{self.other}",
        ]:
            self.assertEqual(
                self.client.get(
                    url, headers={"Accept": "application/json"}
                ).status_code,
                401,
            )
        export = self.client.get("/mi-side/last-ned")
        self.assertEqual(export.get_json()["email"], "first@example.org")
        self.assertNotIn("version", export.get_json())
        self.assertNotIn("second@example.org", export.get_data(as_text=True))
        self.assertEqual(export.headers["Cache-Control"], "no-store")

    def test_member_login_does_not_carry_board_session(self):
        self.admin_login()
        self.assertEqual(self.client.get("/api/members").status_code, 200)
        self.login()
        self.assertEqual(
            self.client.get(
                "/api/members", headers={"Accept": "application/json"}
            ).status_code,
            401,
        )

    def test_admin_email_change_and_deletion_revoke_member_sessions(self):
        self.login()
        with managed_db(module.get_db) as db:
            revoke_access(db, self.mid)
        self.assertEqual(self.client.get("/mi-side").status_code, 302)
        self.login()
        admin = module.app.test_client()
        fixtures.BoardAuthTests.login(self, client=admin)
        response = admin.put(
            f"/api/members/{self.mid}",
            json={"email": "updated@example.org"},
            headers={"X-CSRF-Token": self.token(admin)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/mi-side").status_code, 302)
        self.login(email="updated@example.org")
        from personvern import erase_member

        with managed_db(module.get_db) as db:
            self.assertEqual(erase_member(db, self.mid)[1], 200)
        self.assertEqual(self.client.get("/mi-side").status_code, 302)
        with managed_db(module.get_db) as db:
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM member_access WHERE member_id=?", (self.mid,)
                ).fetchone()[0],
                0,
            )

    def test_email_change_needs_both_codes_and_revokes_other_sessions(self):
        self.login()
        other = module.app.test_client()
        self.login(other)
        self.mail.reset_mock()
        self.assertEqual(
            self.post("/mi-side/epost", {"email": "new@example.org"}).status_code, 303
        )
        self.assertEqual(
            [call.args[0] for call in self.mail.call_args_list],
            ["first@example.org", "new@example.org"],
        )
        old_code, new_code = [call.args[1] for call in self.mail.call_args_list]
        response = self.post(
            "/mi-side/epost/stadfest", {"old_code": "wrong", "new_code": new_code}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.post(
                "/mi-side/epost/stadfest", {"old_code": old_code, "new_code": new_code}
            ).status_code,
            303,
        )
        with managed_db(module.get_db) as db:
            self.assertEqual(
                db.execute(
                    "SELECT email FROM members WHERE id=?", (self.mid,)
                ).fetchone()[0],
                "new@example.org",
            )
            self.assertEqual(
                db.execute(
                    "SELECT email,desired FROM member_newsletter_jobs WHERE member_id=?",
                    (self.mid,),
                ).fetchone()[:],
                ("first@example.org", 0),
            )
        self.assertEqual(other.get("/mi-side").status_code, 302)
        self.assertEqual(
            self.post(
                "/mi-side/epost/stadfest", {"old_code": old_code, "new_code": new_code}
            ).status_code,
            400,
        )

    def test_email_change_cannot_take_another_members_address_or_change_board_identity(
        self,
    ):
        self.login()
        self.assertEqual(
            self.post("/mi-side/epost", {"email": "second@example.org"}).status_code,
            400,
        )
        self.mail.assert_called_once()  # Berre innlogginga.
        with managed_db(module.get_db) as db:
            db.execute("UPDATE board_users SET member_id=?", (self.mid,))
        self.assertEqual(
            self.post("/mi-side/epost", {"email": "new@example.org"}).status_code, 400
        )

    def test_payment_opening_and_no_duplicate_paid_or_free_renewal(self):
        self.login()
        with patch("kontingent.today", return_value=date(2027, 1, 1)):
            self.assertNotIn(
                "Betal medlemspengar</button>",
                self.client.get("/mi-side").get_data(as_text=True),
            )
            self.assertEqual(
                self.post("/mi-side/betal", {"amount": "5", "terms": "1"}).status_code,
                400,
            )
        with (
            patch("kontingent.today", return_value=date(2026, 11, 25)),
            patch("ny_innmelding.credentials", return_value={"VIPPS_MSN": "123456"}),
        ):
            self.assertIn(
                "Betal medlemspengar</button>",
                self.client.get("/mi-side").get_data(as_text=True),
            )
            self.assertEqual(
                self.post(
                    "/mi-side/betal",
                    {
                        "amount": "5",
                        "terms": "1",
                        "member_id": self.other,
                        "year": "2030",
                    },
                ).status_code,
                303,
            )
            with self.client.session_transaction() as s:
                ref = s["signup_reference"]
            self.assertEqual(self.client.get("/bli-medlem/status").status_code, 200)
            self.assertEqual(
                self.post("/mi-side/betal", {"amount": "10", "terms": "1"}).status_code,
                303,
            )
            with managed_db(module.get_db) as db:
                self.assertEqual(
                    db.execute(
                        "SELECT count(*) FROM signup_orders WHERE renewal_member_id=?",
                        (self.mid,),
                    ).fetchone()[0],
                    1,
                )
                row = db.execute(
                    "SELECT * FROM signup_orders WHERE reference=?", (ref,)
                ).fetchone()
                self.assertEqual(
                    (row["renewal_member_id"], row["for_year"], row["amount_ore"]),
                    (self.mid, 2026, 1000),
                )
                db.execute(
                    "INSERT INTO free_membership_years VALUES (?,2026,'now')",
                    (self.mid,),
                )
            self.assertEqual(
                self.post("/mi-side/betal", {"amount": "5", "terms": "1"}).status_code,
                400,
            )
            with patch("ny_innmelding.client_for") as client:
                with self.assertRaises(Exception):
                    module.app.extensions["signup_service"].create(
                        ref, "https://example.org/status"
                    )
                client.assert_not_called()

    def test_member_payment_access_expires_with_member_login(self):
        self.login()
        with patch("ny_innmelding.credentials", return_value={"VIPPS_MSN": "123456"}):
            self.post("/mi-side/betal", {"amount": "5", "terms": "1"})
        with self.client.session_transaction() as s:
            s["member_logged_at"] = time.time() - SESSION_TTL - 1
        self.assertEqual(self.client.get("/bli-medlem/status").status_code, 404)

    def test_newsletter_choices_are_durable_and_only_explicit_optin_unblocks(self):
        self.login()
        self.post("/mi-side", {"action": "newsletter", "newsletter": "no"})
        api = Mock(return_value=(204, {}))
        with patch.dict(os.environ, {"BREVO_API_KEY": "fake", "BREVO_LIST_ID": "3"}):
            self.assertEqual(process(module.get_db, api), 1)
            self.assertEqual(api.call_args.args[0], "PUT")
            self.assertEqual(api.call_args.args[3], {"unlinkListIds": [3]})
            self.post("/mi-side", {"action": "newsletter", "newsletter": "yes"})
            self.assertEqual(process(module.get_db, api), 1)
            self.assertFalse(api.call_args.args[3]["emailBlacklisted"])
            self.post("/mi-side", self.profile())
            self.assertEqual(process(module.get_db, api), 1)
            self.assertEqual(api.call_args.args[0], "PUT")
            self.assertNotIn("emailBlacklisted", api.call_args.args[3])
            self.assertEqual(api.call_args.args[3]["attributes"]["FIRSTNAME"], "Fyrste")

    def test_newsletter_failure_and_newer_choice_survive_inflight_api(self):
        self.login()
        self.post("/mi-side", {"action": "newsletter", "newsletter": "yes"})
        with patch.dict(os.environ, {"BREVO_API_KEY": "fake", "BREVO_LIST_ID": "3"}):
            self.assertEqual(process(module.get_db, Mock(return_value=(503, {}))), 0)

            def choose_new(*args):
                with managed_db(module.get_db) as db:
                    member = dict(
                        db.execute(
                            "SELECT * FROM members WHERE id=?", (self.mid,)
                        ).fetchone()
                    )
                    choose(db, member, False)
                return 204, {}

            self.assertEqual(process(module.get_db, choose_new), 0)
            api = Mock(return_value=(204, {}))
            self.assertEqual(process(module.get_db, api), 1)
            self.assertEqual(api.call_args.args[3], {"unlinkListIds": [3]})

    def test_duplicate_email_and_smtp_failure_do_not_disclose_membership(self):
        self.add_member("first@example.org", "Delt Adresse")
        self.assertEqual(self.start().status_code, 303)
        self.mail.assert_not_called()
        self.mail.side_effect = RuntimeError("private provider response")
        with self.assertLogs(module.app.logger, level="WARNING") as logs:
            self.assertEqual(self.start("second@example.org").status_code, 303)
        self.assertNotIn("second@example.org", str(logs.output))
        self.assertNotIn("private provider response", str(logs.output))
        with managed_db(module.get_db) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM member_challenges").fetchone()[0], 0
            )

    def test_email_change_rechecks_conflict_and_expiry(self):
        self.login()
        self.post("/mi-side/epost", {"email": "new@example.org"})
        old_code, new_code = [call.args[1] for call in self.mail.call_args_list[-2:]]
        with managed_db(module.get_db) as db:
            db.execute(
                "UPDATE members SET email=? WHERE id=?", ("new@example.org", self.other)
            )
        self.assertEqual(
            self.post(
                "/mi-side/epost/stadfest", {"old_code": old_code, "new_code": new_code}
            ).status_code,
            400,
        )
        with managed_db(module.get_db) as db:
            db.execute(
                "UPDATE members SET email=? WHERE id=?",
                ("second@example.org", self.other),
            )
            db.execute("UPDATE member_challenges SET expires=0 WHERE purpose='email'")
        self.assertEqual(
            self.post(
                "/mi-side/epost/stadfest", {"old_code": old_code, "new_code": new_code}
            ).status_code,
            400,
        )
        with managed_db(module.get_db) as db:
            self.assertEqual(
                db.execute(
                    "SELECT email FROM members WHERE id=?", (self.mid,)
                ).fetchone()[0],
                "first@example.org",
            )

    def test_profile_changes_refresh_an_unstarted_order_and_payment_blocks_email_change(
        self,
    ):
        self.login()
        with patch("ny_innmelding.credentials", return_value={"VIPPS_MSN": "123456"}):
            self.post("/mi-side/betal", {"amount": "5", "terms": "1"})
            self.post("/mi-side", self.profile())
            self.post("/mi-side/betal", {"amount": "5", "terms": "1"})
        with managed_db(module.get_db) as db:
            row = db.execute("SELECT * FROM signup_orders").fetchone()
            self.assertEqual(json.loads(row["details"])["phone"], "88888888")
            db.execute("UPDATE signup_orders SET create_attempted=1")
        self.assertEqual(
            self.post("/mi-side/epost", {"email": "new@example.org"}).status_code, 400
        )

    def test_old_signup_call_cannot_override_a_newer_unsubscribe(self):
        self.login()
        with patch("ny_innmelding.credentials", return_value={"VIPPS_MSN": "123456"}):
            ref = module.app.extensions["signup_service"].new(
                {
                    "fornamn": "Third",
                    "etternamn": "Member",
                    "email": "third@example.org",
                    "phone": "99999999",
                    "adresse": "Test 1",
                    "postnummer": "0001",
                    "poststad": "Oslo",
                    "amount": "5",
                    "terms": "1",
                    "newsletter": "1",
                },
                "third-browser",
                "production",
                "127.0.0.1",
            )
        # Kopla ei eldre, ferdig signup-køoppføring til denne medlemmen.
        with managed_db(module.get_db) as db:
            db.execute(
                "UPDATE signup_orders SET member_id=?,status='complete',newsletter=1,newsletter_done=0 WHERE reference=?",
                (self.mid, ref),
            )

        def old_api(member):
            self.post("/mi-side", {"action": "newsletter", "newsletter": "no"})
            with patch.dict(
                os.environ, {"BREVO_API_KEY": "fake", "BREVO_LIST_ID": "3"}
            ):
                process(module.get_db, Mock(return_value=(204, {})))
            raise OSError("unknown delivery")

        service = module.app.extensions["signup_service"]
        with patch.object(service, "newsletter", side_effect=old_api):
            with self.assertRaises(OSError):
                service.sync_newsletter(ref)
        with managed_db(module.get_db) as db:
            self.assertEqual(
                db.execute("SELECT desired FROM member_newsletter_jobs").fetchone()[0],
                0,
            )

    def test_deletion_during_newsletter_api_requeues_provider_erasure(self):
        self.login()
        self.post("/mi-side", {"action": "newsletter", "newsletter": "yes"})

        def provider(*args):
            from personvern import erase_member

            with managed_db(module.get_db) as db:
                erase_member(db, self.mid)
                db.execute(
                    "DELETE FROM privacy_jobs"
                )  # Ein annan arbeidar har alt sletta hos Brevo.
            return 204, {}

        with patch.dict(os.environ, {"BREVO_API_KEY": "fake", "BREVO_LIST_ID": "3"}):
            process(module.get_db, provider)
        with managed_db(module.get_db) as db:
            self.assertEqual(
                db.execute("SELECT email FROM privacy_jobs").fetchone()[0],
                "first@example.org",
            )

    def test_reminder_contains_no_personal_links_or_new_payment_capability(self):
        with patch("kontingent.send_message") as sender:
            self.assertEqual(
                module.app.extensions["renewals"].send(self.mid, 2026, "production"),
                "sent",
            )
        body = sender.call_args.args[0].get_content()
        self.assertIn("Mi side", body)
        self.assertNotIn("https://", body)
        self.assertNotIn("/forny/", body)
        with managed_db(module.get_db) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM renewal_links").fetchone()[0], 0
            )
            self.assertEqual(
                db.execute("SELECT mail_status FROM renewal_reminders").fetchone()[0],
                "sent",
            )
