#!/usr/bin/env python3
"""Sjekk om SQLCipher er tilgjengeleg slik at MEDLEMSREGISTER_DB_KEY kan brukast."""
import sys
import os
from pathlib import Path

# Last .env
APP_DIR = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(APP_DIR / ".env")
except ImportError:
    pass

key = os.environ.get("MEDLEMSREGISTER_DB_KEY", "").strip()
print("MEDLEMSREGISTER_DB_KEY:", "satt" if key else "ikkje satt")

try:
    import sqlcipher3.dbapi2 as sqlcipher3
    print("sqlcipher3: OK – kryptering er tilgjengeleg")
    if key:
        print("→ Ved neste start av app.py vert databasen kryptert (eller migrert til kryptert).")
    sys.exit(0)
except ImportError as e:
    print("sqlcipher3: FEIL –", e)
    print()
    print("For å aktivere kryptering:")
    print("  1. Installer libsqlcipher:  brew install sqlcipher")
    print("  2. Installer Python-pakken: pip install sqlcipher3")
    print("  3. Start appen på nytt (python3 app.py)")
    sys.exit(1)
