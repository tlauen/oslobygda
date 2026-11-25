"""Nummererte SQLite-migreringar under éin lås og éin transaksjon.

Registrerte migreringar er historikk: legg til nye steg, ikkje endre gamle.
Ingen appimport, nettverk eller automatisk nedgradering.
"""

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
from typing import Callable


class MigrationError(RuntimeError):
    pass


class MigrationConnection:
    """Lån eigaren sin transaksjon til historiske init-funksjonar.

    SQLite executescript() committar elles pågåande arbeid implisitt. Her blir
    heile SQL-setningar køyrde med execute(), inkludert fleirsetnings-triggerar.
    Dei gamle commit/close/context-kalla får ikkje avslutte eigaren sin transaksjon.
    """

    def __init__(self, connection):
        self._connection = connection

    @property
    def in_transaction(self):
        return self._connection.in_transaction

    def execute(self, sql, parameters=()):
        command = sql.strip().rstrip(";").upper()
        if command in (
            "BEGIN",
            "BEGIN TRANSACTION",
            "BEGIN IMMEDIATE",
            "BEGIN EXCLUSIVE",
        ):
            # Eldre initialiseringar tek òg skrivelås; eigaren har allereie teken henne.
            if self.in_transaction:
                return self._connection.execute("SELECT 1")
            raise MigrationError("Migreringa har mist den ytre transaksjonen.")
        if command in ("COMMIT", "END", "END TRANSACTION", "ROLLBACK"):
            raise MigrationError("Migreringar kan ikkje avslutte transaksjonen sjølve.")
        return self._connection.execute(sql, parameters)

    def executemany(self, sql, parameters):
        return self._connection.executemany(sql, parameters)

    def executescript(self, script):
        statement = ""
        for character in script:
            statement += character
            if character == ";" and sqlite3.complete_statement(statement):
                self.execute(statement)
                statement = ""
        if statement.strip():
            self.execute(statement)

    def commit(self):
        # Berre migreringskøyraren kan committe, etter at versjonen er registrert.
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[MigrationConnection], None]


def migrate(get_db, migrations):
    """Køyr berre manglande steg; feil rullar tilbake heile denne oppgraderinga.

    BEGIN IMMEDIATE serialiserer parallelle WSGI-oppstartar før historikken blir
    lesen. Skjemafeil og ukjende/endra versjonar stoppar oppstarten.
    """
    migrations = tuple(migrations)
    if [item.version for item in migrations] != list(range(1, len(migrations) + 1)):
        raise MigrationError(
            "Migreringane må ha stigande, samanhengande versjonar frå 1."
        )
    if any(not item.name for item in migrations) or len(
        {item.name for item in migrations}
    ) != len(migrations):
        raise MigrationError("Kvar migrering må ha eit unikt namn.")
    with closing(get_db()) as db:
        if db.in_transaction:
            raise MigrationError(
                "Migrering krev ei ny databasetilkopling utan transaksjon."
            )
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY CHECK(version>0),
                name TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL
            )""")
            history = [
                tuple(row)
                for row in db.execute(
                    "SELECT version,name FROM schema_migrations ORDER BY version"
                )
            ]
            expected = [(item.version, item.name) for item in migrations]
            if history != expected[: len(history)]:
                raise MigrationError(
                    "Ukjend, endra eller ufullstendig migreringshistorikk. Ikkje nedgrader databasen."
                )
            connection = MigrationConnection(db)
            applied = []
            for item in migrations[len(history) :]:
                # SQLite sin parser fangar òg transaksjonskommandoar etter kommentarar.
                # Dette hindrar utilsikta COMMIT via SQL i ein migreringscallback.
                db.set_authorizer(
                    lambda action, *_: (
                        sqlite3.SQLITE_DENY
                        if action == sqlite3.SQLITE_TRANSACTION
                        else sqlite3.SQLITE_OK
                    )
                )
                try:
                    item.apply(connection)
                finally:
                    db.set_authorizer(None)
                if not db.in_transaction:
                    raise MigrationError("Migreringa avslutta transaksjonen uventa.")
                db.execute(
                    "INSERT INTO schema_migrations VALUES (?,?,?)",
                    (item.version, item.name, datetime.now(timezone.utc).isoformat()),
                )
                applied.append(item.version)
            db.commit()
            return applied
        except BaseException:
            db.rollback()
            raise
