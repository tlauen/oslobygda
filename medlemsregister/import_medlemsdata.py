#!/usr/bin/env python3
"""Importer medlemsdata atomisk i eit tomt register. Ta backup først."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3

TABLES = ('members', 'payments', 'app_settings', 'medlemsar_arkiv')


def import_data(source, destination):
    if not source.is_file() or not destination.is_file() or source.resolve() == destination.resolve():
        raise ValueError('Kjelde og mål må finnast og vere ulike filer.')
    with closing(sqlite3.connect(destination.resolve().as_uri() + '?mode=rw', uri=True)) as db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('ATTACH DATABASE ? AS incoming', (source.resolve().as_uri() + '?mode=ro',))
        for schema in ('main', 'incoming'):
            if db.execute(f'PRAGMA {schema}.integrity_check').fetchall() != [('ok',)]:
                raise ValueError('Integritetskontrollen feila.')
            if db.execute(f'PRAGMA {schema}.foreign_key_check').fetchall():
                raise ValueError('Databasen inneheld ugyldige referansar.')
        db.execute('BEGIN IMMEDIATE')
        try:
            for table in ('members', 'payments', 'medlemsar_arkiv'):
                if db.execute(f'SELECT COUNT(*) FROM main."{table}"').fetchone()[0]:
                    raise ValueError('Målregisteret er ikkje tomt. Importen er stoppa.')
            layouts = {}
            for table in TABLES:
                src = [r[1] for r in db.execute(f'PRAGMA incoming.table_info("{table}")')]
                dst = [r[1] for r in db.execute(f'PRAGMA main.table_info("{table}")')]
                if not src or set(src) != set(dst):
                    raise ValueError('Ulike databaseskjema for ' + table)
                layouts[table] = ','.join('"' + c.replace('"', '""') + '"' for c in dst)
            accounts = db.execute('SELECT * FROM board_users ORDER BY username').fetchall()
            if db.execute('SELECT key FROM incoming.app_settings').fetchall() != [('medlemsbetalingsar',)]:
                raise ValueError('Uventa kjeldeinnstillingar.')
            if any(key != 'medlemsbetalingsar' for (key,) in db.execute('SELECT key FROM main.app_settings')):
                raise ValueError('Uventa målinnstillingar.')
            db.execute('DELETE FROM main.app_settings')
            counts = {}
            for table in TABLES:
                cols = layouts[table]
                db.execute(f'INSERT INTO main."{table}" ({cols}) SELECT {cols} FROM incoming."{table}"')
                src = db.execute(f'SELECT {cols} FROM incoming."{table}" ORDER BY 1').fetchall()
                dst = db.execute(f'SELECT {cols} FROM main."{table}" ORDER BY 1').fetchall()
                if src != dst:
                    raise RuntimeError('Kontroll av importerte rader feila.')
                counts[table] = len(dst)
            if accounts != db.execute('SELECT * FROM board_users ORDER BY username').fetchall():
                raise RuntimeError('Styrekontoane vart endra.')
            if db.execute('PRAGMA main.foreign_key_check').fetchall():
                raise RuntimeError('Referansekontrollen feila.')
            db.commit()
            return counts
        except BaseException:
            db.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--db', type=Path, default=Path(__file__).resolve().parent / 'medlemsregister.db')
    args = parser.parse_args()
    for table, count in import_data(args.source, args.db).items():
        print(f'{table}: {count} rader kontrollerte')
    print('Import fullført. Styrekontoane er uendra.')


if __name__ == '__main__':
    main()
