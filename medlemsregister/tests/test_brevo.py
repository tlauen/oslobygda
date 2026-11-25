import io
import json
from logging import getLogger
import ssl
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from brevo import BrevoContacts, brevo_request


class BrevoTests(unittest.TestCase):
    def test_transport_keeps_https_validation_timeout_and_json(self):
        response = Mock(status=200)
        response.read.return_value = b'{"id":7}'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch("brevo.urlopen", return_value=response) as network:
            self.assertEqual(
                brevo_request("POST", "/contacts", "fake-key", {"name": "Prøve"}),
                (200, {"id": 7}),
            )
        request = network.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.brevo.com/v3/contacts")
        self.assertEqual(request.method, "POST")
        self.assertEqual(json.loads(request.data), {"name": "Prøve"})
        self.assertEqual(network.call_args.kwargs["timeout"], 20)
        context = network.call_args.kwargs["context"]
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        response.__exit__.assert_called_once()

    def test_transport_returns_failure_status_without_retrying(self):
        error = HTTPError(
            "https://api.brevo.com/v3/contacts",
            403,
            "Forbidden",
            {},
            io.BytesIO(b'{"message":"denied"}'),
        )
        with patch("brevo.urlopen", side_effect=error) as network:
            self.assertEqual(
                brevo_request("GET", "/contacts", "fake-key"),
                (403, {"message": "denied"}),
            )
            network.assert_called_once()
        error.close()
        with patch("brevo.urlopen", side_effect=URLError("unavailable")) as network:
            self.assertEqual(brevo_request("GET", "/contacts", "fake-key")[0], 0)
            network.assert_called_once()

    def test_contact_whitelist_and_missing_configuration(self):
        request = Mock(return_value=(201, {}))
        client = BrevoContacts(None, getLogger(__name__), request=request)
        member = dict(
            email="fiktiv@example.invalid",
            fornamn="Test",
            etternamn="Medlem",
            phone="99999999",
            birth_date="2000-01-01",
        )
        with patch.dict(
            "os.environ", BREVO_API_KEY="fake-key", BREVO_INNMELDING_LIST_ID="6"
        ):
            self.assertTrue(client.signup(member))
        payload = request.call_args.args[3]
        self.assertEqual(
            payload,
            {
                "email": "fiktiv@example.invalid",
                "attributes": {"FIRSTNAME": "Test", "LASTNAME": "Medlem"},
                "listIds": [6],
                "updateEnabled": True,
            },
        )
        request.reset_mock()
        with patch.dict("os.environ", BREVO_API_KEY=""):
            self.assertFalse(client.signup(member))
            self.assertFalse(client.delete_contact(member["email"]))
        request.assert_not_called()

    def test_delete_preserves_url_encoding_and_not_found_is_success(self):
        request = Mock(return_value=(404, {}))
        client = BrevoContacts(None, getLogger(__name__), request=request)
        with patch.dict("os.environ", BREVO_API_KEY="fake-key"):
            self.assertTrue(client.delete_contact("fiktiv+test@example.invalid"))
        request.assert_called_once_with(
            "DELETE", "/contacts/fiktiv%2Btest%40example.invalid", "fake-key"
        )
