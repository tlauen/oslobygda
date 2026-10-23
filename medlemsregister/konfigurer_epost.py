#!/usr/bin/env python3
"""Konfigurer SMTP interaktivt på serveren. Hemmelege verdiar vert ikkje skrivne ut."""
from getpass import getpass
from pathlib import Path
import smtplib
import ssl

from dotenv import set_key


def main():
    host = input('SMTP-server (Brevo: smtp-relay.brevo.com): ').strip()
    port = int(input('Port (587 for STARTTLS, 465 for SSL) [587]: ').strip() or '587')
    username = input('SMTP-brukarnamn (Brevo: Login frå SMTP-fana): ').strip()
    sender = input('Avsendaradresse (t.d. ikkjesvar@oslobygda.no): ').strip()
    password = getpass('SMTP-passord (Brevo: SMTP key, ikkje API key): ')
    if not all((host, username, sender, password)) or port not in (587, 465) or '@' not in sender:
        raise SystemExit('Ufullstendige innstillingar. Ingenting vart lagra.')
    context = ssl.create_default_context()
    try:
        if port == 465:
            smtp = smtplib.SMTP_SSL(host, port, context=context, timeout=15)
        else:
            smtp = smtplib.SMTP(host, port, timeout=15)
        with smtp:
            if port == 587:
                smtp.starttls(context=context)
            smtp.login(username, password)
    except Exception:
        raise SystemExit('SMTP-innlogginga feila. Kontroller server, brukarnamn og passord. Ingenting vart lagra.') from None
    env = Path(__file__).resolve().parent / '.env'
    env.touch(mode=0o600, exist_ok=True)
    env.chmod(0o600)
    for key, value in {'SMTP_HOST':host, 'SMTP_PORT':str(port), 'SMTP_USER':username,
                       'SMTP_PASSWORD':password, 'STYRE_EPOST_FRA':sender}.items():
        set_key(env, key, value)
    env.chmod(0o600)
    print('SMTP-innlogging godkjend. Innstillingane er lagra. Last webappen på nytt i Web-fana.')
    print('Ingen e-post er send. Prøv kontoregistrering for å kontrollere levering.')


if __name__ == '__main__':
    main()
