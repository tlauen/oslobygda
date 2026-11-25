"""Brevo-transport, nyhendebrevkontaktar og vedlikehald av personvernslettingar.

Ingen appimport; kontaktar og databaseopnar blir sende inn eksplisitt.
"""

import json
import os
import ssl
import time
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from database import managed_db
from personvern import process_privacy_jobs

try:
    import certifi

    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = None


def brevo_request(
    method: str, path: str, api_key: str, body: dict | None = None
) -> tuple[int, dict]:
    url = f"https://api.brevo.com/v3/{path.lstrip('/')}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(
        url,
        data=data,
        headers={
            "api-key": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method=method.upper(),
    )
    try:
        with urlopen(req, timeout=20, context=_SSL_CTX) as res:
            payload = res.read().decode().strip()
            return res.status, (json.loads(payload) if payload else {})
    except HTTPError as e:
        raw = e.read().decode().strip()
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"message": raw or str(e)}
        return e.code, parsed
    except (URLError, OSError) as e:
        return 0, {"message": str(e)}


class BrevoContacts:
    def __init__(self, get_db, logger, request=brevo_request):
        self.get_db = get_db
        self.logger = logger
        self.request = request

    def signup(self, member):
        # Berre nødvendige kontaktfelt vert overførte. Aldri nullstill avmeldingsstatus.
        key = os.environ.get("BREVO_API_KEY", "").strip()
        list_id = os.environ.get("BREVO_INNMELDING_LIST_ID") or os.environ.get(
            "BREVO_LIST_ID", ""
        )
        if not key or not str(list_id).isdigit():
            return False
        status, _ = self.request(
            "POST",
            "/contacts",
            key,
            {
                "email": member["email"],
                "attributes": {
                    "FIRSTNAME": member["fornamn"],
                    "LASTNAME": member["etternamn"],
                },
                "listIds": [int(list_id)],
                "updateEnabled": True,
            },
        )
        return status in (200, 201, 204)

    def delete_contact(self, email):
        key = os.environ.get("BREVO_API_KEY", "").strip()
        if not key:
            return False
        status, _ = self.request("DELETE", "/contacts/" + quote(email, safe=""), key)
        return status in (204, 404)

    def maintenance(self):
        # Lesekontroll kvar 30. dag held òg API-nøkkelen i bruk når det er få innmeldingar.
        key = os.environ.get("BREVO_API_KEY", "").strip()
        list_id = os.environ.get("BREVO_INNMELDING_LIST_ID") or os.environ.get(
            "BREVO_LIST_ID", ""
        )
        now = int(time.time())
        if key and str(list_id).isdigit():
            with managed_db(self.get_db) as db:
                row = db.execute(
                    "SELECT value FROM app_settings WHERE key='brevo_api_last_check'"
                ).fetchone()
            if not row or now - int(row[0]) >= 30 * 86400:
                status, _ = self.request(
                    "GET", "/contacts/lists/" + str(int(list_id)), key
                )
                if status == 200:
                    with managed_db(self.get_db) as db:
                        db.execute(
                            "INSERT INTO app_settings(key,value) VALUES ('brevo_api_last_check',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                            (str(now),),
                        )
                else:
                    self.logger.warning(
                        "Brevo API-kontroll feila. Kontroller tilgang og listeoppsett."
                    )
        return process_privacy_jobs(self.get_db, self.delete_contact)
