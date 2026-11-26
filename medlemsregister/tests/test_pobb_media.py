import base64
import copy
import io
import json
import os
import unittest
from unittest.mock import patch

import app as module
import test_styre_auth as fixtures
from database import managed_db
from nettsidetekst import BLOCK_MARKERS, ROOT, digest, markdown_html
from pobb_media import (
    FILE,
    SETTING,
    GithubGallery,
    asset_key,
    read_setting,
    uploaded_asset,
    validate_gallery,
)
from publisering import PublicationConflict


@patch.dict(os.environ, {"GITHUB_DOCUMENTS_TOKEN": ""})
class PubMediaTests(unittest.TestCase):
    setUp = fixtures.BoardAuthTests.setUp
    tearDown = fixtures.BoardAuthTests.tearDown
    token = fixtures.BoardAuthTests.token

    def state(self):
        with managed_db(module.get_db) as db:
            return read_setting(db, SETTING)

    def form(self, **values):
        saved = self.state()
        original = json.loads((ROOT / FILE).read_text())
        return dict(
            csrf_token=self.token(),
            revision=digest(saved),
            source_revision=digest(original),
            **values,
        )

    def test_fixed_markdown_blocks_and_text_editor(self):
        html = markdown_html(
            "# Hovudtekst\n\n[[kalenderknapp]]\n\n[[kalenderabonnement]]\n\n[[folg-oss]]\n\n`[[folg-oss]]`"
        )
        for marker in BLOCK_MARKERS.values():
            self.assertIn(marker, html)
        self.assertIn("<code>[[folg-oss]]</code>", html)
        self.assertIn("<h1>Hovudtekst</h1>", html)
        fixtures.BoardAuthTests.login(self)
        response = self.client.get("/nettsida/tekst/pub")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/nettsida/pobb/galleri", response.text)
        page = json.loads((ROOT / "_data/sidetekstar.json").read_text())["pub"]
        form = dict(
            page["source"],
            csrf_token=self.token(),
            revision=digest(None),
            source_revision=digest(page),
            action="save",
        )
        response = self.client.post("/nettsida/tekst/pub", data=form)
        self.assertEqual(response.status_code, 200)
        self.assertIn('href="https://oslobygda.no/kalender/"', response.text)
        self.assertIn("<details><summary>Få tilskipingane", response.text)

    def test_private_upload_replace_edit_and_remove(self):
        path = "/nettsida/pobb/galleri"
        self.assertEqual(self.client.get(path).status_code, 302)
        fixtures.BoardAuthTests.login(self)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(
            self.client.post(path, data={"action": "save"}).status_code, 400
        )
        form = self.form(
            action="save", tekst="Nytt bilete", fotograf="Fotograf", position="1"
        )
        form["media"] = (io.BytesIO(b"\xff\xd8\xffimage"), "bilete.jpg")
        with patch.object(
            GithubGallery, "api", side_effect=AssertionError("No network")
        ):
            response = self.client.post(path, data=form)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Nettsida er ikkje endra", response.text)
        state = self.state()
        first = state["items"][0]
        self.assertEqual(first["tekst"], "Nytt bilete")
        self.assertEqual(first["fotograf"], "Fotograf")
        self.assertIsNotNone(asset_key(first["fil"]))
        asset_url = "/nettsida/pobb/media/" + first["fil"].split("/")[-1]
        response = self.client.get(asset_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"\xff\xd8\xffimage")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        edit = self.form(
            action="save",
            edit=first["fil"],
            tekst="Endra tekst",
            fotograf="Ny kreditering",
            position="2",
        )
        self.assertEqual(self.client.post(path, data=edit).status_code, 200)
        self.assertEqual(self.state()["items"][1]["tekst"], "Endra tekst")
        self.assertEqual(self.client.post(path, data=edit).status_code, 409)
        remove = self.form(action="remove", edit=first["fil"])
        self.assertEqual(self.client.post(path, data=remove).status_code, 200)
        self.assertNotIn(first["fil"], [item["fil"] for item in self.state()["items"]])
        self.assertEqual(self.client.get(asset_url).status_code, 200)
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get(asset_url).status_code, 302)

    def test_reject_files_paths_and_bad_metadata(self):
        for data in (b'<svg onload="alert(1)">', b"<!doctype html>", b"bad"):
            with self.assertRaises(ValueError):
                uploaded_asset(io.BytesIO(data))
        video = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00"
        self.assertEqual(uploaded_asset(io.BytesIO(video))["mime"], "video/mp4")
        with self.assertRaises(ValueError):
            uploaded_asset(io.BytesIO(video), poster=True)
        for name in ("../x.jpg", "/x.jpg", "x.svg", "x%2f.jpg", "x.jpg?bad"):
            with self.assertRaises(ValueError):
                validate_gallery([{"fil": name, "tekst": "Bilete"}])
        with self.assertRaises(ValueError):
            validate_gallery([{"fil": "x.jpg", "tekst": ""}])

    def test_github_publishes_assets_before_manifest_and_retries(self):
        original = json.loads((ROOT / FILE).read_text())
        asset = uploaded_asset(io.BytesIO(b"\xff\xd8\xffimage"))
        items = [{"fil": asset["fil"], "tekst": "Nytt bilete"}] + copy.deepcopy(
            original
        )
        state = {"items": items, "base": digest(original)}
        client = object.__new__(GithubGallery)
        client.branch = "main"
        with (
            patch.object(
                client,
                "read_gallery",
                side_effect=[(original, "sha1"), (original, "sha2")],
            ),
            patch.object(client, "api", return_value=None) as api,
        ):
            client.publish_gallery(state, [asset])
            writes = [call.args for call in api.call_args_list if call.args[0] == "PUT"]
            self.assertEqual(len(writes), 2)
            self.assertTrue(writes[0][1].startswith("lutar/bilete/pobb/opplasta/"))
            self.assertEqual(writes[-1][1], FILE)
            self.assertEqual(writes[-1][2]["sha"], "sha2")
            self.assertEqual(
                json.loads(base64.b64decode(writes[-1][2]["content"])), items
            )
        with (
            patch.object(client, "read_gallery", return_value=(items, "sha")),
            patch.object(client, "api") as api,
        ):
            client.publish_gallery(state, [asset])
            api.assert_not_called()
        changed = copy.deepcopy(original)
        changed[0]["tekst"] = "Endra av ein annan"
        with (
            patch.object(client, "read_gallery", return_value=(changed, "sha")),
            patch.object(client, "api") as api,
        ):
            with self.assertRaises(PublicationConflict):
                client.publish_gallery(state, [asset])
            api.assert_not_called()

    def test_video_replacement_poster_and_publication_confirmation(self):
        fixtures.BoardAuthTests.login(self)
        original = json.loads((ROOT / FILE).read_text())
        edit = original[0]["fil"]
        form = self.form(
            action="save",
            edit=edit,
            tekst="Ny film",
            fotograf="Filmskapar",
            position="1",
        )
        form["media"] = (
            io.BytesIO(b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00"),
            "film.mp4",
        )
        form["poster"] = (io.BytesIO(b"\x89PNG\r\n\x1a\nposter"), "poster.png")
        response = self.client.post("/nettsida/pobb/galleri", data=form)
        self.assertEqual(response.status_code, 200)
        state = self.state()
        self.assertTrue(state["items"][0]["fil"].endswith(".mp4"))
        self.assertTrue(state["items"][0]["plakat"].endswith(".png"))
        self.assertNotIn(edit, [item["fil"] for item in state["items"]])
        with (
            patch.object(GithubGallery, "__init__", return_value=None),
            patch.object(GithubGallery, "publish_gallery") as publish,
        ):
            form = self.form(action="publish")
            self.assertEqual(
                self.client.post("/nettsida/pobb/galleri", data=form).status_code, 400
            )
            publish.assert_not_called()
            form["confirmed"] = "yes"
            response = self.client.post("/nettsida/pobb/galleri", data=form)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(publish.call_args.args[1]), 2)
        self.assertEqual(self.state()["base"], digest(state["items"]))

    def test_large_file_checks_use_github_object_responses(self):
        from unittest.mock import MagicMock, Mock

        with patch.dict(os.environ, {"GITHUB_DOCUMENTS_TOKEN": "test-token"}):
            client = GithubGallery()
        response = Mock()
        response.read.return_value = (
            b'{"sha":"blob-sha","content":"","encoding":"none"}'
        )
        client.opener = MagicMock()
        client.opener.open.return_value.__enter__.return_value = response
        result = client.api("GET", "lutar/bilete/pobb/opplasta/test.mp4")
        self.assertEqual(result["sha"], "blob-sha")
        self.assertEqual(
            client.opener.open.call_args.args[0].get_header("Accept"),
            "application/vnd.github.object+json",
        )
