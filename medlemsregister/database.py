"""Felles transaksjons- og livsløpshandtering for appdatabasen."""

from contextlib import contextmanager


@contextmanager
def managed_db(get_db, *, commit_on_success=True):
    """Lukk alltid; rull tilbake ved feil eller uferdig manuelt arbeid.

    Standardmodus bruker driveren sin transaksjonskontekst: commit ved normal
    retur, rollback ved feil (òg feil under commit). Betalingsflytar med eigne
    varige kontrollpunkt bruker commit_on_success=False: berre eksplisitte
    commit-kall blir lagra, og attverande arbeid blir rulla tilbake før lukking.
    """
    connection = get_db()
    try:
        if commit_on_success:
            with connection:
                yield connection
        else:
            try:
                yield connection
            finally:
                if connection.in_transaction:
                    connection.rollback()
    finally:
        connection.close()
