# Bygdelista

Flask-app for medlemsadministrasjon, årsmøte og økonomi på `https://bygdelista.oslobygda.no`.
Den offentlege nettsida blir bygd separat med Jekyll, men menydata og footer
har éi felles kjelde i repoet.

## Funksjonar

- Personlege styrekontoar med passord, TOTP og e-poststadfesting.
- Medlemsliste, innbetalingar, medlemsår, eksport og personvernhandtering.
- Nye medlemmar på `/bli-medlem`: Vipps, stadfesta trekk og valfritt nyhendebrev.
- Årlege kontingentsatsar og personlege fornyingslenkjer med Vipps.
- Innmeldingsoversikt for styret på `/innmeldingar`.
- Oppretting og redigering av komande tilskipingar på `/tilskipingar`.
- Årsfesta styre med namn, verv og portrett på `/styret`.
- Strukturert årsmelding med kalenderimport og faste versjonar på `/arsmote`.
- Rekneskap, bilag, balanse og stegvis årsslutt på `/okonomi`.
- Budsjett og oppfølging på `/budsjett`.
- [Sakliste, møtereglar og protokoll med to godkjenningar](SAKLISTE.md) på `/sakliste`.
- Offentleg eksport, utskriftsvising og kryptert backup med gjenopprettingskontroll.

## Årsmøte, økonomi og drift

Start med [rekneskap](REKNESKAP.md), [årsdokument](ARSDOKUMENT.md) og
[budsjett](BUDSJETT.md). Sjå også [betalingsimport](BETALINGSIMPORT.md),
[publisering](PUBLISERING.md), [PDF/utskrift](UTSKRIFT.md) og [backup](BACKUP.md).
Medlems- og økonomidelane har eigne hjelpesider i appen.

Bruk [Nidarosbygda-rettleiinga](NIDAROSBYGDA-TEST.md) for isolert lokal prøving.
Testdata, testkonto og prøvedato skal ikkje overførast til produksjon.
Følg [UTRULLING.md](UTRULLING.md) og [PYTHONANYWHERE.md](PYTHONANYWHERE.md)
ved serveroppdatering. Nye funksjonar i Git er ikkje prov på at dei køyrer på serveren.

Styret-sida lagrar ei privat arbeidskjelde. Årsmeldinga hentar ein kopi for året;
nettsida blir oppdatert via nedlastbar nettsidepakke. Ordinær økonomibackup tek
med database, bilag, styredata og portrett. Produksjonskalender og kode blir
bevarte i Git; konfigurasjonsløyndomar må sikrast separat.

Gamle `/innmelding` sender vidare til det nye skjemaet. POST `/api/innmelding`
er avvikla (410) og har ingen e-post- eller kontakt-sideeffektar.

## Lokalt miljø

Bruk Python 3.10 eller nyare og eit eige virtuelt miljø. Felles avhengnader:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-common.txt
python app.py
```

Dette startar lokalt på `127.0.0.1:5001`. For ein eksisterande SQLCipher-database,
installer `requirements.txt` og libsqlcipher. Appen nektar å opne databasen dersom
krypteringsnøkkel er sett utan driver, og migrerer ikkje automatisk frå ukryptert
SQLite. Ta backup og migrer alle tabellane særskilt ved behov.

Testane lagar mellombelse databasar. Dei sender ingen betalingar eller e-post:

```bash
python -m unittest discover -s tests
```

## Felles nettsidefiler

- `_data/nav.yml`: same fire menyval på nettsida og i innmeldingsflyten.
- `_tillegg/kolofon.html`: éin footer-mal med ordforklaring og logo.
- `lutar/kolofon.css` og `lutar/topp.css`: felles CSS, levert under `/felles/`.

Desse filene må følgje med serverkoden. Ikkje kopier berre `medlemsregister/`.

## Integrasjonar og drift

- [PythonAnywhere](PYTHONANYWHERE.md): mappar, HTTPS og WSGI.
- [Vipps](VIPPS.md): testmiljø, webhook, reservejobb og produksjonsprøve.
- [Styrekontoar](STYREKONTOAR.md): oppretting og sperring.
- [Tilskipingar](TILSKIPINGAR.md): GitHub-tilgang og kalenderpublisering.
- [Backup](BACKUP.md): konsistent SQLite-backup og testa gjenoppretting.
- [Fornying](FORNYING.md): vedtak, opning av kontingentår og personlege lenkjer.
- [Medlemsår](HUSK_MEDLEMSAR.md): årsavslutning.

Løyndomar ligg berre i `.env` og `.env.vipps-test` (600), aldri i Git eller
nettlesaren. Oppsettsskript for Vipps, Brevo, SMTP og GitHub les nøklar skjult.
`requirements-common.txt` er felles, medan dei to andre pakkelistene legg til
miljøspesifikke avhengnader.

Brevo-utgang er berre for betalte produksjonsinnmeldingar som vel nyhendebrev.
`BREVO_INNMELDING_LIST_ID` peikar til nyhendebrevlista. Eventuell manuell import
frå Brevo krev ei eiga, uttrykkeleg `BREVO_MEDLEMMAR_LIST_ID`; appen fell aldri
tilbake til nyhendebrevlista som medlemsregister.

## Sletting og rekneskap

Ved sletting blir medlemsopplysningar, ordredetaljar og tilknytt styrekonto fjerna.
Dersom medlemmen har innbetalingar, blir ein post utan kontaktopplysningar bevart for at summer,
medlemsår og betalingsreferansar skal kunne avstemmast. Han blir ikkje vist som
medlem. Pågåande produksjonsbetalingar eller `review` må avklarast før sletting.

Sletting hos Brevo blir lagd i `privacy_jobs`; den timelege reservejobben prøver
igjen til leverandøren stadfestar sletting eller at kontakten ikkje finst. E-posten
blir fjerna frå køen etterpå. Eldre backupkopiar følgjer backup-rotasjonen og må
ikkje brukast til å reaktivere sletta medlemskap eller nyhendebrevabonnement.
