"""Transaksjonsmail for stadfesta medlemskap, uavhengig av nyhendebrev."""
import os
from email.message import EmailMessage
from email.utils import formatdate
from epost import send_message
from styre_registrering import mail_ready


def send_confirmation(order):
    if not mail_ready():
        return False
    message = EmailMessage()
    message['From'] = os.environ['STYRE_EPOST_FRA']
    message['To'] = order['email']
    message['Reply-To'] = 'folk@oslobygda.no'
    message['Subject'] = f"Velkomen i Oslobygda – medlemskap for {order['for_year']}"
    message['Date'] = formatdate(localtime=False, usegmt=True)
    message['Message-ID'] = f"<innmelding-{order['reference']}@oslobygda.no>"
    amount = f"{order['amount_ore'] // 100},{order['amount_ore'] % 100:02d}"
    message.set_content(f"""Velkomen i Oslobygda kulturlag!

Medlemskapen din for {order['for_year']} er registrert, og betalinga er stadfesta.

Betalt med Vipps: {amount} kr
Betalingsreferanse: {order['reference']}
Medlemskapen gjeld kalenderåret {order['for_year']}.

Sjå komande tilskipingar: https://oslobygda.no/kalender/

Du har 14 dagars angrerett. Vilkår: https://oslobygda.no/salsvilkar/
Ved spørsmål, retting eller ønske om refusjon kan du svare på denne e-posten.
Oppgi gjerne betalingsreferansen, og ikkje send kort- eller BankID-opplysningar.

Helsing Oslobygda kulturlag
folk@oslobygda.no
""")
    send_message(message)
    return True
