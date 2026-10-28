"""Slett persondata, men bevar anonyme beløp for rekneskapsavstemming."""

from datetime import datetime, timezone
import time
from database import managed_db


def init_privacy(get_db):
    with managed_db(get_db) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(members)")}
        if "privacy_deleted" not in columns:
            db.execute(
                "ALTER TABLE members ADD COLUMN privacy_deleted INTEGER NOT NULL DEFAULT 0"
            )
        db.execute("""CREATE TABLE IF NOT EXISTS privacy_jobs (
            email TEXT PRIMARY KEY, created_at REAL NOT NULL
        )""")


def erase_member(db, mid):
    row = db.execute(
        "SELECT * FROM members WHERE id=? AND privacy_deleted=0", (mid,)
    ).fetchone()
    if not row:
        return {"error": "Medlem finst ikkje"}, 404
    email = row["email"].strip().casefold()
    orders = db.execute(
        "SELECT reference,email,status,environment FROM signup_orders WHERE member_id=? OR (email<>? AND lower(trim(email))=?)",
        (mid, "", email),
    ).fetchall()
    if any(
        o["environment"] == "production"
        and o["status"]
        not in ("complete", "ABORTED", "EXPIRED", "TERMINATED", "redacted")
        for o in orders
    ):
        return {
            "error": "Medlemmen har ei pågåande betaling eller ei betaling til kontroll. Avklar denne før sletting."
        }, 409
    addresses = {email} | {o["email"].strip().casefold() for o in orders if o["email"]}
    for address in addresses:
        if address:
            db.execute(
                "INSERT OR IGNORE INTO privacy_jobs(email,created_at) VALUES (?,?)",
                (address, time.time()),
            )
    db.execute("DELETE FROM board_password_reset WHERE username=? OR username IN (SELECT username FROM board_users WHERE member_id=?)", (email, mid))
    db.execute("DELETE FROM board_users WHERE member_id=? OR username=?", (mid, email))
    db.execute(
        "DELETE FROM board_enrollment WHERE member_id=? OR lower(trim(email))=?",
        (mid, email),
    )
    for order in orders:
        db.execute(
            "UPDATE signup_orders SET details='{}',email='',browser_key='',consent_at='',status='redacted',newsletter=0,newsletter_done=1,member_id=NULL,lease_token=NULL,lease_until=0,problem='' WHERE reference=?",
            (order["reference"],),
        )
    if db.execute("SELECT 1 FROM payments WHERE member_id=?", (mid,)).fetchone():
        # Bevar summane, åra og referansane, men ikkje fritekst som kan innehalde namn.
        db.execute(
            "UPDATE payments SET note=COALESCE((SELECT 'Vipps '||reference FROM signup_orders WHERE payment_id=payments.id),'Anonymisert betalingspost') WHERE member_id=?",
            (mid,),
        )
        db.execute(
            """UPDATE members SET full_name='Sletta medlem',fornamn='',mellomnamn='',etternamn='',
            email='',phone='',adresse='',postnummer='',poststad='',birth_date=NULL,
            membership_type='vanleg',consent_at='',privacy_deleted=1,updated_at=? WHERE id=?""",
            (datetime.now(timezone.utc).isoformat(), mid),
        )
    else:
        db.execute("DELETE FROM members WHERE id=?", (mid,))
    return {
        "message": "Medlemsopplysningane og eventuell styretilgang er sletta lokalt. Bokførte beløp er bevarte utan kontaktopplysningar. Sletting hos Brevo står i kø."
    }, 200


def process_privacy_jobs(get_db, delete_contact):
    with managed_db(get_db) as db:
        emails = [
            row[0]
            for row in db.execute(
                "SELECT email FROM privacy_jobs ORDER BY created_at LIMIT 100"
            )
        ]
    done = 0
    for email in emails:
        if delete_contact(email):
            with managed_db(get_db) as db:
                db.execute("DELETE FROM privacy_jobs WHERE email=?", (email,))
            done += 1
    return done
