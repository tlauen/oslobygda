from functools import wraps
import unittest
from unittest.mock import patch

from flask import Blueprint, Flask

from csrf import csrf_exempt, install_csrf


class CSRFTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "isolated-test-secret"
        install_csrf(self.app)

    def test_unmarked_old_endpoint_names_do_not_bypass_protection(self):
        for name in ("api_innmelding", "signup_webhook", "minutes_auto_publish"):
            self.app.add_url_rule(
                "/" + name, endpoint=name, view_func=lambda: "changed", methods=["POST"]
            )
        client = self.app.test_client()
        for name in ("api_innmelding", "signup_webhook", "minutes_auto_publish"):
            with self.subTest(endpoint=name):
                self.assertEqual(client.post("/" + name).status_code, 400)

    def test_exemption_survives_endpoint_rename_blueprint_and_wrapping(self):
        def wrapper(view):
            @wraps(view)
            def decorated():
                return view()

            return decorated

        blueprint = Blueprint("renamed", __name__)

        @blueprint.post("/signed", endpoint="new_endpoint_name")
        @wrapper
        @csrf_exempt
        def original_name():
            return "signed handler"

        self.app.register_blueprint(blueprint)
        self.assertEqual(self.app.test_client().post("/signed").status_code, 200)

    def test_normal_changes_require_browser_bound_token_in_form_or_header(self):
        self.app.add_url_rule(
            "/change",
            view_func=lambda: "changed",
            methods=["POST", "PUT", "PATCH", "DELETE"],
        )
        client = self.app.test_client()
        other = self.app.test_client()
        with client.session_transaction() as state:
            state["csrf_token"] = "first-browser-token"
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                self.assertEqual(client.open("/change", method=method).status_code, 400)
                self.assertEqual(
                    client.open(
                        "/change", method=method, headers={"X-CSRF-Token": "wrong"}
                    ).status_code,
                    400,
                )
                self.assertEqual(
                    client.open(
                        "/change",
                        method=method,
                        headers={"X-CSRF-Token": "first-browser-token"},
                    ).status_code,
                    200,
                )
        self.assertEqual(
            client.post(
                "/change", data={"csrf_token": "first-browser-token"}
            ).status_code,
            200,
        )
        self.assertEqual(
            other.post(
                "/change", data={"csrf_token": "first-browser-token"}
            ).status_code,
            400,
        )

    def test_safe_methods_do_not_need_token(self):
        self.app.add_url_rule(
            "/read", view_func=lambda: "read", methods=["GET", "HEAD", "OPTIONS"]
        )
        for method in ("GET", "HEAD", "OPTIONS"):
            self.assertEqual(
                self.app.test_client().open("/read", method=method).status_code, 200
            )


class ExternalRouteTests(unittest.TestCase):
    def test_machine_routes_still_require_their_own_authentication(self):
        import app as module

        client = module.app.test_client()
        with patch(
            "ny_innmelding.credentials",
            return_value={"VIPPS_WEBHOOK_SECRET": "fake-test-secret"},
        ):
            self.assertEqual(
                client.post("/vipps/webhook/production", json={}).status_code, 401
            )
        with patch.dict("os.environ", BYGDELISTA_PUBLICATION_TOKEN=""):
            self.assertEqual(client.post("/api/protokoll/publiser").status_code, 403)
        self.assertEqual(client.post("/api/innmelding", json={}).status_code, 410)
