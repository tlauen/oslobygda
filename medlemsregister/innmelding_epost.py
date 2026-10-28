"""Transaksjonsmail for stadfesta medlemskap, uavhengig av nyhendebrev."""
import json
from email.message import EmailMessage
from email.utils import formatdate
from html import escape

from epost import send_message
from styre_registrering import mail_ready


def send_confirmation(order):
    if not mail_ready():
        return False
    message = EmailMessage()
    message['From'] = 'Oslobygda kulturlag <folk@oslobygda.no>'
    message['To'] = order['email']
    message['Reply-To'] = 'folk@oslobygda.no'
    message['Subject'] = 'No er du med i Oslobygda! 🎉'
    message['Date'] = formatdate(localtime=False, usegmt=True)
    message['Message-ID'] = f"<innmelding-{order['reference']}@oslobygda.no>"
    amount = f"{order['amount_ore'] // 100},{order['amount_ore'] % 100:02d}"
    details = json.loads(order.get('details') or '{}')
    name = details.get('fornamn', '').strip()
    greeting = f'Hei, {name}!' if name else 'Hei!'
    year = str(order['for_year'])
    reference = order['reference']
    message.set_content(f"""{greeting}

Så kjekt at du vil vere med i Oslobygda! No er medlemskapen din for {year} i boks, og me har fått dei {amount} kronene du betalte med Vipps. Tusen takk for bidraget!

Me gler oss til å sjå deg – anten du vil spele, danse eller berre drikke noko godt og preike skit. Du treng ikkje kunne ein einaste springar for å kjenne deg heime hjå oss.

Her ser du kva du kan glede deg til →
https://oslobygda.no/kalender/

Har du spørsmål eller noko på hjartet? Berre svar på denne e-posten, så høyrer du frå oss.

Me sjåast på pøbb!

Helsing oss i Oslobygda kulturlag
Frilynt · folkeleg · litt for seint heim

---

Medlemskapen gjeld kalenderåret {year}. Betalingsreferansen din er {reference}.

Du har 14 dagars angrerett. Om du angrar, svar på denne e-posten, så hjelper me deg. Her finn du salsvilkåra:
https://oslobygda.no/salsvilkar/
""")
    message.add_alternative(f"""<!doctype html>
<html lang="nn"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#fcf9f3;color:#12110e;font:16px/1.7 system-ui,-apple-system,Segoe UI,sans-serif">
<div style="max-width:580px;margin:0 auto;padding:32px 24px">
<p>{escape(greeting)}</p>
<p>Så kjekt at du vil vere med i Oslobygda! No er medlemskapen din for {escape(year)} i boks, og me har fått dei <strong>{escape(amount)} kronene</strong> du betalte med Vipps. Tusen takk for bidraget!</p>
<p>Me gler oss til å sjå deg – anten du vil spele, danse eller berre drikke noko godt og preike skit. Du treng ikkje kunne ein einaste springar for å kjenne deg heime hjå oss.</p>
<p><a href="https://oslobygda.no/kalender/" style="color:#206582">Her ser du kva du kan glede deg til →</a></p>
<p>Har du spørsmål eller noko på hjartet? Berre svar på denne e-posten, så høyrer du frå oss.</p>
<p>Me sjåast på pøbb!</p>
<p>Helsing oss i Oslobygda kulturlag<br><em>Frilynt · folkeleg · litt for seint heim</em></p>
<hr style="border:0;border-top:1px solid #dedcd4;margin:28px 0">
<div style="font-size:13px;color:#5e5c55">
<p>Medlemskapen gjeld kalenderåret {escape(year)}. Betalingsreferansen din er {escape(reference)}.</p>
<p>Du har 14 dagars angrerett. Om du angrar, svar på denne e-posten, så hjelper me deg. <a href="https://oslobygda.no/salsvilkar/" style="color:#206582">Her finn du salsvilkåra.</a></p>
</div></div></body></html>
""", subtype='html')
    send_message(message)
    return True
