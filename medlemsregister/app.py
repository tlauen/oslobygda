#!/usr/bin/env python3
"""
Bygdelista – GDPR-sikkert medlemsliste for Oslobygda.
Felter: namn, epost, telefon, adresse, postnummer, poststad, fødselsdato, medlemstype, betalingsstatus, samtykke.
Database kan krypterast med SQLCipher ved å setje MEDLEMSREGISTER_DB_KEY (da vert fila ikkje lesbar i BBEdit o.l.).
"""
import csv
import io
import json
import os
import smtplib
import sys
import ssl
import sqlite3
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.utils import formatdate
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = None

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    session,
    redirect,
    url_for,
    Response,
)
from werkzeug.security import check_password_hash, generate_password_hash

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "medlemsregister.db"

# Last .env frå medlemsregister-mappa (så du ikkje må køyre export manuelt)
try:
    from dotenv import load_dotenv
    load_dotenv(APP_DIR / ".env")
except ImportError:
    pass

# Kryptering: viss MEDLEMSREGISTER_DB_KEY er satt, bruk SQLCipher (fila vert ikkje lesbar som rein tekst)
DB_KEY = os.environ.get("MEDLEMSREGISTER_DB_KEY", "").strip()
_use_sqlcipher = False
if DB_KEY:
    try:
        import sqlcipher3.dbapi2 as _sqlcipher_sqlite
        _use_sqlcipher = True
    except ImportError:
        import warnings
        warnings.warn(
            "MEDLEMSREGISTER_DB_KEY er satt, men sqlcipher3 er ikkje installert. "
            "Kjør: pip install sqlcipher3 (krev også libsqlcipher, t.d. brew install sqlcipher). "
            "Databasen vert ikkje kryptert.",
            UserWarning,
        )

app = Flask(
    __name__,
    static_folder="fast",
    static_url_path="/fast",
    template_folder="malar",
)
app.secret_key = os.environ.get("MEDLEMSREGISTER_SECRET_KEY", "endre-meg-i-produksjon")

# Ved drift bak omvendt mellomtenar på oslobygda.no/medlemsregister/ – sett til "/medlemsregister"
URL_PREFIX = os.environ.get("MEDLEMSREGISTER_URL_PREFIX", "").rstrip("/")
if URL_PREFIX:
    app.config["APPLICATION_ROOT"] = URL_PREFIX

# Enkel passordvern – sett MEDLEMSREGISTER_PASSWORD_HASH i miljøet
ADMIN_PASSWORD_HASH = os.environ.get(
    "MEDLEMSREGISTER_PASSWORD_HASH",
    generate_password_hash("admin"),  # Berre for lokal utvikling – sett miljøvariabel i produksjon
)


def _pragma_key_sql() -> str:
    """PRAGMA key for SQLCipher (parameterisert støttes ikkje, så vi escapar apostrof i key)."""
    escaped = DB_KEY.replace("'", "''")
    return f"PRAGMA key = '{escaped}'"


def _is_plain_sqlite(path: Path) -> bool:
    """Sjekk om fila ser ut som ukyrptert SQLite (første 16 byte)."""
    if not path.exists() or path.stat().st_size < 16:
        return False
    with open(path, "rb") as f:
        return f.read(16).startswith(b"SQLite format 3\x00")


def _migrate_plain_to_encrypted() -> None:
    """Kopier ukyrptert DB til ny kryptert fil og erstatt. Køyr berre éin gong."""
    if not _use_sqlcipher or not DB_PATH.exists() or not _is_plain_sqlite(DB_PATH):
        return
    plain_conn = sqlite3.connect(DB_PATH)
    plain_conn.row_factory = sqlite3.Row
    rows = plain_conn.execute("SELECT * FROM members").fetchall()
    cols = [d[1] for d in plain_conn.execute("PRAGMA table_info(members)").fetchall()]
    has_payments = plain_conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='payments'"
    ).fetchone() is not None
    payment_rows = []
    payment_cols = []
    if has_payments:
        payment_rows = plain_conn.execute("SELECT * FROM payments").fetchall()
        payment_cols = [d[1] for d in plain_conn.execute("PRAGMA table_info(payments)").fetchall()]
    plain_conn.close()
    enc_path = APP_DIR / "medlemsregister.db.new"
    enc_conn = _sqlcipher_sqlite.connect(enc_path)
    enc_conn.execute(_pragma_key_sql())
    enc_conn.executescript("""
        CREATE TABLE members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            fornamn TEXT, mellomnamn TEXT, etternamn TEXT,
            email TEXT NOT NULL, phone TEXT, adresse TEXT, postnummer TEXT, poststad TEXT,
            birth_date TEXT, membership_type TEXT NOT NULL, payment_status TEXT NOT NULL,
            consent_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_members_email ON members(email);
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            amount_ore INTEGER NOT NULL,
            paid_at TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_payments_member_id ON payments(member_id);
    """)
    col_list = ", ".join(cols)
    placeholders = ", ".join("?" * len(cols))
    for row in rows:
        enc_conn.execute(f"INSERT INTO members ({col_list}) VALUES ({placeholders})", tuple(row))
    if has_payments and payment_cols:
        payment_col_list = ", ".join(payment_cols)
        payment_placeholders = ", ".join("?" * len(payment_cols))
        for row in payment_rows:
            enc_conn.execute(
                f"INSERT INTO payments ({payment_col_list}) VALUES ({payment_placeholders})",
                tuple(row),
            )
    enc_conn.commit()
    enc_conn.close()
    bak_path = APP_DIR / "medlemsregister.db.plain.bak"
    if bak_path.exists():
        bak_path.unlink()
    DB_PATH.rename(bak_path)
    enc_path.rename(DB_PATH)
    _restrict_db_permissions(DB_PATH)
    sys.stderr.write("Database migrert til kryptert. Den gamle ukyrpterte kopien ligg som medlemsregister.db.plain.bak\n")


def _restrict_db_permissions(path: Path) -> None:
    """Sett fil slik at berre eigar kan lese/skrive (chmod 600)."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def get_db():
    _migrate_plain_to_encrypted()
    if _use_sqlcipher:
        conn = _sqlcipher_sqlite.connect(DB_PATH)
        conn.execute(_pragma_key_sql())
        conn.row_factory = getattr(_sqlcipher_sqlite, "Row", sqlite3.Row)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
    if DB_PATH.exists():
        _restrict_db_permissions(DB_PATH)
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                fornamn TEXT,
                mellomnamn TEXT,
                etternamn TEXT,
                email TEXT NOT NULL,
                phone TEXT,
                adresse TEXT,
                postnummer TEXT,
                poststad TEXT,
                birth_date TEXT,
                membership_type TEXT NOT NULL,
                payment_status TEXT NOT NULL,
                consent_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_members_email ON members(email);
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER NOT NULL,
                amount_ore INTEGER NOT NULL,
                paid_at TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_payments_member_id ON payments(member_id);
        """)
        # Kan fjernast når alle instansar har køyrt migrering minst éin gong
        for col in ("adresse", "postnummer", "poststad", "fornamn", "mellomnamn", "etternamn", "birth_date"):
            try:
                conn.execute(f"ALTER TABLE members ADD COLUMN {col} TEXT")
            except Exception as e:
                if "duplicate column" not in str(e).lower():
                    raise
        # Migrer gamle rader: sett fornamn = full_name så brukar kan dele opp ved redigering
        conn.execute("UPDATE members SET fornamn = full_name WHERE fornamn IS NULL AND full_name IS NOT NULL")
        # Normaliser betalingsstatus til nynorsk
        conn.execute("UPDATE members SET payment_status = 'ikkje betalt' WHERE payment_status = 'ikke betalt'")
        conn.commit()


def require_admin(f):
    from functools import wraps
    @wraps(f)
    def inner(*args, **kwargs):
        if not session.get("admin_logged_in"):
            if request.accept_mimetypes.best == "application/json":
                return jsonify({"error": "Ikkje innlogga"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return inner


def prefix_url(endpoint, **values):
    """URL med eventuelt prefiks (for mellomtenar under /medlemsregister)."""
    url = url_for(endpoint, **values)
    if URL_PREFIX and url.startswith("/"):
        return URL_PREFIX + url
    return url


app.jinja_env.globals["prefix_url"] = prefix_url
app.jinja_env.globals["url_prefix"] = URL_PREFIX  # for fetch()-base i JS

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("innlogging.html")
    password = request.form.get("password", "")
    if check_password_hash(ADMIN_PASSWORD_HASH, password):
        session["admin_logged_in"] = True
        return redirect(prefix_url("index"))
    return render_template("innlogging.html", error="Feil passord"), 401


@app.route("/logout")
def logout():
    session.pop("admin_logged_in", None)
    return redirect(prefix_url("login"))


@app.route("/")
@require_admin
def index():
    return render_template("index.html")


# —— Offentleg innmeldingsskjema (ingen innlogging) ——

@app.route("/innmelding")
def innmelding_page():
    return render_template("innmelding.html")


def _send_innmelding_epost(to_email: str, fornamn: str, mellomnamn: str, etternamn: str, email: str, phone: str, adresse: str, postnummer: str, poststad: str, birth_date: str, membership_type: str) -> tuple[bool, str]:
    """Send innmeldings-epost til styret. Returnerer (success, feilmelding)."""
    full_name = _build_full_name(fornamn, mellomnamn, etternamn)
    body = f"""Ny innmelding via nettskjema – registrer i Bygdelista:

Fornamn:     {fornamn}
Mellomnamn:  {mellomnamn or '(tom)'}
Etternamn:   {etternamn}
Epost:       {email}
Telefon:     {phone or '(tom)'}
Adresse:     {adresse or '(tom)'}
Postnummer:  {postnummer or '(tom)'}
Poststad:    {poststad or '(tom)'}
Fødselsdato: {birth_date or '(tom)'}
Medlemstype: {_medlemstype_visning(membership_type, med_beskrivelse=True)}

——
Logg inn i Bygdelista og bruk «Legg til medlem» med opplysningane over.
"""
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"Ny innmelding: {full_name}"
    msg["From"] = os.environ.get("INNMELDING_EPOST_FRA", "noreply@oslobygda.no")
    msg["To"] = to_email
    msg["Date"] = formatdate(localtime=True)

    host = os.environ.get("SMTP_HOST", "").strip()
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    if not host or not user or not password:
        return False, "E-post ikkje konfigurert (manglar SMTP_HOST, SMTP_USER, SMTP_PASSWORD)"

    try:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls()
            s.login(user, password)
            s.send_message(msg)
        return True, ""
    except Exception as e:
        return False, str(e)


def _mailerlite_fetch_group_subscribers(token: str, group_id: str) -> tuple[list[dict], str]:
    """Hent alle abonnentar i ei gruppe (Connect API, cursor-paginering). Returnerer (liste med dict, feilmelding)."""
    out = []
    cursor = None
    url_base = f"https://connect.mailerlite.com/api/groups/{group_id}/subscribers"
    while True:
        url = f"{url_base}?limit=100" if cursor is None else f"{url_base}?limit=100&cursor={cursor}"
        req = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, method="GET")
        try:
            with urlopen(req, timeout=20, context=_SSL_CTX) as res:
                data = json.loads(res.read().decode())
        except (HTTPError, URLError, OSError, json.JSONDecodeError) as e:
            return [], str(e)
        for s in data.get("data") or []:
            out.append(s)
        cursor = (data.get("meta") or {}).get("next_cursor")
        if not cursor:
            break
    return out, ""


def _mailerlite_add_subscriber(email: str, fornamn: str, mellomnamn: str, etternamn: str, token: str, group_id: str) -> tuple[bool, str]:
    """Legg til eller oppdater abonnent i MailerLite. Returnerer (success, feilmelding)."""
    full_name = _build_full_name(fornamn, mellomnamn, etternamn)
    body = {
        "email": email,
        "fields": {
            "name": fornamn or full_name,
            "last_name": etternamn or "",
        },
        "groups": [group_id],
    }
    req = Request(
        "https://connect.mailerlite.com/api/subscribers",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=15, context=_SSL_CTX) as res:
            if res.status in (200, 201):
                return True, ""
            return False, f"MailerLite svarte med {res.status}"
    except HTTPError as e:
        try:
            err_body = json.loads(e.read().decode())
            msg = err_body.get("message", str(e))
        except Exception:
            msg = str(e)
        return False, msg
    except (URLError, OSError) as e:
        return False, str(e)


@app.route("/api/innmelding", methods=["POST"])
def api_innmelding():
    """Offentleg: send innmelding til folk@oslobygda.no (epost) og (valfritt) til MailerLite. Styret registrerer manuelt i Bygdelista."""
    data = request.get_json() or {}
    fornamn = (data.get("fornamn") or "").strip()
    mellomnamn = (data.get("mellomnamn") or "").strip()
    etternamn = (data.get("etternamn") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    adresse = (data.get("adresse") or "").strip()
    postnummer = (data.get("postnummer") or "").strip()
    poststad = (data.get("poststad") or "").strip()
    birth_date = (data.get("birth_date") or "").strip()  # ISO YYYY-MM-DD
    membership_type = (data.get("membership_type") or "vanleg").strip()
    consent = data.get("consent") is True

    if not consent:
        return jsonify({"error": "Du må godta at vi lagrar og brukar opplysningane for medlemskap og nyhendebrev."}), 400
    if not fornamn or not etternamn:
        return jsonify({"error": "Fornamn og etternamn er påkrevd."}), 400
    if not email:
        return jsonify({"error": "Epost er påkrevd."}), 400

    to_email = os.environ.get("INNMELDING_EPOST_TIL", "folk@oslobygda.no").strip()
    epost_ok, epost_err = _send_innmelding_epost(to_email, fornamn, mellomnamn, etternamn, email, phone, adresse, postnummer, poststad, birth_date, membership_type)

    mailerlite_ok = True
    mailerlite_err = ""
    token = os.environ.get("MAILERLITE_API_TOKEN", "").strip()
    group_id = (os.environ.get("MAILERLITE_INNMELDING_GROUP_ID") or os.environ.get("MAILERLITE_GROUP_ID", "")).strip()
    if token and group_id:
        mailerlite_ok, mailerlite_err = _mailerlite_add_subscriber(email, fornamn, mellomnamn, etternamn, token, group_id)

    if not epost_ok and not mailerlite_ok:
        return jsonify({"error": f"Kunne ikkje sende innmeldinga. E-post: {epost_err}. Nyhendebrev: {mailerlite_err}"}), 500
    if not epost_ok:
        return jsonify({"message": "Du er lagt til i nyhendebrev-lista.", "warning": f"E-post til styret kunne ikkje sendast: {epost_err}. Kontakt folk@oslobygda.no for å fullføre innmeldinga."}), 201
    if not mailerlite_ok:
        return jsonify({"message": "Innmeldinga er sendt til styret. Du vil bli registrert i Bygdelista snart.", "warning": f"Kunne ikkje legge til i nyhendebrev-lista: {mailerlite_err}"}), 201

    default_msg = "Takk for innmeldinga! Vi har sendt henne til styret (folk@oslobygda.no), og du er lagt til i nyhendebrev-lista. Styret registrerer deg i Bygdelista så snart dei ser henne."
    msg = os.environ.get("INNMELDING_SUCCESS_MESSAGE", default_msg).strip() or default_msg
    return jsonify({"message": msg}), 201


# —— API (berre for innlogga styret) ——

@app.route("/api/sync-mailerlite", methods=["POST"])
@require_admin
def api_sync_mailerlite():
    """Hent abonnentar frå MailerLite-gruppa «Medlemmar» (eller MAILERLITE_GROUP_ID) og legg til nye i Bygdelista."""
    token = os.environ.get("MAILERLITE_API_TOKEN", "").strip()
    group_id = (os.environ.get("MAILERLITE_MEDLEMMAR_GROUP_ID") or os.environ.get("MAILERLITE_GROUP_ID", "")).strip()
    if not token or not group_id:
        return jsonify({"error": "MAILERLITE_API_TOKEN og MAILERLITE_GROUP_ID (eller MAILERLITE_MEDLEMMAR_GROUP_ID) må vere satt."}), 400
    subscribers, err = _mailerlite_fetch_group_subscribers(token, group_id)
    if err:
        return jsonify({"error": f"Kunne ikkje hente frå MailerLite: {err}"}), 502
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    def _normalize_medlemstype(val):
        if not val:
            return "vanleg"
        v = (val or "").strip().lower()
        if "kul" in v or v == "k":
            return "kul"
        return "vanleg"

    with get_db() as conn:
        for s in subscribers:
            email = (s.get("email") or "").strip().lower()
            if not email:
                continue
            if conn.execute("SELECT 1 FROM members WHERE email = ?", (email,)).fetchone():
                continue
            fields = s.get("fields") or {}
            # Skjema-felt (Subscribers → Fields): fornamn, mellomnamn, etternamn, adresse, medlemstype, fodselsdato + name/last_name/city/zip/phone
            fornamn = (fields.get("fornamn") or fields.get("name") or "").strip() or "–"
            etternamn = (fields.get("etternamn") or fields.get("last_name") or "").strip() or "–"
            mellomnamn = (fields.get("mellomnamn") or fields.get("company") or "").strip()
            phone = (fields.get("phone") or "").strip()
            adresse = (fields.get("adresse") or fields.get("state") or "").strip()
            poststad = (fields.get("poststad") or fields.get("city") or "").strip()
            postnummer = (fields.get("postnummer") or fields.get("zip") or fields.get("z_i_p") or "").strip()
            membership_type = _normalize_medlemstype(fields.get("medlemstype") or fields.get("country"))
            birth_date = (fields.get("fodselsdato") or fields.get("birthday") or fields.get("birth_date") or "").strip() or None
            full_name = _build_full_name(fornamn, mellomnamn, etternamn)
            consent_at = s.get("subscribed_at") or now
            conn.execute(
                """INSERT INTO members (full_name, fornamn, mellomnamn, etternamn, email, phone, adresse, postnummer, poststad, birth_date, membership_type, payment_status, consent_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (full_name, fornamn, mellomnamn, etternamn, email, phone, adresse, postnummer, poststad, birth_date, membership_type, "ikkje betalt", consent_at, now, now),
            )
            added += 1
        conn.commit()
    return jsonify({"message": f"{added} nye medlemmar importert frå MailerLite." if added else "Ingen nye å hente frå MailerLite.", "added": added})


def _build_full_name(fornamn, mellomnamn, etternamn):
    return " ".join(filter(None, [fornamn, mellomnamn, etternamn])).strip()


@app.route("/api/members", methods=["GET"])
@require_admin
def list_members():
    try:
        with get_db() as conn:
            rows = conn.execute(
                """SELECT m.id, m.full_name, m.fornamn, m.mellomnamn, m.etternamn, m.email, m.phone, m.adresse, m.postnummer, m.poststad,
                          m.birth_date, m.membership_type, m.payment_status, m.consent_at, m.created_at, m.updated_at,
                          COALESCE(SUM(p.amount_ore), 0) AS total_paid_ore
                   FROM members m
                   LEFT JOIN payments p ON p.member_id = m.id
                   GROUP BY m.id
                   ORDER BY m.full_name"""
            ).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/members", methods=["POST"])
@require_admin
def create_member():
    data = request.get_json() or {}
    fornamn = (data.get("fornamn") or "").strip()
    mellomnamn = (data.get("mellomnamn") or "").strip()
    etternamn = (data.get("etternamn") or "").strip()
    full_name = _build_full_name(fornamn, mellomnamn, etternamn)
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    adresse = (data.get("adresse") or "").strip()
    postnummer = (data.get("postnummer") or "").strip()
    poststad = (data.get("poststad") or "").strip()
    birth_date = (data.get("birth_date") or "").strip() or None
    membership_type = (data.get("membership_type") or "").strip()
    payment_status = (data.get("payment_status") or "").strip()
    consent_at = data.get("consent_at") or datetime.now(timezone.utc).isoformat()

    if not fornamn or not etternamn:
        return jsonify({"error": "Fornamn og etternamn er påkrevd"}), 400
    if not email:
        return jsonify({"error": "Epost er påkrevd"}), 400
    if not membership_type:
        membership_type = "vanleg"
    if not payment_status:
        payment_status = "ikkje betalt"

    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO members (full_name, fornamn, mellomnamn, etternamn, email, phone, adresse, postnummer, poststad, birth_date, membership_type, payment_status, consent_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (full_name, fornamn, mellomnamn, etternamn, email, phone, adresse, postnummer, poststad, birth_date, membership_type, payment_status, consent_at, now, now),
        )
        conn.commit()
        mid = cur.lastrowid
    return jsonify({"id": mid, "message": "Medlem lagt til"}), 201


@app.route("/api/members/<int:mid>", methods=["GET", "PUT", "DELETE"])
@require_admin
def member(mid):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM members WHERE id = ?", (mid,)).fetchone()
    if not row:
        return jsonify({"error": "Medlem finst ikkje"}), 404
    row = dict(row)

    if request.method == "GET":
        return jsonify(row)

    if request.method == "PUT":
        data = request.get_json() or {}
        fornamn = (data.get("fornamn") or row.get("fornamn") or "").strip()
        mellomnamn = (data.get("mellomnamn") or row.get("mellomnamn") or "").strip()
        etternamn = (data.get("etternamn") or row.get("etternamn") or "").strip()
        full_name = _build_full_name(fornamn, mellomnamn, etternamn)
        email = (data.get("email") or row["email"]).strip().lower()
        phone = (data.get("phone") or row.get("phone") or "").strip()
        adresse = (data.get("adresse") or row.get("adresse") or "").strip()
        postnummer = (data.get("postnummer") or row.get("postnummer") or "").strip()
        poststad = (data.get("poststad") or row.get("poststad") or "").strip()
        birth_date = (data.get("birth_date") or row.get("birth_date") or "").strip() or None
        membership_type = (data.get("membership_type") or row["membership_type"]).strip()
        payment_status = (data.get("payment_status") or row["payment_status"]).strip()
        if not fornamn or not etternamn:
            return jsonify({"error": "Fornamn og etternamn er påkrevd"}), 400
        if not email:
            return jsonify({"error": "Epost er påkrevd"}), 400
        now = datetime.now(timezone.utc).isoformat()
        with get_db() as conn:
            conn.execute(
                """UPDATE members SET full_name=?, fornamn=?, mellomnamn=?, etternamn=?, email=?, phone=?, adresse=?, postnummer=?, poststad=?, birth_date=?, membership_type=?, payment_status=?, updated_at=?
                   WHERE id=?""",
                (full_name, fornamn, mellomnamn, etternamn, email, phone, adresse, postnummer, poststad, birth_date, membership_type, payment_status, now, mid),
            )
            conn.commit()
        return jsonify({"message": "Oppdatert"})

    if request.method == "DELETE":
        with get_db() as conn:
            conn.execute("DELETE FROM payments WHERE member_id = ?", (mid,))
            conn.execute("DELETE FROM members WHERE id = ?", (mid,))
            conn.commit()
        return jsonify({"message": "Medlem sletta"}), 200

    return jsonify({"error": "Ugyldig metode"}), 405


@app.route("/api/members/<int:mid>/payments", methods=["GET", "POST"])
@require_admin
def member_payments(mid):
    with get_db() as conn:
        member_exists = conn.execute("SELECT 1 FROM members WHERE id = ?", (mid,)).fetchone()
        if not member_exists:
            return jsonify({"error": "Medlem finst ikkje"}), 404

        if request.method == "GET":
            rows = conn.execute(
                """SELECT id, amount_ore, paid_at, note, created_at
                   FROM payments
                   WHERE member_id = ?
                   ORDER BY paid_at DESC, id DESC""",
                (mid,),
            ).fetchall()
            total_ore = conn.execute(
                "SELECT COALESCE(SUM(amount_ore), 0) FROM payments WHERE member_id = ?",
                (mid,),
            ).fetchone()[0]
            return jsonify(
                {
                    "payments": [dict(r) for r in rows],
                    "total_ore": int(total_ore or 0),
                }
            )

        data = request.get_json() or {}
        amount_nok = data.get("amount_nok")
        paid_at = (data.get("paid_at") or "").strip()
        note = (data.get("note") or "").strip() or None
        try:
            amount_nok = float(amount_nok)
        except (TypeError, ValueError):
            return jsonify({"error": "Beløp må vere eit tal"}), 400
        if amount_nok <= 0:
            return jsonify({"error": "Beløp må vere større enn 0"}), 400
        amount_ore = int(round(amount_nok * 100))
        if not paid_at:
            paid_at = datetime.now(timezone.utc).isoformat()
        elif len(paid_at) == 10:
            paid_at = f"{paid_at}T12:00:00"
        created_at = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            """INSERT INTO payments (member_id, amount_ore, paid_at, note, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (mid, amount_ore, paid_at, note, created_at),
        )
        conn.commit()
        return jsonify({"id": cur.lastrowid, "message": "Betaling registrert"}), 201


def _medlemstype_visning(membership_type: str, *, med_beskrivelse: bool = False) -> str:
    """Returner visningsnamn for medlemstype (vanleg→Kul, kul→Superkul)."""
    if membership_type == "kul":
        return "Superkul (meir enn 5 kr)" if med_beskrivelse else "Superkul"
    return "Kul (5 kr)" if med_beskrivelse else "Kul"


@app.route("/api/export/excel")
@require_admin
def export_excel():
    """Last ned medlemslista som CSV (Excel-kompatibel)."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT fornamn, mellomnamn, etternamn, email, phone, adresse, postnummer, poststad,
                      birth_date, membership_type, payment_status, consent_at
               FROM members ORDER BY full_name"""
        ).fetchall()
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow([
        "Fornamn", "Mellomnamn", "Etternamn", "Epost", "Telefon", "Adresse",
        "Postnummer", "Poststad", "Fødselsdato", "Medlemstype", "Betalingsstatus", "Samtykke"
    ])
    for r in rows:
        writer.writerow([
            r["fornamn"] or "",
            r["mellomnamn"] or "",
            r["etternamn"] or "",
            r["email"] or "",
            r["phone"] or "",
            r["adresse"] or "",
            r["postnummer"] or "",
            r["poststad"] or "",
            r["birth_date"] or "",
            _medlemstype_visning(r["membership_type"] or "vanleg"),
            r["payment_status"] or "",
            r["consent_at"] or "",
        ])
    # UTF-8 med BOM slik at Excel opnar teiknsettet riktig
    body = "\ufeff" + buf.getvalue()
    return Response(
        body,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=medlemsliste.csv"},
    )


@app.route("/api/gdpr/export/<int:mid>")
@require_admin
def gdpr_export(mid):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM members WHERE id = ?", (mid,)).fetchone()
    if not row:
        return jsonify({"error": "Medlem finst ikkje"}), 404
    return jsonify(dict(row))


@app.route("/api/gdpr/delete/<int:mid>", methods=["POST"])
@require_admin
def gdpr_delete(mid):
    with get_db() as conn:
        conn.execute("DELETE FROM members WHERE id = ?", (mid,))
        conn.commit()
    return jsonify({"message": "Medlem sletta"}), 200


def main():
    # Tydelig melding om database-kryptering ved oppstart
    if DB_KEY:
        if _use_sqlcipher:
            sys.stderr.write("Database: kryptert (SQLCipher). medlemsregister.db er ikkje lesbar som rein tekst.\n")
        else:
            sys.stderr.write(
                "Database: UKRYPTERT. MEDLEMSREGISTER_DB_KEY er satt, men sqlcipher3 er ikkje tilgjengeleg.\n"
                "For kryptering: installer libsqlcipher (macOS: brew install sqlcipher), deretter pip install sqlcipher3\n"
            )
    else:
        sys.stderr.write("Database: ukyrptert (ingen MEDLEMSREGISTER_DB_KEY). Sett key i .env for kryptering.\n")
    init_db()
    port = int(os.environ.get("PORT", 5001))
    # Ved driftsetjing: la serveren lytte på 0.0.0.0
    host = "0.0.0.0" if os.environ.get("MEDLEMSREGISTER_PRODUCTION") else "127.0.0.1"
    app.run(host=host, port=port, debug=os.environ.get("FLASK_DEBUG", "0") == "1")


if __name__ == "__main__":
    main()
