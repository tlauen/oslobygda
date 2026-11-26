"""Driftstilstand for kontrollert økonomiimport; nettverk skjer utan skrivelås."""

import json
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from arsdokument import canonical, digest, stamp
from database import managed_db


def fingerprint(value):
    return digest(canonical(value))


def migrate_finance(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS payment_checks (
      payment_id INTEGER PRIMARY KEY,evidence_id INTEGER NOT NULL,checked_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS payment_attempts (
      payment_id INTEGER PRIMARY KEY,attempted_at TEXT NOT NULL,next_at TEXT NOT NULL,
      failures INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL,message TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS finance_locks (name TEXT PRIMARY KEY,token TEXT NOT NULL,expires TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS finance_runs (
      id INTEGER PRIMARY KEY,kind TEXT NOT NULL,started_at TEXT NOT NULL,finished_at TEXT,
      counts TEXT NOT NULL DEFAULT '{}',error TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS finance_previews (
      token TEXT PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL,expires TEXT NOT NULL,
      created_by TEXT NOT NULL,applied_at TEXT,result TEXT NOT NULL DEFAULT '{}'
    );
    CREATE TABLE IF NOT EXISTS vipps_report_entries (
      identity TEXT PRIMARY KEY,msn TEXT NOT NULL,kind TEXT NOT NULL,reference TEXT NOT NULL,
      psp_reference TEXT NOT NULL,day TEXT NOT NULL,amount_ore INTEGER NOT NULL,
      payload TEXT NOT NULL,content_hash TEXT NOT NULL,created_at TEXT NOT NULL,
      journal_id INTEGER REFERENCES ledger_journals(id),resolution TEXT NOT NULL DEFAULT '',
      note TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS vipps_bank_confirmations (
      identity TEXT PRIMARY KEY REFERENCES vipps_report_entries(identity),day TEXT NOT NULL,
      amount_ore INTEGER NOT NULL,bank_reference TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS vipps_report_cursors (
      ledger TEXT PRIMARY KEY,cursor TEXT,updated_at TEXT NOT NULL
    );
    """)

    db.executescript("""
    CREATE TRIGGER IF NOT EXISTS vipps_report_source_fixed BEFORE UPDATE OF identity,msn,kind,reference,psp_reference,day,amount_ore,payload,content_hash ON vipps_report_entries
    BEGIN SELECT RAISE(ABORT,'Rapportkjelda kan ikkje endrast'); END;
    CREATE TRIGGER IF NOT EXISTS finance_preview_fixed BEFORE UPDATE OF kind,payload,expires,created_by ON finance_previews
    BEGIN SELECT RAISE(ABORT,'Kontrollgrunnlaget kan ikkje endrast'); END;
    CREATE TRIGGER IF NOT EXISTS bank_confirmation_fixed BEFORE UPDATE ON vipps_bank_confirmations
    BEGIN SELECT RAISE(ABORT,'Bankgrunnlaget kan ikkje endrast'); END;
    """)


@contextmanager
def finance_lock(get_db, name, minutes=20):
    token = secrets.token_hex(16)
    with managed_db(get_db) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM finance_locks WHERE expires<?", (stamp(),))
        old = db.execute("SELECT 1 FROM finance_locks WHERE name=?", (name,)).fetchone()
        if old:
            raise ValueError(
                "Ein kontroll køyrer allereie. Prøv igjen når han er ferdig."
            )
        db.execute(
            "INSERT INTO finance_locks VALUES (?,?,?)",
            (
                name,
                token,
                (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat(),
            ),
        )

    def renew():
        with managed_db(get_db) as db:
            result = db.execute(
                "UPDATE finance_locks SET expires=? WHERE name=? AND token=?",
                (
                    (
                        datetime.now(timezone.utc) + timedelta(minutes=minutes)
                    ).isoformat(),
                    name,
                    token,
                ),
            )
            if result.rowcount != 1:
                raise ValueError(
                    "Kontrolljobben har mist låsen. Start kontrollen på nytt."
                )

    try:
        yield renew
    finally:
        with managed_db(get_db) as db:
            db.execute(
                "DELETE FROM finance_locks WHERE name=? AND token=?", (name, token)
            )


def attempt(db, pid, status, message=""):
    old = db.execute(
        "SELECT failures FROM payment_attempts WHERE payment_id=?", (pid,)
    ).fetchone()
    failures = (old[0] + 1 if old else 1) if status == "error" else 0
    seconds = (
        min(86400, 300 * 2 ** min(failures - 1, 8))
        if failures
        else (86400 if status in ("booked", "historical") else 300)
    )
    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO payment_attempts VALUES (?,?,?,?,?,?) ON CONFLICT(payment_id) DO UPDATE SET attempted_at=excluded.attempted_at,next_at=excluded.next_at,failures=excluded.failures,status=excluded.status,message=excluded.message",
        (
            pid,
            now.isoformat(),
            (now + timedelta(seconds=seconds)).isoformat(),
            failures,
            status,
            message[:500],
        ),
    )


def save_preview(db, kind, payload, actor):
    raw = canonical(payload)
    old = db.execute(
        "SELECT token FROM finance_previews WHERE kind=? AND payload=? AND created_by=? AND applied_at IS NULL AND expires>? ORDER BY expires DESC LIMIT 1",
        (kind, raw, actor, stamp()),
    ).fetchone()
    if old:
        return old[0]
    token = secrets.token_urlsafe(24)
    db.execute(
        "INSERT INTO finance_previews(token,kind,payload,expires,created_by) VALUES (?,?,?,?,?)",
        (
            token,
            kind,
            raw,
            (datetime.now(timezone.utc) + timedelta(minutes=50)).isoformat(),
            actor,
        ),
    )
    return token


def load_preview(db, token, kind):
    row = db.execute(
        "SELECT * FROM finance_previews WHERE token=? AND kind=?", (token, kind)
    ).fetchone()
    if not row:
        raise ValueError("Førehandsvisinga finst ikkje. Kontroller kjelda på nytt.")
    if row["applied_at"]:
        return row, json.loads(row["payload"])
    if row["expires"] < stamp():
        raise ValueError("Førehandsvisinga er utgått. Kontroller kjelda på nytt.")
    return row, json.loads(row["payload"])
