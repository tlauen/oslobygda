"""Stadfest eigarskap til e-post før medlemsstatus eller betaling blir avklart."""

import hashlib
import hmac
import secrets
import time
from database import managed_db


def digest(app, reference, email, code):
    key = app.secret_key.encode() if isinstance(app.secret_key, str) else app.secret_key
    return hmac.new(
        key,
        ("signup-email:" + reference + ":" + email + ":" + code).encode(),
        hashlib.sha256,
    ).hexdigest()


def issue(app, get_db, order):
    with managed_db(get_db) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM signup_email_codes WHERE reference=?", (order["reference"],)
        ).fetchone()
        if row and row["email"] == order["email"] and row["expires"] > time.time():
            return
        # Same adressegrense uavhengig av medlemskap og nettlesar. Eit generisk
        # HTTP-svar røper heller ikkje om ein annan nettlesar har bede om kode.
        bucket = "signup-code:" + digest(app, "limit", order["email"], "")
        db.execute("DELETE FROM signup_limits WHERE expires<=?", (time.time(),))
        limit = db.execute(
            "SELECT count FROM signup_limits WHERE bucket=?", (bucket,)
        ).fetchone()
        if limit and limit[0] >= 3:
            return
        db.execute(
            "INSERT INTO signup_limits VALUES (?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1",
            (bucket, time.time() + 900),
        )
        code = f"{secrets.randbelow(100000000):08d}"
        expires = time.time() + 600
        db.execute(
            "INSERT OR REPLACE INTO signup_email_codes(reference,email,code_hash,expires) VALUES (?,?,?,?)",
            (
                order["reference"],
                order["email"],
                digest(app, order["reference"], order["email"], code),
                expires,
            ),
        )
        app.extensions["auth_mail"].enqueue(
            db, order["reference"], "signup", order["email"], code, expires
        )


def verify(app, get_db, order, code):
    with managed_db(get_db) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM signup_email_codes WHERE reference=?", (order["reference"],)
        ).fetchone()
        if (
            not row
            or row["email"] != order["email"]
            or row["expires"] <= time.time()
            or row["attempts"] >= 5
        ):
            return False
        db.execute(
            "UPDATE signup_email_codes SET attempts=attempts+1 WHERE reference=?",
            (order["reference"],),
        )
        if (
            not isinstance(code, str)
            or len(code) != 8
            or not code.isascii()
            or not code.isdigit()
            or not hmac.compare_digest(
                row["code_hash"], digest(app, order["reference"], order["email"], code)
            )
        ):
            return False
        db.execute(
            "DELETE FROM signup_email_codes WHERE reference=?", (order["reference"],)
        )
        db.execute("DELETE FROM auth_mail_jobs WHERE id=?", (order["reference"],))
        return True
