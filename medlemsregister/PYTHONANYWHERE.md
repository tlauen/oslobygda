# Bygdelista på PythonAnywhere EU

Konto: `oslobygda` på <https://eu.pythonanywhere.com/>.
Adresse: `https://bygdelista.oslobygda.no`.

Innlogging brukar personlege styrekontoar med passord og autentiseringsapp
(TOTP). Vipps Login er ikkje nødvendig. Vent med ekte medlemsdata til HTTPS,
kontotilgang og backup med testa gjenoppretting er på plass.

## Filer og Python-miljø

Legg prosjektet i `/home/oslobygda/oslobygda`. Bruk berre kodefilene frå Git;
ikkje last opp lokal `.env` eller medlemsdatabasen som del av koden.

Footer-malen kjem direkte frå `_tillegg/kolofon.html`, og footer-CSS frå
`lutar/kolofon.css` og `lutar/topp.css`; menyen blir lesen frå `_data/nav.yml`. Desse må vere med på serveren, i tillegg til
`medlemsregister/`. Årsmøte-/økonomisidene krev òg `_data/rekneskapskategoriar.json`. Flask leverer CSS-en på `/felles/kolofon.css`; den vanlege
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

## Fast oppdateringsrutine

PythonAnywhere har ei eiga, rein Git-kjelde i `/home/oslobygda/oslobygda-kjelde`.
Den aktive appen ligg framleis i `/home/oslobygda/oslobygda`; ikkje rediger filer
direkte i nokon av desse mappene. Rediger lokalt og push til `main` først.

Etter at du har committa og pusha, køyr dette i PythonAnywhere sin Bash-konsoll:

```bash
python3 /home/oslobygda/oppdater-bygdelista.py
```

Gå så til **Web → Reload bygdelista.oslobygda.no**, og last nettsida på nytt.
GitHub Pages publiserer hovudnettsida automatisk; denne kommandoen oppdaterer
Python-appen på PythonAnywhere.

Kommandoen hentar `main`, sjekkar Python-syntaks, tek kodebackup og kopierer
berre godkjende kodefiler, malar og nødvendige felles footer-/menyfiler.
`.env`, Vipps-testnøklar, databasar og byggjemapper blir ikkje kopierte.
Ingen medlemsregistrering, betaling eller e-postsending blir starta.

Du kan sjå om det er kode å oppdatere utan å endre den aktive appen:

```bash
python3 /home/oslobygda/oppdater-bygdelista.py --dry-run
```

Når oppdateringsskriptet sjølv er endra (til dømes for å ta med felles
header-CSS), oppdater serverkopien etter første køyring og køyr på nytt før Reload:

```bash
cp /home/oslobygda/oslobygda-kjelde/skript/oppdater_bygdelista.py /home/oslobygda/oppdater-bygdelista.py
python3 /home/oslobygda/oppdater-bygdelista.py
```

Ved endringar i `requirements-common.txt` eller `requirements-pythonanywhere.txt`,
køyr òg før Reload:

```bash
/home/oslobygda/.virtualenvs/bygdelista/bin/pip install -r /home/oslobygda/oslobygda/medlemsregister/requirements-pythonanywhere.txt
```

Oppdateringsprogrammet si kjelde er `skript/oppdater_bygdelista.py` i repoet;
serverkopien ligg i heimemappa slik at kommandoen alltid er på same stad.
Kodebackup blir lagra i `/home/oslobygda/Bygdelista-backup/kode-for-oppdatering-*.tar.gz`.
Dette kjem i tillegg til den vanlege databasebackupen.

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
gjenoppretting. Automatisk kryptert kopi til Proton Drive er aktivert;
sjå [PROTON-BACKUP.md](PROTON-BACKUP.md) for drift og gjenopprettingskontroll.

## Dokumentasjon

- <https://help.pythonanywhere.com/pages/Flask/>
- <https://help.pythonanywhere.com/pages/CustomDomains/>
- <https://help.pythonanywhere.com/pages/HTTPSSetup/>


## Intern økonomi og bilag (steg 5)

Sjå [REKNESKAP.md](REKNESKAP.md) før funksjonen blir teken i bruk. Nye økonomitabellar
blir oppretta ved initialisering. Bilag skal lagrast utanfor kode- og statiske mapper,
standard `/home/oslobygda/bygdelista-data/bilag`, eventuelt styrt med
`BYGDELISTA_BILAG_DIR`. Ingen offentleg filkopling skal peike dit.

Bruk appens virtuelle miljø til backup. `backup.py` inkluderer bilag automatisk når
økonomitabellane finst. Ved bilagsoppsett i `.env`, bruk `backup_kommando.py` som
les dette oppsettet. Test eit komplett økonomibackupsett og kontroller diskbruk før
drift. Dei lokale setta er ukrypterte; Proton-jobben krypterer eksporten før overføring.


## Offentlege årsdokument (steg 6)

Sjå [PUBLISERING.md](PUBLISERING.md) før oppsett. Eigen dokumenttoken, publiserte
sidestubbar og ein vedlikehaldsjobb må konfigurerast før løpande tal kjem på nettsida.
Koden aktiverer ikkje publisering berre ved installasjon. Arbeidaren
`python -m flask --app app publiser-arsdokument` skriv berre kølagde, validerte
og uttrykkeleg valde offentlege dokument. Køyr fyrst etter kontrollert oppsett.


## Medlemsinntekter og kontrollert import (steg 8)

Sjå [BETALINGSIMPORT.md](BETALINGSIMPORT.md). Funksjonen er avslått som standard og
opprettar ingen jobb automatisk. Etter eksplisitt aktivering og kontrollert prøving
kan `python -m flask --app app importer-medlemsbetalingar --hent-vipps` brukast til
lesing av produksjonsstatus/hendingslogg og bokføring av kvalifiserte nye inntekter.
Kommandoen startar ikkje Vipps-trekk eller refusjonar. Historiske/manuelle betalingar,
gebyr og bankoppgjer må framleis avstemmast separat. Ikkje aktiver før reelle
opningssaldoar og tidlegare føringar er gjennomgått.

## Sluttkontroll og kryptert eksport

Sjå [SLUTTKONTROLL.md](SLUTTKONTROLL.md) før utrulling og
[BACKUP.md](BACKUP.md) for dei nye krypterings- og prøvekommandoane.
Lokale backupsett er framleis ukrypterte; berre særskild eksport blir kryptert.
Proton-jobben kontrollerer opplasting, nedlasting og gjenoppretting automatisk,
sjå [PROTON-BACKUP.md](PROTON-BACKUP.md).

## Oppdatering med årsmøte og økonomi

Bruk den konkrete rekkjefølgja i [SLUTTKONTROLL.md](SLUTTKONTROLL.md). Før Reload
må den oppdaterte versjonen av oppdateringsskriptet ha kopiert kategorinotane frå
`_data/rekneskapskategoriar.json`, og avhengnadene må vere installerte i eksisterande
appmiljø. Ta og prøv databasebackup før oppdatering. WSGI initialiserer dei nye
tabellane ved oppstart. Ingen publiserings- eller betalingsjobb blir aktivert av dette.

## Ny årsmøte- og økonomileveranse

Følg [UTRULLING.md](UTRULLING.md) før oppdatering. Der er oppdatert filoversikt,
styrelagring, backup, røykprøve og tilbakeføring samla. Ingen lokal testdata skal
kopierast til produksjon.
