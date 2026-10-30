# Kontrollert utrulling av årsmøte og økonomi

Status 29. oktober 2026: førebuing, ikkje utført produksjonsutrulling.
Arbeidet ligg på `test/nidarosbygda`; serveroppdateraren hentar berre `main`.
Ingen testdatabase, testkonto, lokal kalender, prøveversjon eller backuppassfrase
skal overførast til produksjon. `lokal_test.py` skal aldri vere WSGI-inngang.

## 1. Før kode blir gjord tilgjengeleg

- Køyr heile Python-testsamlinga, Jekyll-bygg og `git diff --check`.
- Gå gjennom endringane og legg dei nye modulane, malane og datafilene til i Git.
  Lag ein gjennomgått commit/PR frå testgreina. Ingen direkte kopiering av heile
  arbeidsmappa til server. Publisering av kode/main er eit seinare steg.
- Avtal eit kort opphald i registrering. Dokumenter kva kodeversjon som køyrer
  på serveren og kva database, virtuelle miljø og WSGI-fil han faktisk bruker.
- Ta ein konsistent databasebackup med eksisterande rutine før ny kode køyrer.
  Bevar også eksisterande .env og eventuelle private filmapper i privat lagring.
  Test gjenoppretting til ei anna fil, aldri oppå aktiv database.

## 2. Serverkontroll før Reload

Bruk det eksisterande virtuelle miljøet. Sjå PYTHONANYWHERE.md for miljøstigen;
ikkje gjett han og ikkje opprett miljøet på nytt.

```bash
python --version
python -m pip install -r /home/oslobygda/oslobygda/medlemsregister/requirements-pythonanywhere.txt
python -m pip check
```

Kommandoane køyrast først etter at godkjend kode er tilgjengeleg på serveren.
Oppdater sjølve `/home/oslobygda/oppdater-bygdelista.py` etter eksisterande
rettleiing. Det nye filteret må ta med:

- `_data/rekneskapskategoriar.json`
- `_data/balanseforklaringar.json`
- `_data/styre.yml` og offentlege portrett i `lutar/bilete/styret/`
- alle nye Python-modular, malar og statiske filer i medlemsregisteret.

```bash
python3 /home/oslobygda/oppdater-bygdelista.py --dry-run
```

Dry-run gjer ingen installasjon i appmappa, men oppdaterer Git-kjeldekopien.
Installer med same kommando utan `--dry-run` først når sjekklista er gjennomgått.

## 3. Private mapper og innstillingar

Stadfest desse før Reload, utan å skrive løyndomar i loggar eller chat:

- Eksisterande database og øktløyndom skal bevarast.
- Bilag: privat mappe utanfor repo og statiske mapper (`BYGDELISTA_BILAG_DIR`).
- Styredata: `BYGDELISTA_STYRE_FILE=/home/oslobygda/bygdelista-data/styre.yml`.
  Manglande fil les offentleg startgrunnlag frå repoet. Fyrste lagring opprettar
  den private arbeidskopien. Nye portrett ligg i same foreldremappe/styreportrett.
- `BYGDELISTA_LOCAL_TEST` skal ikkje vere sett. WSGI avviser verdien `1`.
- Ingen prøveklokke: berre lokal_test.py set prøvedatoen.
- Verifiser faktiske innstillingar for import og publisering; ikkje aktiver nye
  automatiske jobbar som del av denne utrullinga. Eksisterande innmeldingsteneste
  skal behalde sine ordinære innstillingar.
- Ikkje aktiver SQLCipher som del av denne endringa; det krev eiga migrering.

## 4. Reload og røykprøve

Etter installasjon og avhengnadskontroll: PythonAnywhere → Web → Reload.
WSGI kallar init_db; ikkje kopier inn Nidarosbygda-databasen.

Kontroller med vanleg personleg styreinnlogging:

1. Eksisterande medlemstal og medlemsopplysningar er bevarte.
2. Medlemsliste, innmeldingar, styre og årsmøtesider opnar utan feil.
3. Ingen TESTMILJØ-banner eller prøvedato; rekneskapen inneheld ikkje dømeåret.
4. Styrekjelda og portretta lastar. Offentleg nettside er framleis uendra.
5. Kontroller bilagsvern utan å leggje reelle personopplysningar i offentleg lagring.
6. Ta ny komplett backup via `okonomi-backup` i appmiljøet. Den inkluderer no
   database, bilag og styredata/portrett. Stadfest også dei faktiske backupjobbane.
7. Krypter og prøv gjenoppretting av produksjonskopien. Nøkkelen skal oppbevarast
   separat. Gjenta Proton-rundturen med denne kopien før rutinen blir godkjend.

Kalenderen i produksjon ligg i Git, ikkje i den lokale prøvefila. Git-kjelde og
private konfigurasjonsløyndomar må ha eigne bevaringsrutinar i tillegg til appbackup.

## 5. Tilbakeføring

Ved oppstartsfeil: stans registrering, bevar feillogg og kontroller miljø/kode.
Oppdateraren lagar kodebackup i `/home/oslobygda/Bygdelista-backup/`.
Kodebackup er ikkje databasebackup. Nye tabellar kan normalt bli ståande ved
kodetilbakeføring, men dette må vurderast mot feilen. Ikkje gjenopprett ein eldre
database før appen er stansa og ein ny kopi av den noverande databasen er teken.
Avtal korleis eventuelle nye innleggingar etter utrullinga skal bevarast.

## Ferdigkriterium

Utrullinga er ikkje ferdig før røykprøva, serverbackupen og gjenopprettingsprøva
passerer. Reell offentleg dokumentpublisering og ePayment-import får eigne prøver
og aktiveringssteg etterpå. Styret-sida publiserer førebels via nedlastbar
nettsidepakke, ikkje direkte til GitHub.
