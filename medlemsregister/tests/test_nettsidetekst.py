import base64
import copy
import json
import os
import unittest
from unittest.mock import patch

import app as module
import test_styre_auth as fixtures
from database import managed_db
from nettsidetekst import FILE, ROOT, GithubTexts, digest, make_page, markdown_html
from publisering import PublicationConflict


class WebsiteTextTests(unittest.TestCase):
    setUp = fixtures.BoardAuthTests.setUp
    tearDown = fixtures.BoardAuthTests.tearDown
    token = fixtures.BoardAuthTests.token

    def page(self):
        return json.loads((ROOT / FILE).read_text())["framside"]

    def form(self, action="save", page=None, revision=None):
        page = page or self.page()
        if revision is None:
            with managed_db(module.get_db) as db:
                row = db.execute(
                    "SELECT value FROM app_settings WHERE key='website_text_draft_framside'"
                ).fetchone()
            revision = digest(json.loads(row["value"]) if row else None)
        return dict(
            page["source"],
            csrf_token=self.token(),
            source_revision=digest(self.page()),
            revision=revision,
            action=action,
        )

    @patch.dict(os.environ, {"GITHUB_DOCUMENTS_TOKEN": ""})
    def test_access_csrf_draft_preview_and_conflict(self):
        path = "/nettsida/tekst"
        self.assertEqual(self.client.get(path).status_code, 302)
        fixtures.BoardAuthTests.login(self)
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn(">Nettsida</a>", response.text)
        self.assertEqual(
            self.client.post(path, data={"action": "save"}).status_code, 400
        )
        data = self.form()
        data["intro"] = "**Ny tekst** med [lenkje](/om/)."
        old_revision = data["revision"]
        with patch.object(GithubTexts, "api", side_effect=AssertionError("No network")):
            response = self.client.post(path, data=data)
            self.assertEqual(response.status_code, 200)
            self.assertIn("<strong>Ny tekst</strong>", response.text)
            self.assertIn("Utkastet er lagra", response.text)
            self.assertEqual(
                self.client.post(
                    path, data=dict(data, revision=old_revision)
                ).status_code,
                409,
            )
            preview = self.form("preview")
            preview["intro"] = "*Berre førehandsvising*"
            self.assertIn(
                "<em>Berre førehandsvising</em>",
                self.client.post(path, data=preview).text,
            )
            self.assertIn("**Ny tekst**", self.client.get(path).text)
        self.assertEqual(self.client.get("/nettsida/tekst/ukjend").status_code, 404)

    @patch.dict(os.environ, {"GITHUB_DOCUMENTS_TOKEN": ""})
    def test_publication_requires_saved_unchanged_draft_and_confirmation(self):
        fixtures.BoardAuthTests.login(self)
        self.assertEqual(
            self.client.post("/nettsida/tekst", data=self.form("publish")).status_code,
            400,
        )
        self.client.post("/nettsida/tekst", data=self.form())
        with (
            patch.object(GithubTexts, "__init__", return_value=None),
            patch.object(GithubTexts, "publish_page") as publish,
        ):
            data = self.form("publish")
            self.assertEqual(
                self.client.post("/nettsida/tekst", data=data).status_code, 400
            )
            data["confirmed"] = "yes"
            data["title"] = "Ulagra endring"
            self.assertEqual(
                self.client.post("/nettsida/tekst", data=data).status_code, 400
            )
            publish.assert_not_called()
            data = self.form("publish")
            data["confirmed"] = "yes"
            self.assertEqual(
                self.client.post("/nettsida/tekst", data=data).status_code, 200
            )
            publish.assert_called_once()

    def test_safe_markdown_and_literal_template_code(self):
        html = markdown_html(
            "**Feit** og *kursiv*\n\n- Ein\n- To\n\n<script>alert(1)</script> [farleg](javascript:alert(1)) {{ site.secret }} {% include x %}"
        )
        self.assertIn("<strong>Feit</strong>", html)
        self.assertIn("<ul>", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn('href="javascript:', html)
        self.assertIn("{{ site.secret }}", html)
        self.assertNotIn("<img", markdown_html("![bilete](https://example.invalid/x)"))

    def test_github_conflicts_merge_other_page_and_idempotent_retry(self):
        data = json.loads((ROOT / FILE).read_text())
        original = copy.deepcopy(data)
        page = make_page(
            "framside", dict(data["framside"]["source"], intro="Ny **tekst**.")
        )
        client = object.__new__(GithubTexts)
        client.branch = "main"
        data["om"] = make_page(
            "om", dict(data["om"]["source"], title="Endra av ein annan")
        )
        with (
            patch.object(client, "read_texts", return_value=(data, "new-sha")),
            patch.object(client, "api") as api,
        ):
            client.publish_page("framside", page, digest(original["framside"]))
            body = api.call_args.args[2]
            written = json.loads(base64.b64decode(body["content"]))
            self.assertEqual(written["om"], data["om"])
            self.assertEqual(written["framside"], page)
            self.assertEqual(body["sha"], "new-sha")
        with (
            patch.object(client, "read_texts", return_value=(written, "sha")),
            patch.object(client, "api") as api,
        ):
            client.publish_page("framside", page, digest(original["framside"]))
            api.assert_not_called()
            with self.assertRaises(PublicationConflict):
                client.publish_page(
                    "framside", original["framside"], digest(original["framside"])
                )

    @patch.dict(os.environ, {"GITHUB_DOCUMENTS_TOKEN": ""})
    def test_editing_and_publication_are_separate_simple_steps(self):
        fixtures.BoardAuthTests.login(self)
        response = self.client.get("/nettsida/tekst")
        self.assertIn('name="tekstseksjon" open', response.text)
        self.assertIn("Fleire tekstval</summary>", response.text)
        self.assertEqual(response.text.count('value="save"'), 1)
        self.assertNotIn('value="preview"', response.text)
        self.assertNotIn('value="publish"', response.text)
        self.assertNotIn('type="checkbox"', response.text)
        response = self.client.post("/nettsida/tekst", data=self.form())
        self.assertIn("Tekstførehandsvising", response.text)
        self.assertNotIn("<textarea", response.text)
        self.assertNotIn('value="save"', response.text)
        self.assertNotIn('value="reload"', response.text)
        # A configured publisher reveals only the publication action at this step.
        with patch.dict(os.environ, {"GITHUB_DOCUMENTS_TOKEN": "test-only"}):
            response = self.client.post("/nettsida/tekst", data=self.form())
            self.assertIn(
                'name="confirmed" value="yes">Publiser på nettsida', response.text
            )
