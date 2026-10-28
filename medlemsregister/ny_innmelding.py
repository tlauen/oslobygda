"""Nyinnmelding: varig ordre før Vipps-kall, stadfesta trekk før bokføring."""

import base64
from contextlib import closing
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import time
from urllib.parse import urlsplit

from dotenv import dotenv_values, set_key
from flask import abort, redirect, render_template, request, session
from vipps_client import VippsClient, VippsError, amount_ore
from epost import DeliveryUncertain

SCHEMA = """
CREATE TABLE IF NOT EXISTS signup_orders (
 reference TEXT PRIMARY KEY, browser_key TEXT NOT NULL, email TEXT NOT NULL,
 details TEXT NOT NULL, amount_ore INTEGER NOT NULL, for_year INTEGER NOT NULL,
 environment TEXT NOT NULL, msn TEXT NOT NULL, create_key TEXT NOT NULL,
 capture_key TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new', redirect_url TEXT,
 member_id INTEGER, payment_id INTEGER, newsletter INTEGER NOT NULL,
 newsletter_done INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL,
 checked_at REAL NOT NULL DEFAULT 0, lease_until REAL NOT NULL DEFAULT 0,
 lease_token TEXT, problem TEXT NOT NULL DEFAULT '', consent_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS signup_email ON signup_orders(email,environment);
CREATE TABLE IF NOT EXISTS signup_limits (bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, expires REAL NOT NULL);
"""
FIELDS = {
    "fornamn": 100,
    "mellomnamn": 100,
    "etternamn": 100,
    "email": 254,
    "phone": 30,
    "adresse": 200,
    "postnummer": 4,
    "poststad": 100,
    "birth_date": 10,
}


def init_signup(get_db):
    with closing(get_db()) as db:
        db.executescript(SCHEMA)
        columns = {row[1] for row in db.execute("PRAGMA table_info(signup_orders)")}
        for name, definition in (
            ('overview_archived', 'INTEGER NOT NULL DEFAULT 0'),
            ('renewal_member_id', 'INTEGER'),
            ('renewal_link_id', 'INTEGER'),
            ('period_revision', 'INTEGER'),
            ('threshold_ore', 'INTEGER'),
            ('create_attempted', 'INTEGER NOT NULL DEFAULT 0'),
            ('payer_name', "TEXT NOT NULL DEFAULT ''"),
            ('payer_phone', "TEXT NOT NULL DEFAULT ''"),
            ('confirmation_status', "TEXT NOT NULL DEFAULT 'skipped'"),
        ):
            if name not in columns:
                db.execute(f"ALTER TABLE signup_orders ADD COLUMN {name} {definition}")
        db.commit()
    from kontingent import init_periods
    init_periods(get_db)


def credentials(environment):
    if environment == "test":
        config = dotenv_values(Path(__file__).resolve().parent / ".env.vipps-test")
    else:
        config = os.environ
    return config


def client_for(environment, msn=None):
    config = credentials(environment)
    client = VippsClient(
        *(
            config.get(key, "")
            for key in (
                "VIPPS_CLIENT_ID",
                "VIPPS_CLIENT_SECRET",
                "VIPPS_SUBSCRIPTION_KEY",
                "VIPPS_MSN",
            )
        ),
        environment=environment,
    )
    if msn and client.headers["Merchant-Serial-Number"] != msn:
        raise VippsError(
            "Salseininga er endra. Administrator må kontrollere denne ordren."
        )
    return client


def validate(values, minimum=500):
    data = {key: values.get(key, "").strip() for key in FIELDS}
    if any(
        len(data[k]) > maximum or any(ord(c) < 32 for c in data[k])
        for k, maximum in FIELDS.items()
    ):
        raise ValueError("Kontroller lengda og teikna i felta.")
    if not all(
        data[k]
        for k in (
            "fornamn",
            "etternamn",
            "email",
            "phone",
            "adresse",
            "postnummer",
            "poststad",
        )
    ):
        raise ValueError("Fyll ut alle obligatoriske felt.")
    data["email"] = data["email"].casefold()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", data["email"]):
        raise ValueError("Skriv ei gyldig e-postadresse.")
    if not re.fullmatch(r"[0-9]{4}", data["postnummer"]):
        raise ValueError("Postnummeret må ha fire siffer.")
    phone = re.sub(r"[ ()-]", "", data["phone"])
    if not re.fullmatch(r"\+?[0-9]{8,15}", phone):
        raise ValueError("Skriv eit gyldig telefonnummer.")
    data["phone"] = phone
    if data["birth_date"]:
        try:
            born = date.fromisoformat(data["birth_date"])
            if born > date.today() or born.year < 1900:
                raise ValueError()
        except ValueError:
            raise ValueError("Kontroller fødselsdatoen.") from None
    if values.get("terms") != "1":
        raise ValueError("Du må godta salsvilkåra før du går vidare.")
    ore = amount_ore(values.get("amount", ""))
    if ore < minimum:
        raise ValueError(f"Medlemskap kostar minst {minimum/100:.2f} kroner.")
    return data, ore


class SignupService:
    def __init__(self, get_db, get_year, get_threshold, newsletter, confirmation=lambda order: False):
        self.db = get_db
        self.get_year = get_year
        self.get_threshold = get_threshold
        self.newsletter = newsletter
        self.confirmation = confirmation

    def order(self, reference):
        with closing(self.db()) as db:
            row = db.execute(
                "SELECT * FROM signup_orders WHERE reference=?", (reference,)
            ).fetchone()
            return dict(row) if row else None

    def new(self, values, browser_key, environment, ip):
        from kontingent import payable, today
        with closing(self.db()) as db:
            policy=payable(db,today().year)
        data, ore = validate(values,policy["minimum_ore"])
        config = credentials(environment)
        msn = config.get("VIPPS_MSN", "")
        if not msn:
            raise ValueError("Betaling er ikkje sett opp enno.")
        now = time.time()
        stamp = datetime.now(timezone.utc).isoformat()
        with closing(self.db()) as db:
            db.execute("BEGIN IMMEDIATE")
            policy=payable(db,today().year)
            if ore<policy["minimum_ore"]: raise ValueError("Satsane er endra. Last skjemaet på nytt.")
            old = db.execute(
                "SELECT reference FROM signup_orders WHERE browser_key=? AND environment=? AND for_year=?",
                (browser_key, environment,policy["year"]),
            ).fetchone()
            if old:
                db.rollback()
                return old[0]
            bucket = hashlib.sha256(ip.encode()).hexdigest()
            db.execute("DELETE FROM signup_limits WHERE expires<?", (now,))
            limit = db.execute(
                "SELECT count FROM signup_limits WHERE bucket=?", (bucket,)
            ).fetchone()
            if limit and limit[0] >= 10:
                raise ValueError("For mange forsøk. Prøv igjen om ein time.")
            db.execute(
                "INSERT INTO signup_limits VALUES (?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1",
                (bucket, now + 3600),
            )
            existing = db.execute(
                "SELECT 1 FROM members WHERE lower(trim(email))=?", (data["email"],)
            ).fetchone()
            pending = db.execute(
                "SELECT 1 FROM signup_orders WHERE email=? AND environment=? AND status NOT IN ('ABORTED','EXPIRED','TERMINATED')",
                (data["email"], environment),
            ).fetchone()
            if existing or pending:
                db.commit()
                raise ValueError(
                    "Me kan ikkje starte ei ny innmelding med denne e-postadressa. Har du meldt deg inn før, kontakt folk@oslobygda.no."
                )
            ref = "ny-" + secrets.token_hex(16)
            db.execute(
                """INSERT INTO signup_orders(reference,browser_key,email,details,amount_ore,for_year,environment,msn,create_key,capture_key,newsletter,created_at,consent_at,confirmation_status,period_revision,threshold_ore)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ref,
                    browser_key,
                    data["email"],
                    json.dumps(data),
                    ore,
                    policy["year"],
                    environment,
                    msn,
                    secrets.token_hex(16),
                    secrets.token_hex(16),
                    int(values.get("newsletter") == "1"),
                    now,
                    stamp,
                    "pending" if environment == "production" else "skipped",
                    policy["revision"],policy["superkul_ore"],
                ),
            )
            db.commit()
        return ref

    def renew(self,link,values):
        from kontingent import payable, member_paid
        if values.get('terms')!='1': raise ValueError('Du må godta salsvilkåra.')
        ore=amount_ore(values.get('amount',''))
        env=link['environment'];msn=credentials(env).get('VIPPS_MSN','')
        if not msn: raise ValueError('Betaling er ikkje sett opp.')
        with closing(self.db()) as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT * FROM renewal_links WHERE id=? AND token_hash=? AND revoked=0',(link['id'],link['token_hash'])).fetchone()
            member=db.execute('SELECT * FROM members WHERE id=? AND privacy_deleted=0',(link['member_id'],)).fetchone()
            if not current or not member: raise ValueError('Lenkja er ikkje gyldig lenger.')
            policy=payable(db,link['for_year'])
            if ore<policy['minimum_ore']: raise ValueError('Beløpet må vere minst minimumssatsen.')
            if env=='production' and member_paid(db,member['id'],link['for_year']): raise ValueError('Medlemskapen er allereie betalt for dette året.')
            old=db.execute("SELECT * FROM signup_orders WHERE renewal_member_id=? AND for_year=? AND environment=? AND status NOT IN ('ABORTED','EXPIRED','TERMINATED','redacted') ORDER BY created_at DESC LIMIT 1",(member['id'],link['for_year'],env)).fetchone()
            if old:
                if old['renewal_link_id']!=link['id']:
                    # Ny e-postlenkje tek over tilgangen til same ordre, aldri ei ny betaling.
                    db.execute('UPDATE signup_orders SET renewal_link_id=? WHERE reference=?',(link['id'],old['reference']))
                if old['status']=='new' and not old['create_attempted']:
                    db.execute('UPDATE signup_orders SET amount_ore=?,period_revision=?,threshold_ore=? WHERE reference=?',(ore,policy['revision'],policy['superkul_ore'],old['reference']))
                db.commit();return old['reference']
            ref='forny-'+secrets.token_hex(16)
            details={k:member[k] or '' for k in FIELDS}
            db.execute("""INSERT INTO signup_orders(reference,browser_key,email,details,amount_ore,for_year,environment,msn,create_key,capture_key,newsletter,created_at,consent_at,confirmation_status,renewal_member_id,renewal_link_id,period_revision,threshold_ore)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(ref,'renew-'+secrets.token_hex(16),member['email'],json.dumps(details),ore,link['for_year'],env,msn,secrets.token_hex(16),secrets.token_hex(16),0,time.time(),datetime.now(timezone.utc).isoformat(),'pending' if env=='production' else 'skipped',member['id'],link['id'],policy['revision'],policy['superkul_ore']))
            db.commit()
        return ref

    def create(self, reference, return_url):
        order = self.order(reference)
        from kontingent import payable, member_paid
        with closing(self.db()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                policy=payable(db,order['for_year'])
                if order.get('period_revision') is not None and order['period_revision']!=policy['revision'] and not order['create_attempted']:
                    raise ValueError('Satsane er endra. Opne skjemaet på nytt før du betalar.')
                if order['amount_ore']<policy['minimum_ore']:
                    raise ValueError('Beløpet er lågare enn den vedtekne satsen. Kontakt styret.')
                if order.get('renewal_member_id'):
                    link=db.execute('SELECT * FROM renewal_links WHERE id=? AND revoked=0',(order['renewal_link_id'],)).fetchone()
                    member=db.execute('SELECT * FROM members WHERE id=? AND privacy_deleted=0',(order['renewal_member_id'],)).fetchone()
                    if not link or not member: raise ValueError('Fornyingslenkja er ikkje gyldig lenger.')
                    if order['environment']=='production' and member_paid(db,member['id'],order['for_year']):
                        raise ValueError('Medlemskapen er allereie betalt.')
                if order['status'] not in ('new','CREATED'):
                    raise ValueError('Denne betalinga kan ikkje startast på nytt.')
                if order['redirect_url']: return order['redirect_url']
                db.execute('UPDATE signup_orders SET create_attempted=1 WHERE reference=?',(reference,));db.commit()
            except ValueError as exc:
                raise VippsError(str(exc)) from None
        result = client_for(order["environment"], order["msn"]).create(
            reference, order["amount_ore"], return_url, order["create_key"]
        )
        url = result.get("redirectUrl", "")
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
        ):
            raise VippsError(
                "Vipps gav ikkje ei gyldig betalingsadresse. Prøv same betaling igjen."
            )
        with closing(self.db()) as db:
            db.execute(
                "UPDATE signup_orders SET redirect_url=?,status='CREATED' WHERE reference=? AND status='new'",
                (url, reference),
            )
            db.commit()
        return url

    def reconcile(self, reference):
        original = self.order(reference)
        if original and original["status"] == "complete":
            result = client_for(original["environment"], original["msn"]).get(reference)
            self.check_result(original, result)
            if (
                result["aggregate"]["refundedAmount"]["value"]
                or result["aggregate"]["capturedAmount"]["value"]
                != original["amount_ore"]
            ):
                with closing(self.db()) as db:
                    db.execute(
                        "UPDATE signup_orders SET status='review',problem='Refusjon eller endra trekk etter bokføring. Styret må avstemme betalinga.' WHERE reference=? AND status='complete'",
                        (reference,),
                    )
                    db.commit()
            return
        now = time.time()
        lease = secrets.token_hex(16)
        with closing(self.db()) as db:
            # Delt lås mellom web workers og vedlikehaldsjobben. Ingen nettverk under DB-låsen.
            row = db.execute(
                "UPDATE signup_orders SET lease_until=?,lease_token=?,checked_at=? WHERE reference=? AND lease_until<? AND checked_at<? AND status NOT IN ('complete','review','ABORTED','EXPIRED','TERMINATED','redacted')",
                (now + 120, lease, now, reference, now, now - 5),
            )
            db.commit()
            if row.rowcount != 1:
                return
        try:
            order = self.order(reference)
            client = client_for(order["environment"], order["msn"])
            result = client.get(reference)
            self.check_result(order, result)
            aggregate = result["aggregate"]
            captured = aggregate["capturedAmount"]["value"]
            if (
                result["state"] == "AUTHORIZED"
                and captured == 0
                and aggregate["cancelledAmount"]["value"] == 0
                and aggregate["refundedAmount"]["value"] == 0
            ):
                if aggregate["authorizedAmount"]["value"] != order["amount_ore"]:
                    raise VippsError(
                        "Reservert beløp stemmer ikkje. Administrator må kontrollere betalinga."
                    )
                client.capture(reference, order["amount_ore"], order["capture_key"])
                result = client.get(reference)
                self.check_result(order, result)
                captured = result["aggregate"]["capturedAmount"]["value"]
            if (
                result["state"] == "AUTHORIZED"
                and captured == order["amount_ore"]
                and result["aggregate"]["refundedAmount"]["value"] == 0
                and result["aggregate"]["cancelledAmount"]["value"] == 0
            ):
                self.finalize(reference, lease, result.get("userDetails"))
            else:
                unusual = any(
                    result["aggregate"][k]["value"]
                    for k in ("capturedAmount", "cancelledAmount", "refundedAmount")
                )
                terminal_unpaid = (
                    result["state"] in ("ABORTED", "EXPIRED", "TERMINATED")
                    and captured == 0
                    and result["aggregate"]["refundedAmount"]["value"] == 0
                )
                state = (
                    result["state"]
                    if terminal_unpaid
                    or (not unusual and result["state"] in ("CREATED", "AUTHORIZED"))
                    else "review"
                )
                with closing(self.db()) as db:
                    db.execute(
                        "UPDATE signup_orders SET status=?,problem=? WHERE reference=? AND lease_token=?",
                        (
                            state,
                            "" if state != "review" else "Kontroller betalingsstatus",
                            reference,
                            lease,
                        ),
                    )
                    db.commit()
        except (VippsError, ValueError, KeyError, TypeError):
            with closing(self.db()) as db:
                db.execute(
                    "UPDATE signup_orders SET problem='Betalingsstatus må kontrollerast på nytt' WHERE reference=? AND lease_token=?",
                    (reference, lease),
                )
                db.commit()
            raise VippsError(
                "Kunne ikkje stadfeste betalinga enno. Prøv statuskontrollen igjen seinare."
            ) from None
        finally:
            with closing(self.db()) as db:
                db.execute(
                    "UPDATE signup_orders SET lease_until=0 WHERE reference=? AND lease_token=?",
                    (reference, lease),
                )
                db.commit()

    @staticmethod
    def check_result(order, result):
        if (
            type(result["amount"].get("value")) is not int
            or result["reference"] != order["reference"]
            or result["amount"] != {"currency": "NOK", "value": order["amount_ore"]}
        ):
            raise VippsError("Beløp eller referanse stemmer ikkje.")
        for key in (
            "authorizedAmount",
            "cancelledAmount",
            "capturedAmount",
            "refundedAmount",
        ):
            amount = result["aggregate"][key]
            if (
                amount.get("currency") != "NOK"
                or type(amount.get("value")) is not int
                or amount["value"] < 0
            ):
                raise VippsError("Ugyldig betalingsbeløp.")

    def finalize(self, reference, lease, user_details=None):
        with closing(self.db()) as db:
            db.execute("BEGIN IMMEDIATE")
            order = dict(
                db.execute(
                    "SELECT * FROM signup_orders WHERE reference=?", (reference,)
                ).fetchone()
            )
            if order["status"] == "complete" or order["lease_token"] != lease:
                return
            if order["environment"] == "test":
                db.execute(
                    "UPDATE signup_orders SET status='complete',problem='' WHERE reference=?",
                    (reference,),
                )
                db.commit()
                return
            if order.get('renewal_member_id'):
                from kontingent import member_paid
                member=db.execute('SELECT * FROM members WHERE id=? AND privacy_deleted=0',(order['renewal_member_id'],)).fetchone()
                if not member or member_paid(db,order['renewal_member_id'],order['for_year']):
                    db.execute("UPDATE signup_orders SET status='review',problem='Betalt fornying krev kontroll: medlem manglar eller året er betalt frå før.' WHERE reference=?",(reference,));db.commit();return
                stamp=datetime.now(timezone.utc).isoformat()
                pid=db.execute('INSERT INTO payments(member_id,amount_ore,paid_at,note,created_at,for_year) VALUES (?,?,?,?,?,?)',(member['id'],order['amount_ore'],stamp,'Vipps '+reference,stamp,order['for_year'])).lastrowid
                if order['for_year']==self.get_year(db):
                    kind=member['membership_type'] if member['membership_type'].strip().lower()=='styret' else ('kul' if order['amount_ore']>order['threshold_ore'] else 'vanleg')
                    db.execute("UPDATE members SET payment_status='betalt',membership_type=?,updated_at=? WHERE id=?",(kind,stamp,member['id']))
                db.execute("UPDATE signup_orders SET status='complete',member_id=?,payment_id=?,problem='' WHERE reference=?",(member['id'],pid,reference));db.commit();return
            data = json.loads(order["details"])
            if db.execute(
                "SELECT 1 FROM members WHERE lower(trim(email))=?", (order["email"],)
            ).fetchone():
                db.execute(
                    "UPDATE signup_orders SET status='review',problem='Betalt, men e-post finst i registeret. Må handterast av styret.' WHERE reference=?",
                    (reference,),
                )
                db.commit()
                return
            profile = user_details if isinstance(user_details, dict) else {}
            def clean_profile(key, maximum):
                value = profile.get(key, '')
                return value.strip() if isinstance(value, str) and len(value) <= maximum and not any(ord(c) < 32 for c in value) else ''
            payer_name = ' '.join(filter(None, (clean_profile('firstName', 200), clean_profile('lastName', 200))))
            payer_phone = clean_profile('mobileNumber', 30)
            db.execute("UPDATE signup_orders SET payer_name=?,payer_phone=? WHERE reference=?", (payer_name, payer_phone, reference))
            stamp = datetime.now(timezone.utc).isoformat()
            kind = "kul" if order["amount_ore"] > (order["threshold_ore"] if order["threshold_ore"] is not None else self.get_threshold(db)) else "vanleg"
            mid = db.execute(
                """INSERT INTO members(full_name,fornamn,mellomnamn,etternamn,email,phone,adresse,postnummer,poststad,birth_date,membership_type,payment_status,consent_at,created_at,updated_at)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    " ".join(
                        data[k]
                        for k in ("fornamn", "mellomnamn", "etternamn")
                        if data[k]
                    ),
                    *(data[k] for k in FIELDS),
                    kind,
                    "betalt"
                    if order["for_year"] == self.get_year(db)
                    else "ikkje betalt",
                    order["consent_at"],
                    stamp,
                    stamp,
                ),
            ).lastrowid
            pid = db.execute(
                "INSERT INTO payments(member_id,amount_ore,paid_at,note,created_at,for_year) VALUES (?,?,?,?,?,?)",
                (
                    mid,
                    order["amount_ore"],
                    stamp,
                    "Vipps " + reference,
                    stamp,
                    order["for_year"],
                ),
            ).lastrowid
            db.execute(
                "UPDATE signup_orders SET status='complete',member_id=?,payment_id=?,problem='' WHERE reference=?",
                (mid, pid, reference),
            )
            db.commit()

    def send_confirmation(self, reference):
        # Atomisk krav hindrar parallelle webhook/status-jobbar i å sende dobbelt.
        with closing(self.db()) as db:
            claimed = db.execute("UPDATE signup_orders SET confirmation_status='sending' WHERE reference=? AND environment='production' AND status='complete' AND confirmation_status='pending'", (reference,))
            db.commit()
            if claimed.rowcount != 1:
                return False
        order = self.order(reference)
        state = 'pending'
        try:
            if self.confirmation(order):
                state = 'sent'
        except DeliveryUncertain:
            state = 'review'
        except Exception:
            # Avvist SMTP eller feil før sending: reservejobben kan prøve igjen.
            state = 'pending'
        finally:
            with closing(self.db()) as db:
                db.execute("UPDATE signup_orders SET confirmation_status=? WHERE reference=? AND confirmation_status='sending'", (state, reference))
                db.commit()
        return state == 'sent'

    def sync_newsletter(self, reference):
        order = self.order(reference)
        if (
            not order
            or order["environment"] != "production"
            or order["status"] != "complete"
            or not order["newsletter"]
            or order["newsletter_done"]
        ):
            return False
        with closing(self.db()) as db:
            member = db.execute(
                "SELECT * FROM members WHERE id=?", (order["member_id"],)
            ).fetchone()
            if not member:
                return False
            member = dict(member)
        if self.newsletter(member):
            with closing(self.db()) as db:
                db.execute(
                    "UPDATE signup_orders SET newsletter_done=1 WHERE reference=?",
                    (reference,),
                )
                db.commit()
            return True
        return False


def webhook_valid(req, secret):
    try:
        stamp = req.headers["x-ms-date"]
        if abs(time.time() - parsedate_to_datetime(stamp).timestamp()) > 300:
            return False
        digest = base64.b64encode(hashlib.sha256(req.get_data()).digest()).decode()
        if not hmac.compare_digest(digest, req.headers.get("x-ms-content-sha256", "")):
            return False
        path = req.full_path.rstrip("?")
        signed = f"POST\n{path}\n{stamp};{req.host};{digest}"
        signature = base64.b64encode(
            hmac.new(secret.encode(), signed.encode(), hashlib.sha256).digest()
        ).decode()
        expected = (
            "HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256&Signature="
            + signature
        )
        return hmac.compare_digest(expected, req.headers.get("Authorization", ""))
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


def install_signup(
    app,
    get_db,
    get_year,
    get_threshold,
    newsletter,
    require_admin,
    privacy_maintenance=lambda: 0,
    confirmation=lambda order: False,
):
    service = SignupService(get_db, get_year, get_threshold, newsletter, confirmation)
    app.extensions["signup_service"] = service

    def sync_followups_safely(reference):
        service.send_confirmation(reference)
        # Brevo er uavhengig av bokføringa. Feil blir liggjande i den varige køen.
        try:
            return service.sync_newsletter(reference)
        except Exception:
            app.logger.error("Brevo-overføring feila. Innmeldinga ligg i kø for nytt forsøk.")
            return False

    def mode():
        selected = os.environ.get("VIPPS_SIGNUP_MODE", "disabled")
        if selected == "production-preview":
            if not app.extensions["styre_auth_valid"]():
                abort(
                    503,
                    "Nyinnmelding er snart klar. Kontakt folk@oslobygda.no i mellomtida.",
                )
            return "production"
        if selected not in ("test", "production"):
            abort(503, "Nyinnmelding med Vipps er ikkje opna enno.")
        return selected

    @app.route("/bli-medlem", methods=["GET", "POST"])
    def new_signup():
        environment = mode()
        key = session.setdefault("signup_key", secrets.token_urlsafe(32))
        values = {}
        error = None
        if request.method == "POST":
            values = request.form.to_dict()
            try:
                if values.get("website"):
                    raise ValueError("Ugyldig innsending.")
                reference = service.new(
                    values, key, environment, request.remote_addr or "unknown"
                )
                session["signup_reference"] = reference
                return redirect("/bli-medlem/status", code=303)
            except ValueError as exc:
                error = str(exc)
                app.logger.warning(
                    "Nyinnmelding: validering stoppa innsendinga (%s)", error
                )
        with closing(get_db()) as db:
            from kontingent import today, payable
            year=today().year
            try:
                policy=payable(db,year)
            except ValueError as exc:
                return render_template("kontingent_stengt.html",environment=environment,reason=str(exc)),200
            threshold=policy["superkul_ore"]
        return render_template(
            "ny_innmelding.html",
            values=values,
            error=error,
            environment=environment,
            year=year,
            threshold=threshold,
            minimum=policy["minimum_ore"],
        ), 400 if error else 200

    def owned():
        reference = session.get("signup_reference", "")
        order = service.order(reference)
        if not order or order["status"] == "redacted" or order["environment"] != mode():
            abort(404)
        if order.get('renewal_link_id'):
            with closing(get_db()) as db:
                link=db.execute('SELECT * FROM renewal_links WHERE id=? AND revoked=0',(order['renewal_link_id'],)).fetchone()
                if not link or session.get('renewal_link')!=link['id'] or session.get('renewal_digest')!=link['token_hash']:
                    abort(404)
        return order

    @app.route("/bli-medlem/status", methods=["GET", "POST"])
    def signup_status():
        order = owned()
        error = None
        if request.method == "POST":
            try:
                if request.form.get("action") == "pay":
                    origin = os.environ.get(
                        "VIPPS_PUBLIC_ORIGIN", "https://bygdelista.oslobygda.no"
                    ).rstrip("/")
                    return redirect(
                        service.create(
                            order["reference"], origin + "/bli-medlem/status"
                        ),
                        code=303,
                    )
                service.reconcile(order["reference"])
                sync_followups_safely(order["reference"])
            except VippsError as exc:
                error = str(exc)
            order = service.order(order["reference"])
        return render_template(
            "innmelding_status.html",
            order=order,
            error=error,
            environment=order["environment"],
        )

    @app.route("/bli-medlem/prov-igjen", methods=["POST"])
    def signup_restart():
        order = owned()
        if order["status"] not in ("ABORTED", "EXPIRED", "TERMINATED"):
            abort(409)
        session.pop("signup_reference", None)
        session["signup_key"] = secrets.token_urlsafe(32)
        return redirect("/forny" if order.get("renewal_member_id") else "/bli-medlem", code=303)

    @app.route("/vipps/webhook/<environment>", methods=["POST"])
    def signup_webhook(environment):
        if environment not in ("test", "production"):
            abort(404)
        secret = credentials(environment).get("VIPPS_WEBHOOK_SECRET", "")
        if not secret or not webhook_valid(request, secret):
            abort(401)
        payload = request.get_json(silent=True) or {}
        reference = payload.get("reference", "")
        order = service.order(reference) if isinstance(reference, str) else None
        if (
            order
            and order["environment"] == environment
            and str(payload.get("msn", "")) == order["msn"]
        ):
            try:
                service.reconcile(reference)
                sync_followups_safely(reference)
            except VippsError:
                return "", 503
        return "", 200

    @app.route("/innmeldingar")
    @require_admin
    def signup_overview():
        with closing(get_db()) as db:
            orders = [
                dict(row)
                for row in db.execute(
                    "SELECT reference,email,amount_ore,for_year,status,problem,newsletter,newsletter_done,environment,payer_name,payer_phone,confirmation_status FROM signup_orders WHERE overview_archived=0 ORDER BY created_at DESC LIMIT 100"
                )
            ]
        return render_template("innmeldingar.html", orders=orders)

    @app.cli.command("innmelding-testmodus")
    def test_mode():
        config = credentials("test")
        if not all(
            config.get(key)
            for key in (
                "VIPPS_CLIENT_ID",
                "VIPPS_CLIENT_SECRET",
                "VIPPS_SUBSCRIPTION_KEY",
                "VIPPS_MSN",
            )
        ):
            raise SystemExit("Legg inn testnøklar med konfigurer_vipps.py først.")
        env = Path(__file__).resolve().parent / ".env"
        env.touch(mode=0o600, exist_ok=True)
        env.chmod(0o600)
        set_key(env, "VIPPS_SIGNUP_MODE", "test")
        print(
            "Testmodus er valt. Produksjonsnøklane er bevarte. Trykk Web → Reload, og opne /bli-medlem."
        )

    @app.cli.command("innmelding-produksjonsprove")
    def production_preview():
        """Vel produksjonsprøve berre for innlogga styret. Ikkje opne offentleg."""
        client_for("production")  # Kontroller berre at alle verdiar er sette.
        env = Path(__file__).resolve().parent / ".env"
        env.touch(mode=0o600, exist_ok=True)
        env.chmod(0o600)
        set_key(env, "VIPPS_SIGNUP_MODE", "production-preview")
        print(
            "Produksjonsprøve er vald for innlogga styret. Registrer produksjonswebhook og trykk Web → Reload. Publikum får ikkje tilgang."
        )

    @app.cli.command("innmelding-webhook")
    def register_webhook():
        environment = os.environ.get("VIPPS_SIGNUP_MODE", "disabled")
        if environment == "production-preview":
            environment = "production"
        if environment not in ("test", "production"):
            raise SystemExit("Vel testmodus før webhook blir registrert.")
        config = credentials(environment)
        if config.get("VIPPS_WEBHOOK_SECRET"):
            print("Webhook er allereie sett opp. Ingen ny registrering utført.")
            return
        origin = os.environ.get(
            "VIPPS_PUBLIC_ORIGIN", "https://bygdelista.oslobygda.no"
        ).rstrip("/")
        result = client_for(environment)._authenticated(
            "POST",
            "/webhooks/v1/webhooks",
            {
                "url": origin + "/vipps/webhook/" + environment,
                "events": [
                    "epayments.payment." + event + ".v1"
                    for event in (
                        "authorized",
                        "captured",
                        "aborted",
                        "expired",
                        "terminated",
                        "cancelled",
                        "refunded",
                    )
                ],
            },
        )
        secret = result.get("secret", "")
        webhook_id = result.get("id", "")
        if (
            not isinstance(secret, str)
            or not secret
            or not isinstance(webhook_id, str)
            or not webhook_id
        ):
            raise SystemExit(
                "Kunne ikkje stadfeste webhook-oppsettet. Kontroller registreringa i Vipps-portalen før nytt forsøk."
            )
        env = Path(__file__).resolve().parent / (
            ".env.vipps-test" if environment == "test" else ".env"
        )
        env.touch(mode=0o600, exist_ok=True)
        env.chmod(0o600)
        set_key(env, "VIPPS_WEBHOOK_SECRET", secret)
        set_key(env, "VIPPS_WEBHOOK_ID", webhook_id)
        print(
            "Webhook registrert og løyndomen lagra. Trykk Web → Reload før du testar ei betaling."
        )

    @app.cli.command("innmelding-vedlikehald")
    def maintain():
        """Stadfest uferdige betalingar og prøv Brevo-køen på nytt."""
        with closing(get_db()) as db:
            refs = [
                r[0]
                for r in db.execute(
                    "SELECT reference FROM signup_orders WHERE status NOT IN ('complete','review','ABORTED','EXPIRED','TERMINATED','redacted') ORDER BY checked_at LIMIT 100"
                )
            ]
            news = [
                r[0]
                for r in db.execute(
                    "SELECT reference FROM signup_orders WHERE environment='production' AND status='complete' AND newsletter=1 AND newsletter_done=0 LIMIT 100"
                )
            ]
        with closing(get_db()) as db:
            confirmations = [row[0] for row in db.execute("SELECT reference FROM signup_orders WHERE environment='production' AND status='complete' AND confirmation_status='pending' LIMIT 100")]
        for ref in confirmations:
            service.send_confirmation(ref)
        privacy_done = privacy_maintenance()
        problems = 0
        for ref in refs:
            try:
                service.reconcile(ref)
                sync_followups_safely(ref)
            except (VippsError, ValueError):
                problems += 1
        for ref in news:
            sync_followups_safely(ref)
        print(
            f"Kontrollert {len(refs)} betalingar; {problems} må prøvast igjen. Handsama {len(news)} Brevo-oppføringar og {privacy_done} slettingar."
        )
