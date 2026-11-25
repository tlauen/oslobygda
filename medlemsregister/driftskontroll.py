"""Les produksjonsstatus utan å importere appen, migrere eller skrive i databasen.

Rapporten inneheld berre teljingar, pakkeversjonar og kontrollresultat, aldri
namn, kontaktdata, token, TOTP-løyndomar eller innhaldet i jobbloggar.
"""
import argparse
from contextlib import closing
from importlib.metadata import version, PackageNotFoundError
import json
from pathlib import Path
import re
import sqlite3

from cryptography.fernet import Fernet
from dotenv import dotenv_values
from betalingsstatus import Ordrestatus, Vippsstatus


def inspect(app_dir, log_dir=Path('/var/log')):
    app_dir = Path(app_dir).resolve()
    env = dotenv_values(app_dir / '.env')
    result = {'vipps_mode': env.get('VIPPS_SIGNUP_MODE', 'disabled')}
    key = env.get('MEDLEMSREGISTER_TOTP_KEY', '')
    box = Fernet(key.encode('ascii')) if key else None
    result['totp_key_present'] = bool(box)
    database = (app_dir / 'medlemsregister.db').as_uri() + '?mode=ro'
    with closing(sqlite3.connect(database, uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        result['database_integrity_ok'] = db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        result['schema_version'] = 0
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone():
            result['schema_version'] = db.execute('SELECT COALESCE(MAX(version),0) FROM schema_migrations').fetchone()[0]
        result['totp'] = {}
        for table in ('board_users', 'board_enrollment'):
            values = [row[0] for row in db.execute(f'SELECT totp_secret FROM {table}')]
            encrypted = readable = 0
            for value in values:
                if value.startswith('enc:v1:'):
                    encrypted += 1
                    if box:
                        try:
                            box.decrypt(value[len('enc:v1:'):].encode('ascii'))
                            readable += 1
                        except Exception:
                            pass  # Berre tal i rapporten, aldri løyndomar eller feildetaljar.
            result['totp'][table] = {'total': len(values), 'encrypted': encrypted, 'readable': readable}
        for table in ('members', 'payments'):
            result[table + '_count'] = db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        # Berre kjende statusar blir skrivne ut; uventa databaseinnhald blir ikkje logga.
        known = {*Ordrestatus, *Vippsstatus}
        result['orders'] = []
        for environment, status, count in db.execute('SELECT environment,status,COUNT(*) FROM signup_orders GROUP BY environment,status'):
            result['orders'].append({'environment': environment if environment in ('production', 'test') else 'unknown',
                                     'status': status if status in known else 'unknown', 'count': count})
    result['jobs'] = {}
    for label, number in (('maintenance', 28463), ('backup', 28111), ('proton', 28824)):
        path = Path(log_dir) / f'schedule-log-{number}.log'
        if not path.is_file():
            result['jobs'][label] = {'log_present': False}
            continue
        # Ikkje skriv ut meldingane frå vedlikehaldet; dei kan innehalde persondata.
        completed = re.findall(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) -- Completed task, took [0-9.]+ seconds, return code was (\d+)\.', path.read_text(errors='replace'))
        result['jobs'][label] = {'log_present': True, 'last_completed_utc': completed[-1][0] if completed else None,
                                 'return_code': int(completed[-1][1]) if completed else None}
    result['packages'] = {}
    lock = Path(__file__).with_name('requirements-lock.txt')
    for line in lock.read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        package, expected = line.split('==')
        try:
            installed = version(package)
        except PackageNotFoundError:
            installed = None
        result['packages'][package] = {'installed': installed, 'expected': expected, 'matches': installed == expected}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-dir', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    try:
        result = inspect(args.app_dir)
    except Exception as error:
        # Unngå at databaseinnhald eller miljøverdiar hamnar i ein traceback.
        print(json.dumps({'error_type': type(error).__name__, 'message': 'Driftskontrollen kunne ikkje fullførast.'}))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
