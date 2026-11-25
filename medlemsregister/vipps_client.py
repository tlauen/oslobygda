"""ePayment-klient. Ikkje kopla til offentlege ruter før komplett flyt er testa."""

from betalingsreglar import vipps_amount_ore as amount_ore, valid_vipps_ore
import json
import os
import re
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, HTTPSHandler, build_opener

import certifi


class VippsError(RuntimeError):
    """Vis aldri leverandørrespons, token eller nøkkel i brukarfeil/loggar."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class VippsClient:
    def __init__(self, client_id, client_secret, subscription_key, msn, environment='test'):
        if environment not in ('test', 'production'):
            raise ValueError('Vel test eller production uttrykkeleg.')
        if not all((client_id,client_secret,subscription_key,msn)):
            raise ValueError('Vipps API-innstillingar manglar.')
        self.base = 'https://apitest.vipps.no' if environment == 'test' else 'https://api.vipps.no'
        self.credentials = {'client_id':client_id,'client_secret':client_secret}
        self.headers = {'Ocp-Apim-Subscription-Key':subscription_key, 'Merchant-Serial-Number':msn,
                        'Vipps-System-Name':'bygdelista', 'Vipps-System-Version':'1.0.0',
                        'Content-Type':'application/json'}
        self.token = None
        self.expires = 0
        context = ssl.create_default_context(cafile=certifi.where())
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=context))

    @classmethod
    def from_environment(cls):
        return cls(*(os.environ.get(key,'').strip() for key in
                     ('VIPPS_CLIENT_ID','VIPPS_CLIENT_SECRET','VIPPS_SUBSCRIPTION_KEY','VIPPS_MSN')),
                   environment=os.environ.get('VIPPS_ENVIRONMENT','test'))

    def _request(self, method, path, headers, body=None):
        data = json.dumps(body).encode() if body is not None else (b'' if method=='POST' else None)
        req = Request(self.base+path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req,timeout=20) as response:
                return json.loads(response.read())
        except HTTPError as error:
            status = error.code
            detail=''
            try:
                payload=json.loads(error.read(65536))
                message=json.dumps(payload,ensure_ascii=True)
                lowered=message.lower()
                # Berre faste lokale tekstar vert viste, aldri leverandørresponsen.
                if status==401 and isinstance(message,str):
                    lowered=message.lower()
                    if 'invalid subscription key' in lowered or 'subscription not found' in lowered:
                        detail=' Vipps avviser Subscription key. Kontroller primary/secondary-nøkkelen for rett miljø og salseining.'
                    elif 'missing subscription key' in lowered:
                        detail=' Vipps melder at Subscription key manglar i førespurnaden.'
                    elif 'invalid client' in lowered or 'invalid_client' in lowered or 'invalid credentials' in lowered:
                        detail=' Vipps avviser innloggingsopplysningane. Kontroller Client ID og Client secret.'
                if status==400:
                    if 'aadsts7000215' in lowered or 'invalid_client' in lowered or 'invalid client secret' in lowered:
                        detail=' Autentiseringa vart avvist: kontroller Client ID og den nye Client secret-verdien (ikkje ein Secret ID).'
                    elif 'aadsts700016' in lowered:
                        detail=' Autentiseringa fann ikkje klienten. Kontroller Client ID og miljø.'
                    elif 'aadsts7000222' in lowered:
                        detail=' Autentiseringa melder at Client secret er utgått.'
                    elif 'client_secret' in lowered or 'client_id' in lowered:
                        detail=' Feilsvaret viser til Client ID eller Client secret.'
                    elif 'merchant-serial-number' in lowered:
                        detail=' Feilsvaret viser til Merchant Serial Number (MSN).'
                    elif 'subscription' in lowered:
                        detail=' Feilsvaret viser til Subscription key.'
                    else:
                        detail=' Vipps avviste formatet eller innhaldet i autentiseringsførespurnaden.'
                    codes=sorted(set(re.findall(r'AADSTS[0-9]{4,10}',message,re.IGNORECASE)))
                    if codes:
                        detail+=' Feilkode: '+', '.join(code.upper() for code in codes)+'.'
            except (ValueError,OSError):
                pass
            finally:
                error.close()
            raise VippsError(f'Vipps svarte med HTTP {status}.'+detail) from None
        except (URLError, OSError, ValueError):
            raise VippsError('Kunne ikkje stadfeste svaret frå Vipps. Kontroller status før nytt forsøk.') from None

    def _authenticated(self, method, path, body=None, key=None):
        if self.token is None or time.time() >= self.expires:
            response = self._request('POST','/accesstoken/get', {**self.headers,**self.credentials})
            try:
                self.token = response['access_token']
                self.expires = time.time()+int(response['expires_in'])-60
                if not isinstance(self.token,str) or not self.token:
                    raise ValueError()
            except (KeyError, TypeError, ValueError):
                self.token = None
                raise VippsError('Ugyldig autentiseringssvar frå Vipps.') from None
        headers={**self.headers,'Authorization':'Bearer '+self.token}
        if key:
            headers['Idempotency-Key']=key
        return self._request(method,path,headers,body)

    @staticmethod
    def _reference(reference):
        if not re.fullmatch(r'[A-Za-z0-9-]{8,50}',reference):
            raise ValueError('Ugyldig betalingsreferanse.')
        return reference

    def create(self, reference, ore, return_url, idempotency_key):
        self._reference(reference)
        if not valid_vipps_ore(ore):
            raise ValueError('Ugyldig beløp i øre.')
        parts=urlsplit(return_url)
        if parts.scheme!='https' or not parts.hostname or parts.username or parts.password:
            raise ValueError('Returadressa må vere ei HTTPS-adresse.')
        if not idempotency_key:
            raise ValueError('Ein lagra idempotensnøkkel er påkravd.')
        return self._authenticated('POST','/epayment/v1/payments',{
            'amount':{'currency':'NOK','value':ore},'paymentMethod':{'type':'WALLET'},
            'reference':reference,'userFlow':'WEB_REDIRECT','returnUrl':return_url,
            'paymentDescription':'Medlemskontingent Oslobygda kulturlag'},idempotency_key)

    def get(self, reference):
        return self._authenticated('GET','/epayment/v1/payments/'+self._reference(reference))

    def capture(self, reference, ore, idempotency_key):
        self._reference(reference)
        if not valid_vipps_ore(ore) or not idempotency_key:
            raise ValueError('Ugyldig beløp eller manglande idempotensnøkkel.')
        return self._authenticated('POST','/epayment/v1/payments/'+reference+'/capture',
                                   {'modificationAmount':{'currency':'NOK','value':ore}},idempotency_key)


    def events(self, reference):
        """Les hendingslogg; ingen betalingssideeffektar."""
        return self._authenticated('GET','/epayment/v1/payments/'+self._reference(reference)+'/events')
