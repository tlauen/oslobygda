#!/usr/bin/env python3
"""Kontroller Brevo-tilgang utan å opprette kontaktar eller sende e-post."""
from getpass import getpass, GetPassWarning
from pathlib import Path
import warnings
from dotenv import set_key
from app import _brevo_request


def main():
    with warnings.catch_warnings():
        warnings.simplefilter('error',GetPassWarning)
        try:
            key=getpass('Brevo API-nøkkel (skjult, ikkje SMTP-nøkkel): ').strip()
        except GetPassWarning:
            raise SystemExit('Bruk ein terminal som støttar skjult innskriving. Ingenting lagra.') from None
    if not key or any(c.isspace() or ord(c)<32 for c in key):
        raise SystemExit('Tom eller ugyldig nøkkel. Ingenting lagra.')
    status,payload=_brevo_request('GET','/contacts/lists?limit=50&offset=0',key)
    if status!=200:
        raise SystemExit(f'Brevo avviste listekontrollen (HTTP {status}). Ingenting lagra.')
    print('Tilgjengelege lister (viser høgst 50):')
    for item in payload.get('lists',[]):
        print(f"  {item.get('id')}: {item.get('name')}")
    list_id=input('Liste-ID for medlemmar som vel nyhendebrev: ').strip()
    if not list_id.isdigit():
        raise SystemExit('Liste-ID må vere eit heiltal. Ingenting lagra.')
    status,_=_brevo_request('GET','/contacts/lists/'+str(int(list_id)),key)
    if status!=200:
        raise SystemExit(f'Brevo kunne ikkje stadfeste lista (HTTP {status}). Ingenting lagra.')
    env=Path(__file__).resolve().parent/'.env'
    env.touch(mode=0o600,exist_ok=True);env.chmod(0o600)
    set_key(env,'BREVO_API_KEY',key)
    set_key(env,'BREVO_INNMELDING_LIST_ID',str(int(list_id)))
    env.chmod(0o600)
    print('Brevo API-tilgang og liste er kontrollerte. Oppsettet er lagra med filrettar 600.')
    print('Ingen kontakt er oppretta og ingen e-post er send. Trykk Web → Reload.')


if __name__=='__main__':
    main()
