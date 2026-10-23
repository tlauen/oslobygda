"""ePayment-klient. Ikkje kopla til offentlege ruter før komplett flyt er testa."""
import json
import os
import re
import ssl
import time
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, HTTPSHandler, build_opener

import certifi


class VippsError(RuntimeError):
    """Vis aldri leverandørrespons, token eller nøkkel i brukarfeil/loggar."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def amount_ore(text):
    if not isinstance(text, str) or not re.fullmatch(r'\d{1,7}([.,]\d{1,2})?', text.strip()):
        raise ValueError('Skriv beløpet med høgst to desimalar.')
    try:
        value = Decimal(text.strip().replace(',', '.')) * 100
    except InvalidOperation:
        raise ValueError('Ugyldig beløp.') from None
    if not 100 <= value <= 100000000:
        raise ValueError('Beløpet må vere mellom 1 og 1 000 000 kroner.')
    return int(value)


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
            error.close()
            raise VippsError(f'Vipps svarte med HTTP {status}.') from None
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
        if type(ore) is not int or not 100 <= ore <= 100000000:
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
        if type(ore) is not int or not 100 <= ore <= 100000000 or not idempotency_key:
            raise ValueError('Ugyldig beløp eller manglande idempotensnøkkel.')
        return self._authenticated('POST','/epayment/v1/payments/'+reference+'/capture',
                                   {'modificationAmount':{'currency':'NOK','value':ore}},idempotency_key)
