"""Lukk databasekoplingar eksplisitt etter transaksjonen."""

from contextlib import contextmanager


@contextmanager
def managed_db(get_db):
    connection = get_db()
    try:
        with connection:
            yield connection
    finally:
        connection.close()
