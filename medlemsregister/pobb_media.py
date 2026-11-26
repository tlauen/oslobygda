"""Galleriutkast med private opplastingar og eksplisitt GitHub-publisering."""

import base64
import hashlib
import io
import json
import unicodedata
from pathlib import PurePosixPath
from urllib.parse import quote

from database import managed_db
from flask import abort, current_app, render_template, request, send_file
from markupsafe import Markup
from nettsidetekst import BLOCK_MARKERS, MEMBERSHIP_MARKER, ROOT, digest
from nettsidetekst import FILE as TEXT_FILE
from publisering import GithubDocuments, PublicationConflict, PublicationError

FILE = "_data/pobb_bilete.yml"
SETTING = "pub_gallery_draft"
ASSET_PREFIX = "website_media_asset_"
MAX_FILE = 10 * 1024 * 1024


def validate_path(value, poster=False):
    if not isinstance(value, str) or not value or len(value) > 300:
        raise ValueError("Ugyldig mediefil.")
    path = PurePosixPath(value)
    allowed = {".jpg", ".jpeg", ".png", ".webp"} | (set() if poster else {".mp4"})
    if (
        path.is_absolute()
        or any(part in (".", "..") for part in value.split("/"))
        or any(c in value for c in '\\<>"?#%')
        or any(ord(c) < 32 for c in value)
        or path.suffix.lower() not in allowed
    ):
        raise ValueError("Ugyldig filnamn eller filtype.")
    return value


def validate_gallery(items):
    if not isinstance(items, list) or len(items) > 100:
        raise ValueError("Galleriet kan ha høgst 100 innslag.")
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) - {
            "fil",
            "tekst",
            "fotograf",
            "plakat",
        }:
            raise ValueError("Ukjent galleriinnhald.")
        path = validate_path(item.get("fil"))
        if path in seen:
            raise ValueError("Same mediefil er vald fleire gonger.")
        seen.add(path)
        for name in ("tekst", "fotograf"):
            value = item.get(name, "")
            if (
                not isinstance(value, str)
                or len(value) > 500
                or any(ord(c) < 32 for c in value)
            ):
                raise ValueError(
                    "Bilettekst og kreditering må vere på éi linje, høgst 500 teikn."
                )
        if not item.get("tekst", "").strip():
            raise ValueError("Skriv ein bilettekst som òg skildrar innhaldet.")
        if item.get("plakat"):
            validate_path(item["plakat"], poster=True)
    return items


def read_setting(db, key):
    row = db.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else None


def write_setting(db, key, value):
    db.execute(
        "INSERT INTO app_settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value, ensure_ascii=False)),
    )


def uploaded_asset(upload, poster=False):
    limit = 3 * 1024 * 1024 if poster else MAX_FILE
    data = upload.read(limit + 1)
    if len(data) > limit:
        raise ValueError(
            "Bilete/film må vere høgst 10 MiB, og framsidebilete høgst 3 MiB. Komprimer store filmar før opplasting."
        )
    if data.startswith(b"\xff\xd8\xff"):
        ext, mime = ".jpg", "image/jpeg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        ext, mime = ".png", "image/png"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        ext, mime = ".webp", "image/webp"
    elif (
        not poster
        and len(data) >= 16
        and data[4:8] == b"ftyp"
        and data[8:12]
        in (b"isom", b"iso2", b"mp41", b"mp42", b"avc1", b"M4V ", b"qt  ")
    ):
        ext, mime = ".mp4", "video/mp4"
    else:
        raise ValueError(
            "Bruk JPEG, PNG, WebP eller MP4. Framsidebiletet til ein film må vere eit bilete."
        )
    key = hashlib.sha256(data).hexdigest()
    return {
        "fil": "opplasta/" + key + ext,
        "mime": mime,
        "data": base64.b64encode(data).decode(),
    }


def asset_key(path):
    if not path.startswith("opplasta/"):
        return None
    stem = PurePosixPath(path).stem
    if len(stem) != 64 or any(c not in "0123456789abcdef" for c in stem):
        return None
    return ASSET_PREFIX + stem


class GithubGallery(GithubDocuments):
    # Object responses keep the blob SHA available for videos larger than 1 MB.
    # https://docs.github.com/en/rest/repos/contents#get-repository-content
    accept = "application/vnd.github.object+json"

    def read_gallery(self):
        result = self.api("GET", FILE)
        if result is None:
            raise PublicationError("Gallerifila manglar i GitHub.")
        try:
            items = validate_gallery(
                json.loads(base64.b64decode(result["content"]).decode())
            )
            return items, result["sha"]
        except (ValueError, KeyError, TypeError):
            raise PublicationError(
                "Gallerifila kunne ikkje lesast. Ingen endringar er publiserte."
            ) from None

    def publish_gallery(self, state, assets):
        items = validate_gallery(state["items"])
        remote, sha = self.read_gallery()
        if remote == items:
            return
        if digest(remote) != state["base"]:
            raise PublicationConflict(
                "Galleriet er endra i GitHub. Ta vare på endringane og hent publisert galleri før du prøver igjen."
            )
        # Immutable files are sent first. The public gallery changes only with the final manifest.
        for asset in assets:
            content = base64.b64decode(asset["data"])
            path = "lutar/bilete/pobb/" + validate_path(asset["fil"])
            expected = hashlib.sha1(
                b"blob " + str(len(content)).encode() + b"\0" + content
            ).hexdigest()
            old = self.api("GET", path)
            if old:
                if old.get("sha") != expected:
                    raise PublicationConflict(
                        "Ei opplasta fil har uventa innhald i GitHub."
                    )
                continue
            self.api(
                "PUT",
                path,
                {
                    "message": "Last opp galleriinnslag frå Bygdelista",
                    "branch": self.branch,
                    "content": asset["data"],
                },
            )
        # Other editors may have changed the gallery while the files were uploading.
        remote, sha = self.read_gallery()
        if remote == items:
            return
        if digest(remote) != state["base"]:
            raise PublicationConflict(
                "Galleriet vart endra under opplastinga. Utkastet er bevart."
            )
        self.api(
            "PUT",
            FILE,
            {
                "message": "Oppdater Folkemusikkpøbben sitt galleri frå Bygdelista",
                "branch": self.branch,
                "sha": sha,
                "content": base64.b64encode(
                    (json.dumps(items, ensure_ascii=False, indent=2) + "\n").encode()
                ).decode(),
            },
        )


def public_media_url(path):
    # Git stores NFC names. Percent-encoding NFD names produced 404s for å/ø/æ.
    return "https://oslobygda.no/lutar/bilete/pobb/" + quote(
        unicodedata.normalize("NFC", path), safe="/"
    )


def install_gallery(app, get_db, require_admin):
    # Same filter name as Jekyll for the shared gallery template. Preview URLs
    # are already encoded, so preserve percent escapes and normalise raw Unicode.
    app.jinja_env.filters["uri_escape"] = lambda value: quote(
        unicodedata.normalize("NFC", str(value)), safe="/:%?=&"
    )

    @app.get("/nettsida/pobb/media/<name>")
    @require_admin
    def pub_media_asset(name):
        key = asset_key("opplasta/" + name)
        if not key:
            abort(404)
        with managed_db(get_db) as db:
            asset = read_setting(db, key)
        if not asset or asset["fil"] != "opplasta/" + name:
            abort(404)
        response = send_file(
            io.BytesIO(base64.b64decode(asset["data"])),
            mimetype=asset["mime"],
            download_name=name,
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def media_url(path, local):
        if path in local:
            return current_app.jinja_env.globals["prefix_url"](
                "pub_media_asset", name=PurePosixPath(path).name
            )
        return public_media_url(path)

    @app.get("/nettsida/pobb/forehandsvis")
    @require_admin
    def pub_gallery_preview():
        with managed_db(get_db) as db:
            saved = read_setting(db, SETTING)
            text = read_setting(db, "website_text_draft_pub")
            items = saved["items"] if saved else json.loads((ROOT / FILE).read_text())
            local = {
                path
                for item in items
                for path in (item["fil"], item.get("plakat", ""))
                if asset_key(path) and read_setting(db, asset_key(path))
            }
        page = (
            text["page"] if text else json.loads((ROOT / TEXT_FILE).read_text())["pub"]
        )
        view = [
            {
                **item,
                "fil": media_url(item["fil"], local),
                "plakat": media_url(item["plakat"], local)
                if item.get("plakat")
                else "",
            }
            for item in items
        ]
        photos = [item for item in view if not item["fil"].endswith(".mp4")]
        videos = [item for item in view if item["fil"].endswith(".mp4")]
        rows = max(len(photos), len(videos)) + 1
        widget = Markup(
            '<span data-kontingent-url="'
            + current_app.jinja_env.globals["prefix_url"]("public_membership_rates")
            + '" data-kontingent-vising="belop">sjå gjeldande sats i innmeldingsskjemaet</span>'
        )
        body = Markup(
            render_template(
                "_markdown_preview.html",
                html=page["html"]["gallery_body"],
                membership_widget=widget,
                membership_marker=MEMBERSHIP_MARKER,
                block_markers=BLOCK_MARKERS,
            )
        )
        response = app.make_response(
            render_template(
                "pobb_media_preview.html",
                gallery_title=page["source"]["gallery_title"],
                gallery_subtitle=page["source"]["gallery_subtitle"],
                gallery_body=body,
                gallery_photos=photos,
                gallery_videos=videos,
                gallery_rows=rows,
                gallery_rows_wide=rows // 2 + 1,
                media_base="",
            )
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
        return response

    @app.route("/nettsida/pobb/galleri", methods=["GET", "POST"])
    @require_admin
    def pub_gallery_editor():
        import os

        with managed_db(get_db) as db:
            saved = read_setting(db, SETTING)
        published = validate_gallery(json.loads((ROOT / FILE).read_text()))
        ready = bool(os.environ.get("GITHUB_DOCUMENTS_TOKEN", "").strip())
        error = message = None
        status = 200
        if ready and saved is None:
            try:
                published = GithubGallery().read_gallery()[0]
            except PublicationError as exc:
                error = str(exc)
                status = 503
        state = saved or {"items": published, "base": digest(published)}
        revision = digest(saved)
        preview_mode = False
        editing = request.values.get("edit", "")
        values = next(
            (dict(item) for item in state["items"] if item["fil"] == editing), {}
        )
        if request.method == "POST":
            values = request.form.to_dict()
            try:
                if error:
                    raise PublicationError(error)
                if values.get("revision") != revision:
                    raise PublicationConflict(
                        "Utkastet er endra. Last sida på nytt før du endrar meir."
                    )
                if saved is None and values.get("source_revision") != state["base"]:
                    raise PublicationConflict(
                        "Publisert galleri er endra. Last sida på nytt."
                    )
                action = values.get("action")
                items = [dict(item) for item in state["items"]]
                assets = []
                if action == "save":
                    old = next((item for item in items if item["fil"] == editing), None)
                    if editing and old is None:
                        raise PublicationConflict(
                            "Innslaget finst ikkje lenger i utkastet."
                        )
                    item = dict(old or {})
                    item.update(
                        tekst=values.get("tekst", "").strip(),
                        fotograf=values.get("fotograf", "").strip(),
                    )
                    for field, target, poster in [
                        ("media", "fil", False),
                        ("poster", "plakat", True),
                    ]:
                        upload = request.files.get(field)
                        if upload and upload.filename:
                            asset = uploaded_asset(upload, poster=poster)
                            assets.append(asset)
                            item[target] = asset["fil"]
                    if not item.get("fil"):
                        raise ValueError("Vel eit bilete eller ein film.")
                    if not item["fil"].endswith(".mp4"):
                        item.pop("plakat", None)
                    if old:
                        items.remove(old)
                    try:
                        position = int(values.get("position", len(items) + 1))
                    except ValueError:
                        raise ValueError("Vel eit heilt tal for plassering.") from None
                    if not 1 <= position <= len(items) + 1:
                        raise ValueError("Plasseringa er utanfor galleriet.")
                    items.insert(position - 1, item)
                elif action == "remove":
                    if not editing or not any(item["fil"] == editing for item in items):
                        raise ValueError("Vel eit eksisterande innslag.")
                    items = [item for item in items if item["fil"] != editing]
                elif action == "reload":
                    if values.get("confirmed") != "yes":
                        raise ValueError("Stadfest at utkastet kan bytast ut.")
                    items = GithubGallery().read_gallery()[0] if ready else published
                elif action == "preview":
                    preview_mode = True
                elif action == "publish":
                    if not saved or values.get("confirmed") != "yes":
                        raise ValueError(
                            "Lagre, kontroller og stadfest utkastet først."
                        )
                    with managed_db(get_db) as db:
                        for item in items:
                            for path in (item["fil"], item.get("plakat", "")):
                                key = asset_key(path)
                                asset = read_setting(db, key) if key else None
                                if asset:
                                    assets.append(asset)
                    GithubGallery().publish_gallery(state, assets)
                    updated = {"items": items, "base": digest(items)}
                    with managed_db(get_db) as db:
                        db.execute("BEGIN IMMEDIATE")
                        if digest(read_setting(db, SETTING)) == revision:
                            write_setting(db, SETTING, updated)
                    state = updated
                    revision = digest(updated)
                    message = "Galleriet er lagra i GitHub. Kontroller nettsida når bygginga er ferdig."
                else:
                    raise ValueError("Vel ei gyldig handling.")
                if action in ("save", "remove", "reload", "preview"):
                    validate_gallery(items)
                    next_state = {
                        "items": items,
                        "base": digest(items) if action == "reload" else state["base"],
                    }
                    with managed_db(get_db) as db:
                        db.execute("BEGIN IMMEDIATE")
                        if digest(read_setting(db, SETTING)) != revision:
                            raise PublicationConflict(
                                "Utkastet vart endra samtidig. Prøv igjen frå siste versjon."
                            )
                        for asset in assets:
                            write_setting(db, asset_key(asset["fil"]), asset)
                        write_setting(db, SETTING, next_state)
                    state = next_state
                    revision = digest(state)
                    editing = ""
                    values = {}
                    preview_mode = True
                    message = "Galleriutkastet er lagra. Nettsida er ikkje endra."
            except (ValueError, PublicationError) as exc:
                error = str(exc)
                status = (
                    409
                    if isinstance(exc, PublicationConflict)
                    else (503 if isinstance(exc, PublicationError) else 400)
                )
        with managed_db(get_db) as db:
            local = {
                item["fil"]
                for item in state["items"]
                if asset_key(item["fil"]) and read_setting(db, asset_key(item["fil"]))
            }
            local.update(
                item["plakat"]
                for item in state["items"]
                if item.get("plakat")
                and asset_key(item["plakat"])
                and read_setting(db, asset_key(item["plakat"]))
            )
        response = app.make_response(
            (
                render_template(
                    "pobb_media.html",
                    items=state["items"],
                    values=values,
                    editing=editing,
                    revision=revision,
                    source_revision=state["base"],
                    local=local,
                    preview_mode=preview_mode,
                    ready=ready,
                    error=error,
                    message=message,
                    max_file=MAX_FILE,
                    media_url=lambda path: media_url(path, local),
                    position=next(
                        (
                            i + 1
                            for i, item in enumerate(state["items"])
                            if item["fil"] == editing
                        ),
                        len(state["items"]) + 1,
                    ),
                ),
                status,
            )
        )
        response.headers["Cache-Control"] = "no-store"
        return response
