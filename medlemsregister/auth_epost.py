"""Varig, kryptert kø for eingongskodar. HTTP-ruter sender aldri SMTP.

Køyr `flask --app app auth-epost --loop` som eigen arbeidar. Ein jobb blir teken
berre éin gong, også ved uvisst leveringsutfall. Brukaren kan be om ny kode.
"""

import base64
import hashlib
import json
import time

import click
from cryptography.fernet import Fernet
from database import managed_db


def init_queue(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS auth_mail_jobs (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
            expires REAL NOT NULL, state TEXT NOT NULL DEFAULT 'pending'
        );
        CREATE TABLE IF NOT EXISTS signup_email_codes (
            reference TEXT PRIMARY KEY REFERENCES signup_orders(reference),
            email TEXT NOT NULL, code_hash TEXT NOT NULL, expires REAL NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0
        );
    """)


class AuthMail:
    def __init__(self, app, get_db):
        self.app, self.db = app, get_db

    def cipher(self):
        secret = self.app.secret_key
        if isinstance(secret, str):
            secret = secret.encode()
        return Fernet(
            base64.urlsafe_b64encode(hashlib.sha256(b"auth-mail-v1:" + secret).digest())
        )

    def enqueue(self, db, identifier, kind, email, code, expires):
        payload = (
            self.cipher()
            .encrypt(json.dumps(dict(email=email, code=code)).encode())
            .decode()
        )
        db.execute(
            "INSERT OR REPLACE INTO auth_mail_jobs(id,kind,payload,expires) VALUES (?,?,?,?)",
            (identifier, kind, payload, expires),
        )

    def valid(self, db, job, email):
        if job["kind"] == "member":
            return db.execute(
                """SELECT 1 FROM member_challenges c JOIN members m ON m.id=c.member_id
                JOIN member_access a ON a.member_id=m.id WHERE c.id=? AND c.purpose='login'
                AND c.expires>? AND c.attempts<5 AND c.version=a.version AND m.privacy_deleted=0
                AND lower(trim(m.email))=? AND c.email=?""",
                (job["id"], time.time(), email, email),
            ).fetchone()
        if job["kind"] == "board":
            from styre_registrering import board_member

            row = db.execute(
                "SELECT * FROM board_enrollment WHERE id=? AND expires>? AND verified=0 AND attempts<5",
                (job["id"], time.time()),
            ).fetchone()
            member = board_member(db, email)
            return (
                row
                and member
                and row["email"] == email
                and row["member_id"] == member["id"]
            )
        if job["kind"] == "reset":
            from styre_registrering import eligible_account

            row = db.execute(
                "SELECT * FROM board_password_reset WHERE id=? AND expires>? AND attempts<5",
                (job["id"], time.time()),
            ).fetchone()
            user = db.execute(
                "SELECT * FROM board_users WHERE username=? AND active=1", (email,)
            ).fetchone()
            return (
                row
                and user
                and row["username"] == email
                and row["session_version"] == user["session_version"]
                and eligible_account(user, db)
            )
        if job["kind"] == "signup":
            return db.execute(
                """SELECT 1 FROM signup_email_codes c JOIN signup_orders o ON o.reference=c.reference
                WHERE c.reference=? AND c.expires>? AND c.attempts<5 AND c.email=? AND o.email=?
                AND o.status='new' AND o.create_attempted=0""",
                (job["id"], time.time(), email, email),
            ).fetchone()
        return False

    def process(self, limit=100):
        with managed_db(self.db) as db:
            db.execute("DELETE FROM auth_mail_jobs WHERE expires<=?", (time.time(),))
            db.execute(
                "DELETE FROM signup_email_codes WHERE expires<=?", (time.time(),)
            )
            jobs = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM auth_mail_jobs WHERE state='pending' ORDER BY expires LIMIT ?",
                    (limit,),
                )
            ]
        sent = 0
        for job in jobs:
            with managed_db(self.db) as db:
                db.execute("BEGIN IMMEDIATE")
                if not db.execute(
                    "UPDATE auth_mail_jobs SET state='sending' WHERE id=? AND state='pending' AND payload=?",
                    (job["id"], job["payload"]),
                ).rowcount:
                    continue
                try:
                    payload = json.loads(self.cipher().decrypt(job["payload"].encode()))
                    valid = self.valid(db, job, payload["email"])
                except Exception:
                    valid = False
            try:
                if valid:
                    if job["kind"] in ("member", "signup"):
                        from medlem_auth import send_code

                        send_code(
                            payload["email"],
                            payload["code"],
                            "login" if job["kind"] == "member" else "signup",
                        )
                    else:
                        from styre_registrering import send_code

                        if job["kind"] == "reset":
                            from passord_reset import send_code
                        send_code(
                            payload["email"],
                            payload["code"],
                            password_reset=job["kind"] == "reset",
                        )
                    sent += 1
            except Exception:
                self.app.logger.warning(
                    "Sending av eingongskode kunne ikkje stadfestast. Be om ny kode."
                )
                with managed_db(self.db) as db:
                    table = {
                        "member": "member_challenges",
                        "board": "board_enrollment",
                        "reset": "board_password_reset",
                        "signup": "signup_email_codes",
                    }[job["kind"]]
                    key = "reference" if job["kind"] == "signup" else "id"
                    db.execute(f"DELETE FROM {table} WHERE {key}=?", (job["id"],))
            finally:
                with managed_db(self.db) as db:
                    db.execute(
                        "DELETE FROM auth_mail_jobs WHERE id=? AND payload=?",
                        (job["id"], job["payload"]),
                    )
        return sent


def install_auth_mail(app, get_db, initialize_db):
    worker = AuthMail(app, get_db)
    app.extensions["auth_mail"] = worker

    @app.cli.command("auth-epost")
    @click.option(
        "--loop", "forever", is_flag=True, help="Køyr kontinuerleg som eigen arbeidar."
    )
    def dispatch(forever):
        initialize_db()
        click.echo("Kodearbeidaren er klar. Ingen adresser eller kodar blir logga.")
        while True:
            worker.process()
            if not forever:
                break
            time.sleep(1)
