"""Utkast og kontrollert publisering av offentleg sidetekst, aldri Jekyll-kode."""

import base64
import hashlib
import json
import os
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from database import managed_db
from flask import abort, render_template, request
from publisering import GithubDocuments, PublicationConflict, PublicationError

FILE = "_data/sidetekstar.json"
ROOT = Path(__file__).resolve().parent.parent
FIELDS = {
    "framside": [
        ("description", "Søkemotortekst", False),
        ("overtekst", "Overtekst", False),
        ("title", "Hovudoverskrift", False),
        ("intro", "Ingress", True),
        ("events_button", "Knapp til arrangement", False),
        ("join_button", "Lenkje til innmelding", False),
        ("events_overline", "Overtekst over kalenderen", False),
        ("events_title", "Overskrift over kalenderen", False),
        ("calendar_button", "Lenkje til kalenderen", False),
        ("member_overline", "Overtekst om medlemskap", False),
        ("member_title", "Overskrift om medlemskap", False),
        ("member_body", "Tekst om medlemskap", True),
        ("member_button", "Innmeldingsknapp", False),
        ("about_button", "Lenkje til Om-sida", False),
        ("badge_text", "Tekst under kontingentsatsen", False),
    ],
    "om": [
        ("title", "Sidetittel", False),
        ("description", "Søkemotortekst", False),
        ("body", "Om laget", True),
        ("join_text", "Tekst før innmeldingslenkja", False),
        ("join_button", "Innmeldingslenkje", False),
    ],
}
LABELS = {"framside": "Framsida", "om": "Om-sida"}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class SafeHTML(HTMLParser):
    """Lita tillatingsliste etter Markdown-konvertering. Ingen rå HTML eller bilete."""

    tags = frozenset(
        {
            "p",
            "br",
            "strong",
            "em",
            "a",
            "ul",
            "ol",
            "li",
            "blockquote",
            "h2",
            "h3",
            "h4",
            "pre",
            "code",
            "hr",
        }
    )

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.tags:
            return
        attr = ""
        if tag == "a":
            url = dict(attrs).get("href", "")
            parsed = urlsplit(url)
            if (
                not any(c.isspace() or ord(c) < 32 for c in url)
                and "\\" not in url
                and (
                    (
                        parsed.scheme in ("https", "mailto")
                        and not parsed.username
                        and not parsed.password
                    )
                    or (url.startswith(("/", "#")) and not url.startswith("//"))
                )
            ):
                attr = ' href="' + escape(url, quote=True) + '"'
        self.output.append("<" + tag + attr + ">")

    def handle_endtag(self, tag):
        if tag in self.tags and tag not in ("br", "hr"):
            self.output.append("</" + tag + ">")

    def handle_data(self, data):
        self.output.append(escape(data))


def markdown_html(source):
    import markdown

    parser = SafeHTML()
    # Escape HTML before parsing. User text is data, never a Liquid template.
    parser.feed(
        markdown.markdown(escape(source, quote=False), extensions=["sane_lists"])
    )
    return "".join(parser.output)


def make_page(key, values):
    if key not in FIELDS:
        raise ValueError("Ukjend side.")
    source = {}
    rendered = {}
    for name, label, is_markdown in FIELDS[key]:
        value = values.get(name, "")
        maximum = 12000 if is_markdown else 500
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > maximum
            or any(ord(c) < 32 and c not in "\n\r\t" for c in value)
        ):
            raise ValueError(f"Fyll ut «{label}» med høgst {maximum} teikn.")
        if not is_markdown and ("\n" in value or "\r" in value):
            raise ValueError(f"«{label}» skal vere éi linje.")
        source[name] = value.strip()
        if is_markdown:
            rendered[name] = markdown_html(source[name])
    return {"source": source, "html": rendered}


def validate_envelope(value):
    if not isinstance(value, dict) or set(value) != set(FIELDS):
        raise PublicationError("Sidetekstfila har ukjent format.")
    for key in FIELDS:
        try:
            if make_page(key, value[key]["source"]) != value[key]:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise PublicationError("Sidetekstfila har ugyldig innhald.") from None
    return value


class GithubTexts(GithubDocuments):
    # Same explicitly configured repository, branch and transport as annual documents.
    def read_texts(self):
        result = self.api("GET", FILE)
        if result is None:
            raise PublicationError(
                "Sidetekstfila manglar i GitHub. Oppdater nettsiderepoet først."
            )
        try:
            data = json.loads(base64.b64decode(result["content"]).decode())
        except (KeyError, TypeError, ValueError):
            raise PublicationError("Kunne ikkje lese sidetekstfila.") from None
        return validate_envelope(data), result["sha"]

    def publish_page(self, key, page, base):
        data, sha = self.read_texts()
        if data[key] == page:
            return
        if digest(data[key]) != base:
            raise PublicationConflict(
                "Sida er endra i GitHub. Ta vare på teksten din og hent publisert tekst før du prøver igjen."
            )
        data[key] = page
        self.api(
            "PUT",
            FILE,
            {
                "message": f"Oppdater {LABELS[key]} frå Bygdelista",
                "branch": self.branch,
                "sha": sha,
                "content": base64.b64encode(
                    (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
                ).decode(),
            },
        )


def install_text_editor(app, get_db, require_admin):
    @app.route("/nettsida/tekst", defaults={"key": "framside"}, methods=["GET", "POST"])
    @app.route("/nettsida/tekst/<key>", methods=["GET", "POST"])
    @require_admin
    def website_text_editor(key):
        if key not in FIELDS:
            abort(404)
        setting = "website_text_draft_" + key
        with managed_db(get_db) as db:
            row = db.execute(
                "SELECT value FROM app_settings WHERE key=?", (setting,)
            ).fetchone()
        draft = json.loads(row["value"]) if row else None
        published = json.loads((ROOT / FILE).read_text())[key]
        ready = bool(os.environ.get("GITHUB_DOCUMENTS_TOKEN", "").strip())
        error = message = None
        status = 200
        # With publication configured, use the current remote text as the starting point.
        if ready and not draft:
            try:
                published = GithubTexts().read_texts()[0][key]
            except PublicationError as exc:
                error = str(exc)
                status = 503
        state = draft or {"page": published, "base": digest(published)}
        revision = digest(draft)
        values = state["page"]["source"]
        preview = state["page"]
        if request.method == "POST":
            values = request.form.to_dict()
            try:
                if error:
                    raise PublicationError(error)
                action = values.get("action")
                if action not in ("preview", "save", "publish", "reload"):
                    raise ValueError("Vel ei gyldig handling.")
                if not draft and values.get("source_revision") != state["base"]:
                    raise PublicationConflict(
                        "Publisert tekst er endra. Kopier teksten din før du lastar sida på nytt."
                    )
                if values.get("revision") != revision:
                    raise PublicationConflict(
                        "Utkastet er endra av ein annan. Kopier teksten din før du opnar siste utkast."
                    )
                if action == "reload":
                    if values.get("confirmed") != "yes":
                        raise ValueError(
                            "Stadfest at utkastet kan bytast ut med publisert tekst."
                        )
                    page = GithubTexts().read_texts()[0][key] if ready else published
                    next_state = {"page": page, "base": digest(page)}
                else:
                    page = make_page(key, values)
                    preview = page
                    next_state = {"page": page, "base": state["base"]}
                if action in ("save", "reload"):
                    with managed_db(get_db) as db:
                        db.execute("BEGIN IMMEDIATE")
                        current = db.execute(
                            "SELECT value FROM app_settings WHERE key=?", (setting,)
                        ).fetchone()
                        if (
                            digest(json.loads(current["value"]) if current else None)
                            != revision
                        ):
                            raise PublicationConflict(
                                "Utkastet vart endra samtidig. Kopier teksten din før du lastar på nytt."
                            )
                        db.execute(
                            "INSERT INTO app_settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                            (setting, json.dumps(next_state, ensure_ascii=False)),
                        )
                    state = next_state
                    revision = digest(state)
                    values = page["source"]
                    preview = page
                    message = (
                        "Utkastet er lagra. Nettsida er ikkje endra."
                        if action == "save"
                        else "Publisert tekst er henta inn som nytt utkast."
                    )
                elif action == "publish":
                    if not draft or page != draft["page"]:
                        raise ValueError(
                            "Lagre og førehandsvis utkastet før publisering."
                        )
                    if values.get("confirmed") != "yes":
                        raise ValueError(
                            "Stadfest at teksten er kontrollert og kan publiserast."
                        )
                    GithubTexts().publish_page(key, page, state["base"])
                    # Preserve a newer draft if somebody saved while GitHub was responding.
                    updated = {"page": page, "base": digest(page)}
                    with managed_db(get_db) as db:
                        db.execute(
                            "UPDATE app_settings SET value=? WHERE key=? AND value=?",
                            (
                                json.dumps(updated, ensure_ascii=False),
                                setting,
                                row["value"],
                            ),
                        )
                    state = updated
                    revision = digest(updated)
                    values = page["source"]
                    message = "Teksten er lagra i GitHub. Kontroller nettsida når bygginga er ferdig."
            except (ValueError, PublicationError) as exc:
                error = str(exc)
                status = (
                    409
                    if isinstance(exc, PublicationConflict)
                    else (503 if isinstance(exc, PublicationError) else 400)
                )
        response = app.make_response(
            (
                render_template(
                    "nettsidetekst.html",
                    key=key,
                    title=LABELS[key],
                    fields=FIELDS[key],
                    values=values,
                    preview=preview,
                    revision=revision,
                    source_revision=state["base"],
                    ready=ready,
                    error=error,
                    message=message,
                ),
                status,
            )
        )
        response.headers["Cache-Control"] = "no-store"
        return response
