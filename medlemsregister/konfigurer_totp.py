"""Opprett ein separat TOTP-nøkkel i eksisterande .env, utan å vise henne."""
from pathlib import Path
from cryptography.fernet import Fernet
from dotenv import dotenv_values, set_key


def main():
    env = Path(__file__).resolve().parent / '.env'
    if not env.is_file() or env.is_symlink():
        raise SystemExit('Krev eksisterande, vanleg .env-fil i medlemsregister-mappa.')
    existing = dotenv_values(env).get('MEDLEMSREGISTER_TOTP_KEY')
    if existing:
        Fernet(existing.encode('ascii'))
        print('TOTP-nøkkelen finst frå før. Han er ikkje endra.')
        return
    env.chmod(0o600)
    set_key(env, 'MEDLEMSREGISTER_TOTP_KEY', Fernet.generate_key().decode('ascii'))
    print('Separat TOTP-nøkkel er lagra i .env. Ikkje lim henne inn i chat eller loggar.')
    print('Bevar nøkkelen separat i laget sin passordhandterar før Reload. Sjå PERSONVERN-DRIFT.md.')


if __name__ == '__main__':
    main()
