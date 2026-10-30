#!/usr/bin/env python3
"""
Bygdelista – GDPR-sikkert medlemsliste for Oslobygda.
Felter: namn, epost, telefon, adresse, postnummer, poststad, fødselsdato, medlemstype, betalingsstatus, samtykke.
Database kan krypterast med SQLCipher ved å setje MEDLEMSREGISTER_DB_KEY (da vert fila ikkje lesbar i BBEdit o.l.).
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation
from datetime import timedelta
import os
import sys
import time
import ssl
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote
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
    redirect,
    url_for,
    Response,
    send_from_directory,
)
from styre_auth import install_auth, init_auth_db
from database import managed_db
from personvern import init_privacy, erase_member, process_privacy_jobs
from jinja2 import ChoiceLoader, FileSystemLoader, PrefixLoader

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "medlemsregister.db"

# Last .env frå medlemsregister-mappa (så du ikkje må køyre export manuelt)
try:
    from dotenv import load_dotenv

    if os.environ.get("BYGDELISTA_LOCAL_TEST") != "1":
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
            "Databasen kan ikkje opnast med krypteringsnøkkel før driveren er installert.",
            UserWarning,
        )

app = Flask(
    __name__,
    static_folder="fast",
    static_url_path="/fast",
    template_folder="malar",
)
# Jekyll og Flask les same footer-mal, utan kopiar som må synkroniserast.
app.jinja_loader = ChoiceLoader(
    [
        app.jinja_loader,
        PrefixLoader({"nettstad": FileSystemLoader(APP_DIR.parent / "_tillegg")}),
    ]
)


@app.get("/felles/topp.css")
def shared_header_css():
    return send_from_directory(APP_DIR.parent / "lutar", "topp.css")


@app.get("/felles/kolofon.css")
def shared_footer_css():
    return send_from_directory(APP_DIR.parent / "lutar", "kolofon.css")


@app.context_processor
def site_navigation():
    import yaml

    items = yaml.safe_load((APP_DIR.parent / "_data/nav.yml").read_text())
    return {
        "site_nav": [
            dict(
                label=item["label"],
                membership=item["path"] == "/bli-medlem/",
                url=prefix_url("new_signup")
                if item["path"] == "/bli-medlem/"
                else "https://oslobygda.no" + item["path"],
                current=item["path"] == "/bli-medlem/",
            )
            for item in items
        ]
    }


@app.errorhandler(503)
def service_unavailable(error):
    return render_template("innmelding_vent.html", environment=None), 503


app.secret_key = os.environ.get("MEDLEMSREGISTER_SECRET_KEY", "endre-meg-i-produksjon")

# Ved drift bak omvendt mellomtenar på oslobygda.no/medlemsregister/ – sett til "/medlemsregister"
URL_PREFIX = os.environ.get("MEDLEMSREGISTER_URL_PREFIX", "").rstrip("/")
if URL_PREFIX:
    app.config["APPLICATION_ROOT"] = URL_PREFIX

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
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
    """Stopp automatisk migrering som ikkje kan garantere alle tabellane."""
    if _use_sqlcipher and DB_PATH.exists() and _is_plain_sqlite(DB_PATH):
        raise RuntimeError(
            "Databasen er ukryptert. Ta backup og migrer heile databasen med SQLCipher før krypteringsnøkkelen blir teken i bruk."
        )


def _restrict_db_permissions(path: Path) -> None:
    """Sett fil slik at berre eigar kan lese/skrive (chmod 600)."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def get_db():
    if DB_KEY and not _use_sqlcipher:
        raise RuntimeError(
            "Krypteringsnøkkel er sett, men SQLCipher manglar. Databasen vert ikkje opna."
        )
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
    try:
        conn.execute("PRAGMA foreign_keys = ON")
    except (sqlite3.Error, AttributeError):
        pass
    return conn


def _default_medlemsbetalingsar() -> int:
    """Standardår for nye betalingar (miljø MEDLEMSBETALING_AR, elles kalenderår i UTC)."""
    try:
        raw = (
            os.environ.get("MEDLEMSBETALING_AR") or str(datetime.now(timezone.utc).year)
        ).strip()
        return int(raw)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc).year


def _get_medlemsbetalingsar(conn) -> int:
    """Aktivt medlemsoppkrævingsår (app_settings, elles default)."""
    try:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            ("medlemsbetalingsar",),
        ).fetchone()
        if row and row[0] is not None and str(row[0]).strip() != "":
            return int(str(row[0]).strip())
    except (ValueError, TypeError, sqlite3.OperationalError):
        pass
    return _default_medlemsbetalingsar()


def _nok_to_ore(value, *, allow_zero=False):
    try:
        number = Decimal(str(value).strip().replace(",", "."))
        if (
            not number.is_finite()
            or number < (0 if allow_zero else Decimal("0.01"))
            or number > 1000000000
        ):
            raise ValueError()
        ore = number * 100
        if ore != ore.to_integral_value():
            raise ValueError()
        return int(ore)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(
            "Beløpet må vere eit gyldig kronebeløp med høgst to desimalar."
        ) from None


def _get_superkul_grense(conn):
    from kontingent import period
    try:
        policy=period(conn,_get_medlemsbetalingsar(conn))
        if policy and policy["superkul_ore"] is not None:
            return policy["superkul_ore"]
    except sqlite3.OperationalError:
        pass
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key='superkul_grense_ore'"
    ).fetchone()
    return int(row[0]) if row else 500


def _oppdater_fra_innbetalingar(conn, mid, *, reset_empty=False):
    member = conn.execute(
        "SELECT membership_type, payment_status FROM members WHERE id=?", (mid,)
    ).fetchone()
    if not member:
        return
    total = conn.execute(
        "SELECT COALESCE(SUM(amount_ore),0) FROM payments WHERE member_id=? AND for_year=?",
        (mid, _get_medlemsbetalingsar(conn)),
    ).fetchone()[0]
    if total <= 0 and not reset_empty:
        return  # Manuelle statusar som gratis vert bevarte når ingen betaling er registrert.
    status = (
        "betalt"
        if total > 0
        else ("gratis" if member["payment_status"] == "gratis" else "ikkje betalt")
    )
    kind = (
        member["membership_type"]
        if member["membership_type"].strip().lower() == "styret"
        else ("kul" if total > _get_superkul_grense(conn) else "vanleg")
    )
    if member["payment_status"] != status or member["membership_type"] != kind:
        conn.execute(
            "UPDATE members SET payment_status=?, membership_type=?, updated_at=? WHERE id=?",
            (status, kind, datetime.now(timezone.utc).isoformat(), mid),
        )


def _oppdater_alle_fra_innbetalingar(conn):
    for row in conn.execute(
        "SELECT DISTINCT member_id FROM payments WHERE for_year=?",
        (_get_medlemsbetalingsar(conn),),
    ).fetchall():
        _oppdater_fra_innbetalingar(conn, row[0])


def _parse_dato_ymd(s: str | None) -> date | None:
    """Parsar dato YYYY-MM-DD (eller ISO med tid), elles None."""
    if s is None:
        return None
    t = str(s).strip()
    if len(t) < 10:
        return None
    t = t[:10]
    try:
        y, m, d = t.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, TypeError, AttributeError):
        return None


def _alder_år(fødsel: date, idag: date) -> int:
    a = idag.year - fødsel.year
    if (idag.month, idag.day) < (fødsel.month, fødsel.day):
        a -= 1
    return a


def init_db():
    from ny_innmelding import init_signup

    init_signup(get_db)
    init_auth_db(get_db)
    with managed_db(get_db) as conn:
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
        for col in (
            "adresse",
            "postnummer",
            "poststad",
            "fornamn",
            "mellomnamn",
            "etternamn",
            "birth_date",
        ):
            try:
                conn.execute(f"ALTER TABLE members ADD COLUMN {col} TEXT")
            except Exception as e:
                if "duplicate column" not in str(e).lower():
                    raise
        # Migrer gamle rader: sett fornamn = full_name så brukar kan dele opp ved redigering
        conn.execute(
            "UPDATE members SET fornamn = full_name WHERE fornamn IS NULL AND full_name IS NOT NULL"
        )
        # Normaliser betalingsstatus til nynorsk
        conn.execute(
            "UPDATE members SET payment_status = 'ikkje betalt' WHERE payment_status = 'ikke betalt'"
        )
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY NOT NULL,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS medlemsar_arkiv (
                ar INTEGER PRIMARY KEY NOT NULL,
                totalt_ore INTEGER NOT NULL,
                antall_medlemer_med_betaling INTEGER NOT NULL,
                oppretta TEXT NOT NULL
            );
            """
        )
        try:
            conn.execute("ALTER TABLE payments ADD COLUMN for_year INTEGER")
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                raise
        default_ar = _default_medlemsbetalingsar()
        conn.execute(
            "UPDATE payments SET for_year = ? WHERE for_year IS NULL", (default_ar,)
        )
        if not conn.execute(
            "SELECT 1 FROM app_settings WHERE key = 'medlemsbetalingsar'"
        ).fetchone():
            conn.execute(
                "INSERT INTO app_settings (key, value) VALUES ('medlemsbetalingsar', ?)",
                (str(default_ar),),
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_payments_for_year ON payments(for_year)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO app_settings(key,value) VALUES ('superkul_grense_ore','500')"
        )
        _oppdater_alle_fra_innbetalingar(conn)
        conn.commit()
    init_privacy(get_db)
    from arsdokument import init_documents
    init_documents(get_db)
    from rekneskap import init_ledger
    init_ledger(get_db)
    from offentleg_rekneskap import init_public_ledger
    init_public_ledger(get_db)
    from budsjett import init_budgets
    init_budgets(get_db)
    from betalingsimport import init_payment_import
    init_payment_import(get_db)


def require_admin(f):
    from functools import wraps

    @wraps(f)
    def inner(*args, **kwargs):
        if not app.extensions["styre_auth_valid"]():
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

from okonomi import install_ledger
install_ledger(app, get_db, require_admin, lambda: DB_PATH)
from budsjett_vising import install_budgets
install_budgets(app, get_db, require_admin)
from betalingsimport_vising import install_payment_import
install_payment_import(app, get_db, require_admin)
from arsmote_utskrift import install_print
install_print(app, get_db, require_admin)

install_auth(app, get_db, prefix_url)

from tilskipingar import install_calendar

install_calendar(app, require_admin)

from arsdokument import install_documents
install_documents(app, get_db, require_admin)


@app.route("/")
@require_admin
def index():
    return render_template("index.html")


@app.get("/medlemsliste/hjelp")
@require_admin
def member_help():
    response=app.make_response(render_template("medlemsliste_hjelp.html"))
    response.headers["Cache-Control"]="no-store"
    return response


# —— Offentleg innmeldingsskjema (ingen innlogging) ——


@app.route("/innmelding")
def innmelding_page():
    return redirect(prefix_url("new_signup"), code=302)


def _brevo_request(
    method: str, path: str, api_key: str, body: dict | None = None
) -> tuple[int, dict]:
    url = f"https://api.brevo.com/v3/{path.lstrip('/')}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(
        url,
        data=data,
        headers={
            "api-key": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method=method.upper(),
    )
    try:
        with urlopen(req, timeout=20, context=_SSL_CTX) as res:
            payload = res.read().decode().strip()
            return res.status, (json.loads(payload) if payload else {})
    except HTTPError as e:
        raw = e.read().decode().strip()
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"message": raw or str(e)}
        return e.code, parsed
    except (URLError, OSError) as e:
        return 0, {"message": str(e)}


@app.route("/api/innmelding", methods=["POST"])
def api_innmelding():
    """Utgått API. Ikkje send e-post eller opprett kontaktar utan betaling."""
    return jsonify({"error": "Dette skjemaet er avvikla. Bruk /bli-medlem."}), 410


# —— API (berre for innlogga styret) ——


@app.route("/api/sync-contacts", methods=["POST"])
@require_admin
def api_sync_contacts():
    """Avvikla: Bygdelista er hovudregisteret, Brevo tek imot nyhendebrevkontaktar."""
    return jsonify({"error":"Import frå nyhendebrevlista er avvikla. Nye medlemmar blir registrerte i Bygdelista gjennom innmelding."}),410


def _build_full_name(fornamn, mellomnamn, etternamn):
    return " ".join(filter(None, [fornamn, mellomnamn, etternamn])).strip()


@app.route("/api/members", methods=["GET"])
@require_admin
def list_members():
    try:
        with managed_db(get_db) as conn:
            ar = _get_medlemsbetalingsar(conn)
            rows = conn.execute(
                """SELECT m.id, m.full_name, m.fornamn, m.mellomnamn, m.etternamn, m.email, m.phone, m.adresse, m.postnummer, m.poststad,
                          m.birth_date, m.membership_type, m.payment_status, m.consent_at, m.created_at, m.updated_at,
                          COALESCE(SUM(CASE WHEN p.for_year = ? THEN p.amount_ore ELSE 0 END), 0) AS total_paid_ore
                   FROM members m
                   LEFT JOIN payments p ON p.member_id = m.id
                   WHERE m.privacy_deleted=0
                   GROUP BY m.id
                   ORDER BY m.full_name""",
                (ar,),
            ).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception:
        app.logger.exception("Kunne ikkje hente medlemsoversikta")
        return jsonify({"error": "Kunne ikkje hente medlemsoversikta."}), 500


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
    with managed_db(get_db) as conn:
        cur = conn.execute(
            """INSERT INTO members (full_name, fornamn, mellomnamn, etternamn, email, phone, adresse, postnummer, poststad, birth_date, membership_type, payment_status, consent_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                full_name,
                fornamn,
                mellomnamn,
                etternamn,
                email,
                phone,
                adresse,
                postnummer,
                poststad,
                birth_date,
                membership_type,
                payment_status,
                consent_at,
                now,
                now,
            ),
        )
        conn.commit()
        mid = cur.lastrowid
    return jsonify({"id": mid, "message": "Medlem lagt til"}), 201


@app.route("/api/members/<int:mid>", methods=["GET", "PUT", "DELETE"])
@require_admin
def member(mid):
    with managed_db(get_db) as conn:
        row = conn.execute(
            "SELECT * FROM members WHERE id = ? AND privacy_deleted=0", (mid,)
        ).fetchone()
    if not row:
        return jsonify({"error": "Medlem finst ikkje"}), 404
    row = dict(row)

    if request.method == "GET":
        return jsonify(row)

    if request.method == "PUT":
        data = request.get_json() or {}
        fornamn = (data.get("fornamn", row.get("fornamn")) or "").strip()
        mellomnamn = (data.get("mellomnamn", row.get("mellomnamn")) or "").strip()
        etternamn = (data.get("etternamn", row.get("etternamn")) or "").strip()
        full_name = _build_full_name(fornamn, mellomnamn, etternamn)
        email = (data.get("email", row.get("email")) or "").strip().lower()
        phone = (data.get("phone", row.get("phone")) or "").strip()
        adresse = (data.get("adresse", row.get("adresse")) or "").strip()
        postnummer = (data.get("postnummer", row.get("postnummer")) or "").strip()
        poststad = (data.get("poststad", row.get("poststad")) or "").strip()
        birth_date = (
            data.get("birth_date", row.get("birth_date")) or ""
        ).strip() or None
        membership_type = (
            data.get("membership_type", row.get("membership_type")) or ""
        ).strip()
        payment_status = (
            data.get("payment_status", row.get("payment_status")) or ""
        ).strip()
        if not fornamn or not etternamn:
            return jsonify({"error": "Fornamn og etternamn er påkrevd"}), 400
        if not email:
            return jsonify({"error": "Epost er påkrevd"}), 400
        now = datetime.now(timezone.utc).isoformat()
        with managed_db(get_db) as conn:
            conn.execute(
                """UPDATE members SET full_name=?, fornamn=?, mellomnamn=?, etternamn=?, email=?, phone=?, adresse=?, postnummer=?, poststad=?, birth_date=?, membership_type=?, payment_status=?, updated_at=?
                   WHERE id=?""",
                (
                    full_name,
                    fornamn,
                    mellomnamn,
                    etternamn,
                    email,
                    phone,
                    adresse,
                    postnummer,
                    poststad,
                    birth_date,
                    membership_type,
                    payment_status,
                    now,
                    mid,
                ),
            )
            conn.commit()
        return jsonify({"message": "Oppdatert"})

    if request.method == "DELETE":
        with managed_db(get_db) as conn:
            conn.execute("BEGIN IMMEDIATE")
            result, status = erase_member(conn, mid)
        return jsonify(result), status

    return jsonify({"error": "Ugyldig metode"}), 405


@app.route("/api/members/<int:mid>/payments", methods=["GET", "POST"])
@require_admin
def member_payments(mid):
    with managed_db(get_db) as conn:
        member_exists = conn.execute(
            "SELECT 1 FROM members WHERE id = ? AND privacy_deleted=0", (mid,)
        ).fetchone()
        if not member_exists:
            return jsonify({"error": "Medlem finst ikkje"}), 404

        if request.method == "GET":
            ar = _get_medlemsbetalingsar(conn)
            rows = conn.execute(
                """SELECT id, amount_ore, paid_at, note, created_at, for_year,
                          EXISTS(SELECT 1 FROM signup_orders WHERE payment_id=payments.id) AS vipps
                   FROM payments
                   WHERE member_id = ?
                   ORDER BY paid_at DESC, id DESC""",
                (mid,),
            ).fetchall()
            total_all = conn.execute(
                "SELECT COALESCE(SUM(amount_ore), 0) FROM payments WHERE member_id = ?",
                (mid,),
            ).fetchone()[0]
            total_year = conn.execute(
                "SELECT COALESCE(SUM(amount_ore), 0) FROM payments WHERE member_id = ? AND for_year = ?",
                (mid, ar),
            ).fetchone()[0]
            return jsonify(
                {
                    "payments": [dict(r) for r in rows],
                    "total_ore": int(total_year or 0),
                    "total_ore_all": int(total_all or 0),
                    "medlemsbetalingsar": ar,
                }
            )

        data = request.get_json() or {}
        amount_nok = data.get("amount_nok")
        paid_at = (data.get("paid_at") or "").strip()
        note = (data.get("note") or "").strip() or None
        try:
            amount_ore = _nok_to_ore(amount_nok)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        if not paid_at:
            paid_at = datetime.now(timezone.utc).isoformat()
        elif len(paid_at) == 10:
            paid_at = f"{paid_at}T12:00:00"
        created_at = datetime.now(timezone.utc).isoformat()
        ar = _get_medlemsbetalingsar(conn)
        cur = conn.execute(
            """INSERT INTO payments (member_id, amount_ore, paid_at, note, created_at, for_year)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (mid, amount_ore, paid_at, note, created_at, ar),
        )
        _oppdater_fra_innbetalingar(conn, mid)
        conn.commit()
        return jsonify(
            {
                "id": cur.lastrowid,
                "message": "Betaling registrert. Betalingsstatus og medlemstype er oppdaterte.",
            }
        ), 201


@app.route("/api/members/<int:mid>/payments/<int:pid>", methods=["DELETE"])
@require_admin
def delete_member_payment(mid, pid):
    with managed_db(get_db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        payment = conn.execute(
            "SELECT for_year FROM payments WHERE id=? AND member_id=?", (pid, mid)
        ).fetchone()
        if not payment:
            return jsonify({"error": "Betalinga finst ikkje på denne medlemmen."}), 404
        if conn.execute("SELECT 1 FROM payment_group_links WHERE payment_id=?", (pid,)).fetchone() or conn.execute("SELECT 1 FROM payment_ledger_links WHERE payment_id=?", (pid,)).fetchone() or conn.execute("SELECT 1 FROM ledger_journals WHERE source_kind='membership_payment' AND source_id=?", (str(pid),)).fetchone():
            return jsonify({"error": "Betalinga er kopla til bokført rekneskap og kan ikkje slettast. Rett rekneskapen med sporbar reversering."}), 409
        if conn.execute(
            "SELECT 1 FROM signup_orders WHERE payment_id=?", (pid,)
        ).fetchone():
            return jsonify(
                {
                    "error": "Vipps-betalingar må refunderast og avstemmast. Dei kan ikkje slettast som manuelle feilregistreringar."
                }
            ), 409
        year = _get_medlemsbetalingsar(conn)
        if (
            payment["for_year"] != year
            or conn.execute(
                "SELECT 1 FROM medlemsar_arkiv WHERE ar=?", (payment["for_year"],)
            ).fetchone()
        ):
            return jsonify(
                {"error": "Betalingar frå avslutta medlemsår kan ikkje slettast her."}
            ), 409
        conn.execute("DELETE FROM payments WHERE id=? AND member_id=?", (pid, mid))
        _oppdater_fra_innbetalingar(conn, mid, reset_empty=True)
        conn.commit()
    return jsonify(
        {
            "message": "Betalingsregistreringa er sletta. Status og medlemstype er oppdaterte."
        }
    )


@app.route("/api/innstillingar/kontingent", methods=["GET", "PUT"])
@require_admin
def kontingent_innstillingar():
    with managed_db(get_db) as conn:
        if request.method == "PUT":
            data = request.get_json() or {}
            try:
                ore = _nok_to_ore(data.get("superkul_grense_nok"), allow_zero=True)
            except ValueError as error:
                return jsonify({"error": str(error)}), 400
            current_year=_get_medlemsbetalingsar(conn)
            if ore!=_get_superkul_grense(conn) and conn.execute("SELECT 1 FROM signup_orders WHERE for_year=? AND environment='production' AND create_attempted=1 LIMIT 1",(current_year,)).fetchone():
                return jsonify({'error':'Satsen er låst etter at produksjonsbetalingar er starta.'}),409
            conn.execute(
                "INSERT INTO app_settings(key,value) VALUES ('superkul_grense_ore',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(ore),),
            )
            conn.execute("UPDATE membership_periods SET superkul_ore=?,revision=revision+1 WHERE year=?",(ore,_get_medlemsbetalingsar(conn)))
            _oppdater_alle_fra_innbetalingar(conn)
            conn.commit()
        return jsonify({"superkul_grense_ore": _get_superkul_grense(conn)})


@app.route("/api/okonomi-sammendrag", methods=["GET"])
@app.route("/api/medlemsoversikt", methods=["GET"])
@require_admin
def api_medlemsoversikt():
    """Samanlagd medlemstal (alder) + innbetaling/arkiv for gjeldande medlemsår."""
    idag = date.today()
    with managed_db(get_db) as conn:
        ar = _get_medlemsbetalingsar(conn)
        tot = conn.execute(
            "SELECT COALESCE(SUM(amount_ore), 0) FROM payments WHERE for_year = ?",
            (ar,),
        ).fetchone()[0]
        n_med = conn.execute(
            "SELECT COUNT(DISTINCT member_id) FROM payments WHERE for_year = ? AND amount_ore > 0",
            (ar,),
        ).fetchone()[0]
        ark = conn.execute(
            "SELECT ar, totalt_ore, antall_medlemer_med_betaling, oppretta FROM medlemsar_arkiv ORDER BY ar DESC"
        ).fetchall()
        fødsel_rader = conn.execute(
            "SELECT birth_date FROM members WHERE privacy_deleted=0"
        ).fetchall()
    from aldersfordeling import age_distribution
    ages = age_distribution(fødsel_rader, idag)
    al_0_25 = ages['age_0_14'] + ages['age_15_25']
    al_26_eldre = ages['age_26_plus']
    al_ukjent = ages['unknown']
    return jsonify(
        {
            "medlemsbetalingsar": ar,
            "totalt_innbetalt_ore": int(tot or 0),
            "antall_medlemer_med_betaling": int(n_med or 0),
            "arkiv": [dict(r) for r in ark],
            "antall_medlemer_totalt": al_0_25 + al_26_eldre + al_ukjent,
            "alder_0_25": al_0_25,
            "alder_0_14": ages["age_0_14"],
            "alder_15_25": ages["age_15_25"],
            "alder_26_eller_eldre": al_26_eldre,
            "alder_utan_fodselsdato": al_ukjent,
        }
    )


@app.route("/api/medlemsar/lukk", methods=["POST"])
@require_admin
def api_medlemsar_lukk():
    """
    Arkivert avslutta medlemsår (sum + tal), oppdaterer til neste kalenderår,
    og nullstiller betalingsstatus så nye kontingentar kan føreleggjast
    (medlemmar med status «gratis» vert ikkje endra).
    """
    data = request.get_json() or {}
    try:
        bekreft = int(data.get("bekreft_ar"))
    except (TypeError, ValueError):
        return (
            jsonify(
                {
                    "error": 'Send JSON med { "bekreft_ar": <år> } – same tal som står som «Gjeldande medlemsår» (år du avsluttar).'
                }
            ),
            400,
        )
    now = datetime.now(timezone.utc).isoformat()
    with managed_db(get_db) as conn:
        ar = _get_medlemsbetalingsar(conn)
        if bekreft != ar:
            return (
                jsonify(
                    {
                        "error": f"Bekreftinga ({bekreft}) samsvarer ikkje med gjeldande medlemsår ({ar})."
                    }
                ),
                400,
            )
        if conn.execute("SELECT 1 FROM medlemsar_arkiv WHERE ar = ?", (ar,)).fetchone():
            return jsonify({"error": f"År {ar} er allereie arkivert."}), 400
        tot = conn.execute(
            "SELECT COALESCE(SUM(amount_ore), 0) FROM payments WHERE for_year = ?",
            (ar,),
        ).fetchone()[0]
        n_med = conn.execute(
            "SELECT COUNT(DISTINCT member_id) FROM payments WHERE for_year = ? AND amount_ore > 0",
            (ar,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO medlemsar_arkiv (ar, totalt_ore, antall_medlemer_med_betaling, oppretta) VALUES (?, ?, ?, ?)",
            (ar, int(tot or 0), int(n_med or 0), now),
        )
        nytt = ar + 1
        upd = conn.execute(
            "UPDATE app_settings SET value = ? WHERE key = 'medlemsbetalingsar'",
            (str(nytt),),
        )
        if upd.rowcount == 0:
            conn.execute(
                "INSERT INTO app_settings (key, value) VALUES ('medlemsbetalingsar', ?)",
                (str(nytt),),
            )
        conn.execute(
            "UPDATE members SET payment_status = 'ikkje betalt' "
            "WHERE LOWER(TRIM(payment_status)) != 'gratis'",
        )
        conn.commit()
    return jsonify(
        {
            "message": f"Medlemsår {ar} er arkivert. Gjeldande medlemsår er no {nytt}. "
            f"Betalingsstatus (utanom «gratis») er satt til «ikkje betalt».",
            "forrige_ar": ar,
            "nytt_ar": nytt,
        }
    )


def _medlemstype_visning(membership_type: str, *, med_beskrivelse: bool = False) -> str:
    """Returner visningsnamn for medlemstype (vanleg→Kul, kul→Superkul)."""
    if membership_type == "styret":
        return "Styret"
    if membership_type == "kul":
        return "Superkul (meir enn 5 kr)" if med_beskrivelse else "Superkul"
    return "Kul (5 kr)" if med_beskrivelse else "Kul"


def _csv_cell(value):
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(
        ("\t", "\r", "\n")
    ):
        return "'" + text
    return text


@app.route("/api/export/excel")
@require_admin
def export_excel():
    """Last ned medlemslista som CSV (Excel-kompatibel)."""
    with managed_db(get_db) as conn:
        rows = conn.execute(
            """SELECT fornamn, mellomnamn, etternamn, email, phone, adresse, postnummer, poststad,
                      birth_date, membership_type, payment_status, consent_at
               FROM members WHERE privacy_deleted=0 ORDER BY full_name"""
        ).fetchall()
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(
        [
            "Fornamn",
            "Mellomnamn",
            "Etternamn",
            "Epost",
            "Telefon",
            "Adresse",
            "Postnummer",
            "Poststad",
            "Fødselsdato",
            "Medlemstype",
            "Betalingsstatus",
            "Samtykke",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                _csv_cell(value)
                for value in [
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
                ]
            ]
        )
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
    with managed_db(get_db) as conn:
        row = conn.execute(
            "SELECT * FROM members WHERE id = ? AND privacy_deleted=0", (mid,)
        ).fetchone()
    if not row:
        return jsonify({"error": "Medlem finst ikkje"}), 404
    return jsonify(dict(row))


@app.route("/api/gdpr/delete/<int:mid>", methods=["POST"])
@require_admin
def gdpr_delete(mid):
    with managed_db(get_db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        result, status = erase_member(conn, mid)
    return jsonify(result), status


def _signup_newsletter(member):
    # Berre nødvendige kontaktfelt vert overførte. Aldri nullstill avmeldingsstatus.
    key = os.environ.get("BREVO_API_KEY", "").strip()
    list_id = os.environ.get("BREVO_INNMELDING_LIST_ID") or os.environ.get(
        "BREVO_LIST_ID", ""
    )
    if not key or not str(list_id).isdigit():
        return False
    status, _ = _brevo_request(
        "POST",
        "/contacts",
        key,
        {
            "email": member["email"],
            "attributes": {
                "FIRSTNAME": member["fornamn"],
                "LASTNAME": member["etternamn"],
            },
            "listIds": [int(list_id)],
            "updateEnabled": True,
        },
    )
    return status in (200, 201, 204)


def _delete_brevo_contact(email):
    key = os.environ.get("BREVO_API_KEY", "").strip()
    if not key:
        return False
    status, _ = _brevo_request("DELETE", "/contacts/" + quote(email, safe=""), key)
    return status in (204, 404)


def _privacy_maintenance():
    # Lesekontroll kvar 30. dag held òg API-nøkkelen i bruk når det er få innmeldingar.
    key = os.environ.get("BREVO_API_KEY", "").strip()
    list_id = os.environ.get("BREVO_INNMELDING_LIST_ID") or os.environ.get(
        "BREVO_LIST_ID", ""
    )
    now = int(time.time())
    if key and str(list_id).isdigit():
        with managed_db(get_db) as db:
            row = db.execute(
                "SELECT value FROM app_settings WHERE key='brevo_api_last_check'"
            ).fetchone()
        if not row or now - int(row[0]) >= 30 * 86400:
            status, _ = _brevo_request(
                "GET", "/contacts/lists/" + str(int(list_id)), key
            )
            if status == 200:
                with managed_db(get_db) as db:
                    db.execute(
                        "INSERT INTO app_settings(key,value) VALUES ('brevo_api_last_check',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (str(now),),
                    )
            else:
                app.logger.warning(
                    "Brevo API-kontroll feila. Kontroller tilgang og listeoppsett."
                )
    return process_privacy_jobs(get_db, _delete_brevo_contact)


from innmelding_epost import send_confirmation
from ny_innmelding import install_signup

install_signup(
    app,
    get_db,
    _get_medlemsbetalingsar,
    _get_superkul_grense,
    _signup_newsletter,
    require_admin,
    _privacy_maintenance,
    confirmation=send_confirmation,
)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


from kontingent import install_renewals
install_renewals(app,get_db,require_admin)

def main():
    # Tydelig melding om database-kryptering ved oppstart
    if DB_KEY:
        if _use_sqlcipher:
            sys.stderr.write(
                "Database: kryptert (SQLCipher). medlemsregister.db er ikkje lesbar som rein tekst.\n"
            )
        else:
            sys.stderr.write(
                "Database: UKRYPTERT. MEDLEMSREGISTER_DB_KEY er satt, men sqlcipher3 er ikkje tilgjengeleg.\n"
                "For kryptering: installer libsqlcipher (macOS: brew install sqlcipher), deretter pip install sqlcipher3\n"
            )
    else:
        sys.stderr.write(
            "Database: ukyrptert (ingen MEDLEMSREGISTER_DB_KEY). Sett key i .env for kryptering.\n"
        )
    init_db()
    port = int(os.environ.get("PORT", 5001))
    # Ved driftsetjing: la serveren lytte på 0.0.0.0
    host = "0.0.0.0" if os.environ.get("MEDLEMSREGISTER_PRODUCTION") else "127.0.0.1"
    app.run(host=host, port=port, debug=os.environ.get("FLASK_DEBUG", "0") == "1")


from styremodul import install_board
install_board(app,require_admin)

if __name__ == "__main__":
    main()
