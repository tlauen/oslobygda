#!/usr/bin/env python3
"""Konsistent SQLite-backup og prøve av gjenoppretting. Køyr med --help."""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
from datetime import datetime, timezone


def connect_readonly(path):
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)


def check_database(db):
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise RuntimeError('Integritetskontrollen feila.')
    if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise RuntimeError('Databasen inneheld ugyldige referansar.')
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'members', 'payments', 'board_users'}.issubset(tables):
        raise RuntimeError('Fila manglar tabellar for Bygdelista.')


def verify_restore(path):
    """Gjenopprett i ei mellombels database; rør aldri den aktive databasen."""
    with tempfile.TemporaryDirectory(prefix='bygdelista-restore-') as folder:
        restored = Path(folder) / 'restored.db'
        with closing(connect_readonly(path)) as source, closing(sqlite3.connect(restored)) as dest:
            source.backup(dest)
            check_database(dest)
        restored.chmod(0o600)


def create_backup(source, directory, keep=30):
    if keep < 1:
        raise ValueError('Minst éin backup må behaldast.')
    if not source.is_file():
        raise FileNotFoundError('Kjeldedatabasen finst ikkje.')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%M%S-%fZ')
    destination = directory / f'medlemsregister-{stamp}.db'
    fd, name = tempfile.mkstemp(prefix='.backup-', dir=directory)
    os.close(fd)
    temporary = Path(name)
    try:
        with closing(connect_readonly(source)) as src, closing(sqlite3.connect(temporary)) as dest:
            src.backup(dest)
            dest.execute("PRAGMA journal_mode=DELETE")
            check_database(dest)
        verify_restore(temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    # Roter berre våre eigne, ferdige filer etter at ny backup er verifisert.
    backups = sorted(directory.glob('medlemsregister-????-??-??T??????-??????Z.db'), reverse=True)
    for old in backups[keep:]:
        old.unlink()
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=Path(__file__).resolve().parent / 'medlemsregister.db')
    parser.add_argument('--directory', type=Path, default=Path.home() / 'Bygdelista-backup')
    parser.add_argument('--keep', type=int, default=30)
    parser.add_argument('--bilag-dir', type=Path, default=Path(os.environ.get('BYGDELISTA_BILAG_DIR', str(Path.home() / 'bygdelista-data' / 'bilag'))), help='Privat bilagsmappe for samla økonomibackup.')
    parser.add_argument('--verify', type=Path, help='Prøv gjenoppretting av denne backupfila utan å endre aktiv database.')
    args = parser.parse_args()
    if args.verify:
        if args.verify.is_dir():
            from okonomi_backup import verify_bundle_restore
            verify_bundle_restore(args.verify)
        else:
            verify_restore(args.verify)
        print('Gjenoppretting i mellombels database og integritetskontroll: OK.')
    else:
        with closing(connect_readonly(args.db)) as source:
            has_ledger = source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ledger_receipts'").fetchone()
        if has_ledger:
            from okonomi_backup import create_bundle
            result = create_bundle(args.db, args.bilag_dir, args.directory, args.keep,include_board=True)
        else:
            result = create_backup(args.db, args.directory, args.keep)
        print(f'Backup og prøve av gjenoppretting: OK. Fil: {result}')


if __name__ == '__main__':
    main()
