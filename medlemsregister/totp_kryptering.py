"""Krypter TOTP-felt med ein separat nøkkel; ingen automatisk nøkkelgenerering."""

import os
from cryptography.fernet import Fernet, InvalidToken

PREFIX = "enc:v1:"


def cipher():
    key = os.environ.get("MEDLEMSREGISTER_TOTP_KEY", "").strip()
    if not key:
        return None  # Berre lokal utvikling/eldre data; produksjons-WSGI krev nøkkel.
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeError):
        raise RuntimeError("MEDLEMSREGISTER_TOTP_KEY er ikkje ein gyldig Fernet-nøkkel.") from None


def reveal(value):
    box = cipher()
    if value.startswith(PREFIX):
        if box is None:
            raise RuntimeError("TOTP-nøkkelen manglar. Gjenopprett den eksisterande nøkkelen.")
        try:
            return box.decrypt(value[len(PREFIX):].encode("ascii")).decode("ascii")
        except (InvalidToken, UnicodeError, ValueError):
            raise RuntimeError("TOTP-feltet kan ikkje dekrypterast med den konfigurerte nøkkelen.") from None
    if box is not None:
        raise RuntimeError("TOTP-felt må migrerast før bruk.")
    return value


def protect(value):
    box = cipher()
    if value.startswith(PREFIX):
        reveal(value)  # Oppdag feil nøkkel før noko blir lagra.
        return value
    return PREFIX + box.encrypt(value.encode("ascii")).decode("ascii") if box else value


def migrate(db):
    """Kall inne i éin transaksjon. Valider alle felt før oppstart held fram."""
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')
    for table, identifier in (("board_users", "username"), ("board_enrollment", "id")):
        for row in db.execute(f"SELECT {identifier},totp_secret FROM {table}").fetchall():
            encrypted = protect(row[1])
            if encrypted != row[1]:
                db.execute(f"UPDATE {table} SET totp_secret=? WHERE {identifier}=?", (encrypted, row[0]))
