#!/usr/bin/env python3
"""Køyr dagleg; send ein fast testmelding via Brevo høgst kvar 30. dag."""
from email.message import EmailMessage
import fcntl
import json
import os
from pathlib import Path
import smtplib
import ssl
import tempfile
import time

from dotenv import load_dotenv

SUBJECT = '[BYGDELISTA-SMTP-KEEPALIVE] Automatisk e-posttest'
RECIPIENT = 'folk@oslobygda.no'
INTERVAL = 30 * 24 * 60 * 60


def send_test():
    if os.environ.get('SMTP_HOST', '').strip().lower() != 'smtp-relay.brevo.com':
        raise ValueError('Brevo SMTP er ikkje konfigurert.')
    if os.environ.get('STYRE_EPOST_FRA', '').strip().lower() != 'ikkjesvar@oslobygda.no':
        raise ValueError('Avsendar må vere ikkjesvar@oslobygda.no.')
    if not os.environ.get('SMTP_USER') or not os.environ.get('SMTP_PASSWORD'):
        raise ValueError('SMTP-brukarnamn eller SMTP-nøkkel manglar.')
    port = int(os.environ.get('SMTP_PORT', '465'))
    if port not in (465, 587):
        raise ValueError('Bruk port 465 eller 587.')
    message = EmailMessage()
    message['From'] = 'ikkjesvar@oslobygda.no'
    message['To'] = RECIPIENT
    message['Subject'] = SUBJECT
    message['Auto-Submitted'] = 'auto-generated'
    message['X-Bygdelista-Message-Type'] = 'smtp-keepalive'
    message.set_content('''Dette er ein automatisk e-posttest frå Bygdelista.

Meldinga vert send kvar 30. dag for å teste utsendinga og halde Brevo sin
SMTP-nøkkel aktiv. Ho inneheld ingen medlemsdata og kan slettast automatisk.
Du treng ikkje svare.
''')
    context = ssl.create_default_context()
    if port == 465:
        smtp = smtplib.SMTP_SSL('smtp-relay.brevo.com', port, context=context, timeout=20)
    else:
        smtp = smtplib.SMTP('smtp-relay.brevo.com', port, timeout=20)
    with smtp:
        if port == 587:
            smtp.starttls(context=context)
        smtp.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
        if smtp.send_message(message):
            raise RuntimeError('Mottakaren vart ikkje godteken.')


def run(directory, now=None):
    now = int(time.time()) if now is None else now
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    state = directory / 'smtp-keepalive.json'
    lock = directory / 'smtp-keepalive.lock'
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        if state.exists():
            last_sent = json.loads(state.read_text())['last_sent']
            if last_sent > now:
                raise ValueError('Lagra sendetid ligg i framtida. Kontroller klokka.')
            if now - last_sent < INTERVAL:
                return False
        send_test()
        # Berre vellukka innsending til SMTP-tenaren vert registrert.
        fd, path = tempfile.mkstemp(prefix='.smtp-state-', dir=directory)
        temporary = Path(path)
        try:
            with os.fdopen(fd, 'w') as out:
                json.dump({'last_sent':now},out)
            temporary.replace(state)
        finally:
            temporary.unlink(missing_ok=True)
        return True


def main():
    load_dotenv(Path(__file__).resolve().parent / '.env')
    try:
        sent = run(Path.home() / '.bygdelista')
    except Exception as error:
        # Leverandørmelding kan innehalde adresser. Vis berre feilklasse og statuskode.
        status = getattr(error, 'smtp_code', None)
        raise SystemExit(f'SMTP-test feila: {type(error).__name__}; SMTP-status={status}. Kontroller Brevo-oppsettet.') from None
    print('SMTP-test godteken av Brevo.' if sent else 'Ikkje tid for ny SMTP-test enno.')


if __name__ == '__main__':
    main()
