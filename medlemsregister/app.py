#!/usr/bin/env python3
"""
Bygdelista – medlemsregister for Oslobygda.
Felter: namn, epost, telefon, adresse, postnummer, poststad, fødselsdato, medlemstype, betalingsstatus, samtykke.
Database kan krypterast med SQLCipher ved å setje MEDLEMSREGISTER_DB_KEY (da vert fila ikkje lesbar i BBEdit o.l.).
"""

from betalingsreglar import member_kind
from csrf import csrf_exempt
from datetime import timedelta
import os
import sys
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    redirect,
    url_for,
    send_from_directory,
)
from styre_auth import install_auth, init_auth_db
from database import managed_db
from personvern import init_privacy
from jinja2 import ChoiceLoader, FileSystemLoader, PrefixLoader

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


@app.get('/felles/fonts/<path:filename>')
def shared_fonts(filename):
    return send_from_directory(APP_DIR.parent / 'lutar' / 'fonts', filename)


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
                url=prefix_url('member_home') if item['path']=='/mi-side/' else
                    prefix_url('new_signup') if item['path']=='/bli-medlem/' else 'https://oslobygda.no'+item['path'],
                current=(item['path']=='/mi-side/' and request.endpoint and request.endpoint.startswith('member_'))
                    or (item['path']=='/bli-medlem/' and request.endpoint in ('new_signup','signup_edit','signup_status')),
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
    kind = member_kind(total, _get_superkul_grense(conn), member["membership_type"])
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
    from migreringar import Migration, migrate
    from totp_kryptering import migrate as validate_totp

    migrate(get_db, (
        Migration(1, "baseline_20261125", lambda db: _initial_schema(lambda: db)),
    ))
    # Dette er driftskontroll/dataoppdatering, ikkje skjemamigrering. Feil nøkkel
    # skal stoppe også når databasen allereie har rett skjemaversjon.
    with managed_db(get_db) as conn:
        validate_totp(conn)
        _oppdater_alle_fra_innbetalingar(conn)


def _initial_schema(get_db):
    """Versjon 1: historisk skjema og oppgradering av databasar utan versjonslogg.

    Denne samansetjinga og init-funksjonane ho bruker utgjer baseline.
    Nye skjemasteg skal registrerast som nye versjonar i init_db(), ikkje her.
    """
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
        columns = {row[1] for row in conn.execute("PRAGMA table_info(members)")}
        for col in (
            "adresse", "postnummer", "poststad", "fornamn",
            "mellomnamn", "etternamn", "birth_date",
        ):
            if col not in columns:
                conn.execute(f"ALTER TABLE members ADD COLUMN {col} TEXT")
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
        columns = {row[1] for row in conn.execute("PRAGMA table_info(payments)")}
        if "for_year" not in columns:
            conn.execute("ALTER TABLE payments ADD COLUMN for_year INTEGER")
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
    from personvern_vedlikehald import init_retention
    init_retention(get_db, _get_medlemsbetalingsar)
    from medlem_auth import init_member_access
    init_member_access(get_db)
    from arsdokument import init_documents
    init_documents(get_db)
    from sakliste import init_agendas
    init_agendas(get_db)
    from protokoll import init_minutes
    init_minutes(get_db)
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

install_auth(app, get_db, prefix_url, init_db)

from tilskipingar import install_calendar

install_calendar(app, require_admin)

from arsdokument import install_documents
install_documents(app, get_db, require_admin)
from sakliste import install_meetings
install_meetings(app, get_db, require_admin)
from protokoll import install_minutes
install_minutes(app, get_db, require_admin)


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


@app.route("/api/innmelding", methods=["POST"])
@csrf_exempt
def api_innmelding():
    """Utgått API. Ikkje send e-post eller opprett kontaktar utan betaling."""
    return jsonify({"error": "Dette skjemaet er avvikla. Bruk /bli-medlem."}), 410


# —— API (berre for innlogga styret) ——


@app.route("/api/sync-contacts", methods=["POST"])
@require_admin
def api_sync_contacts():
    """Avvikla: Bygdelista er hovudregisteret, Brevo tek imot nyhendebrevkontaktar."""
    return jsonify({"error":"Import frå nyhendebrevlista er avvikla. Nye medlemmar blir registrerte i Bygdelista gjennom innmelding."}),410


from medlemsruter import install_members

install_members(
    app, get_db, require_admin, _get_medlemsbetalingsar, _get_superkul_grense,
    _oppdater_fra_innbetalingar, _oppdater_alle_fra_innbetalingar,
)


from brevo import BrevoContacts, brevo_request as _brevo_request

brevo_contacts = BrevoContacts(
    get_db, app.logger, request=lambda *args, **kwargs: _brevo_request(*args, **kwargs)
)
_signup_newsletter = brevo_contacts.signup
_privacy_maintenance = brevo_contacts.maintenance


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
from personvern_vedlikehald import install_retention
install_retention(app, get_db, require_admin)
from mi_side import install_member_portal
install_member_portal(app, get_db, prefix_url)
from medlem_nyhendebrev import process as process_member_newsletters
app.extensions['member_newsletter_maintenance'] = lambda: process_member_newsletters(get_db, _brevo_request)

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
