#!/usr/bin/env python3
"""Legg Vipps-nøklar i serveroppsettet utan terminalhistorikk eller betaling."""
from getpass import getpass, GetPassWarning
from pathlib import Path
import warnings

from dotenv import set_key
from vipps_client import VippsClient, VippsError


def main():
    environment=input('Miljø (test eller production): ').strip()
    if environment not in ('test','production'):
        raise SystemExit('Skriv test eller production. Ingenting lagra.')
    fields=(('VIPPS_CLIENT_ID','Client ID'),('VIPPS_CLIENT_SECRET','Client secret'),
            ('VIPPS_SUBSCRIPTION_KEY','Subscription key (primary)'),('VIPPS_MSN','Merchant Serial Number (MSN)'))
    values={}
    # Stopp dersom terminalen ikkje kan skjule innskrivinga.
    with warnings.catch_warnings():
        warnings.simplefilter('error',GetPassWarning)
        try:
            for key,label in fields:
                value=getpass(label+' (skjult): ').strip()
                if not value or any(c.isspace() or ord(c)<32 for c in value):
                    raise SystemExit('Tom eller ugyldig verdi. Ingenting lagra.')
                values[key]=value
        except Warning:
            raise SystemExit('Terminalen kan ikkje skjule innskrivinga. Bruk ein Bash-konsoll. Ingenting lagra.') from None
    client=VippsClient(*(values[key] for key,_ in fields),environment=environment)
    try:
        response=client._request('POST','/accesstoken/get',{**client.headers,**client.credentials})
        if not isinstance(response,dict) or not isinstance(response.get('access_token'),str) or not response['access_token']:
            raise VippsError('Ugyldig autentiseringssvar frå Vipps.')
    except VippsError as error:
        raise SystemExit(str(error)+' Ingenting lagra.') from None
    env=Path(__file__).resolve().parent/('.env.vipps-test' if environment=='test' else '.env')
    env.touch(mode=0o600,exist_ok=True)
    env.chmod(0o600)
    for key,value in {**values,'VIPPS_ENVIRONMENT':environment}.items():
        set_key(env,key,value)
    env.chmod(0o600)
    print(f'Autentisering hos Vipps fungerer. Nøklane er lagra i {env.name} med filrettar 600.')
    print('Ingen betaling er oppretta eller trekt. Innmeldingsintegrasjonen er ikkje aktivert.')


if __name__=='__main__':
    main()
