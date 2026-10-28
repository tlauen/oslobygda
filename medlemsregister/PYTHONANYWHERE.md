# Bygdelista på PythonAnywhere EU

Konto: `oslobygda` på <https://eu.pythonanywhere.com/>.
Planlagt adresse: `https://bygdelista.oslobygda.no`.

Innlogging brukar personlege styrekontoar med passord og autentiseringsapp
(TOTP). Vipps Login er ikkje nødvendig. Vent med ekte medlemsdata til HTTPS,
kontotilgang og backup med testa gjenoppretting er på plass.

## Filer og Python-miljø

Legg prosjektet i `/home/oslobygda/oslobygda`. Bruk berre kodefilene frå Git;
ikkje last opp lokal `.env` eller medlemsdatabasen som del av koden.

Footer-malen kjem direkte frå `_tillegg/kolofon.html`, og footer-CSS frå
`lutar/kolofon.css`; menyen blir lesen frå `_data/nav.yml`. Desse må vere med på serveren, i tillegg til
`medlemsregister/`. Flask leverer CSS-en på `/felles/kolofon.css`; den vanlege
`/fast/`-koplinga skal stå uendra. Det finst ingen eigne footer-kopiar i appen.

I Bash-konsollen, med ein Python-versjon som òg er tilgjengeleg i Web-fana:

```bash
cd /home/oslobygda/oslobygda/medlemsregister
python3 -m venv /home/oslobygda/.virtualenvs/bygdelista
/home/oslobygda/.virtualenvs/bygdelista/bin/pip install -r requirements-pythonanywhere.txt
```

Dette oppsettet brukar vanleg SQLite. Det opnar ikkje ein eksisterande
SQLCipher-kryptert database. Eventuell flytting av medlemsdata må gjerast
separat, med tryggingskopi og kontroll av kryptering først.

## Hemmelege verdiar

Opprett `medlemsregister/.env` på serveren, med filrettar berre for eigaren
(`chmod 600 .env`). Set ein lang tilfeldig `MEDLEMSREGISTER_SECRET_KEY`.
Aktiver det virtuelle miljøet og generer verdien på serveren:

```bash
source /home/oslobygda/.virtualenvs/bygdelista/bin/activate
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Ikkje legg hemmelege verdiar i Git eller lim dei inn i chatten.
Sjå [STYREKONTOAR.md](STYREKONTOAR.md) for oppretting av første konto.
Det gamle fellespassordet og `MEDLEMSREGISTER_PASSWORD_HASH` gir ikkje lenger tilgang.

## Web-oppsett (når appen er klar for publisering)

1. Opprett éin app med **Manual configuration** i Web-fana, for
   `bygdelista.oslobygda.no`. Vel same Python-versjon som i miljøet.
2. Set virtualenv til `/home/oslobygda/.virtualenvs/bygdelista`.
3. Erstatt innhaldet i WSGI-konfigurasjonsfila med:

   ```python
   import sys
   sys.path.insert(0, "/home/oslobygda/oslobygda/medlemsregister")
   from wsgi import application
   ```

4. Legg til statisk filkopling frå `/fast/` til
   `/home/oslobygda/oslobygda/medlemsregister/fast`.
   Ikkje eksponer sjølve medlemsregister-mappa som statiske filer.
5. Opprett ein CNAME for `bygdelista` hos DNS-leverandøren. Bruk nøyaktig
   målverdi som PythonAnywhere viser i Web-fana, ikkje gjett adressa.
6. Aktiver HTTPS-sertifikat og **Force HTTPS**, og last appen på nytt.

WSGI-inngangen initialiserer databasen og krev eigne løyndomar.
Han set sikre økt-informasjonskapslar og slår av debug.

## Backup før ordinær bruk

Følg [BACKUP.md](BACKUP.md) for `backup.py`, dagleg oppgåve og prøve av
gjenoppretting. Kopiar utanfor PythonAnywhere er førebels ein manuell rutine.

## Dokumentasjon

- <https://help.pythonanywhere.com/pages/Flask/>
- <https://help.pythonanywhere.com/pages/CustomDomains/>
- <https://help.pythonanywhere.com/pages/HTTPSSetup/>
