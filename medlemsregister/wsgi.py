"""WSGI-inngang for PythonAnywhere. Sjå PYTHONANYWHERE.md før publisering."""
import os
from werkzeug.middleware.proxy_fix import ProxyFix
from totp_kryptering import cipher

if os.environ.get('BYGDELISTA_LOCAL_TEST') == '1':
    raise RuntimeError('Lokal testmodus skal ikkje brukast i produksjons-WSGI.')

from app import app as application, init_db


if not os.environ.get("MEDLEMSREGISTER_SECRET_KEY") or application.secret_key == "endre-meg-i-produksjon":
    raise RuntimeError("Set MEDLEMSREGISTER_SECRET_KEY i .env før publisering.")
if os.environ.get("MEDLEMSREGISTER_DB_KEY"):
    raise RuntimeError("SQLCipher må setjast opp og verifiserast særskilt før publisering.")
if cipher() is None:
    raise RuntimeError("Set separat MEDLEMSREGISTER_TOTP_KEY før publisering. Sjå PERSONVERN-DRIFT.md.")

# PythonAnywhere garanterer berre siste X-Forwarded-For-verdi.
# Ikkje stol på andre proxy-headerar eller bruk denne wrapperen lokalt.
application.wsgi_app = ProxyFix(application.wsgi_app, x_for=1, x_proto=0)

application.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    DEBUG=False,
)
init_db()
