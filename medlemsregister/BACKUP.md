# Backup på PythonAnywhere

Last opp `backup.py` i `/home/oslobygda/oslobygda/medlemsregister/`.
Rein databasebackup brukar berre Python-standardbiblioteket og vanleg SQLite, ikkje SQLCipher.
Etter at økonomimodulen er initialisert, inkluderer skriptet òg bilag gjennom
`okonomi_backup.py` og `bilag.py`; køyr då med appen sitt virtuelle miljø.
Det les ikkje `.env`, skriv ikkje ut medlemsdata og endrar ikkje aktiv database.

## Første køyring og dagleg oppgåve

Køyr i Bash-konsollen:

    /home/oslobygda/.virtualenvs/bygdelista/bin/python /home/oslobygda/oslobygda/medlemsregister/backup.py

Når økonomitabellane finst blir resultatet ei `okonomi-DATO-ID`-mappe med database,
bilag og manifest. Før dette er resultatet den vanlege databasefila.
Sjå [REKNESKAP.md](REKNESKAP.md) for samla backup og bilagssti.

Forventa resultat er `Backup og prøve av gjenoppretting: OK` og filstigen.
Kvar kopi vert verifisert med integritets- og referansekontroll, og gjenoppretta
som ei mellombels database for ny kontroll. Den aktive databasen vert ikkje overskriven.

Legg same kommando i ei **Daily** oppgåve under **Tasks** på PythonAnywhere.
Vel eit tidspunkt om natta. Kontroller oppgåveloggen etter første automatiske køyring
og deretter jamleg; oppsettet sender ikkje eigne feilvarsel.

Standard mappe er `/home/oslobygda/Bygdelista-backup`. Dei 30 nyaste kopiane
vert behaldne per backuptype (ikkje nødvendigvis 30 dagar). Gamle databasefiler
blir ikkje automatisk fjerna når ein går over til samla økonomibackup. Berre etter ein vellukka ny
backup vert gamle filer sletta. Mappa vert oppretta med tilgang berre for eigaren,
og backupfilene får rettar 600. Kopiane inneheld både medlemsdata og TOTP-nøklar.

## Test ein nedlasta kopi

Last ned ei ny backupfil eller eit komplett økonomibackupsett via **Files**.
For eit økonomisett må både database, manifest og bilag bevarast saman. Ho skal òg testast utanfor PythonAnywhere,
til dømes på Mac-en med kommandoen under (bruk faktisk filstig):

    python3 /sti/til/backup.py --verify /sti/til/medlemsregister-DATO.db

Denne testen prøver gjenoppretting i ei mellombels database og rører ikkje registeret.

## Kopi utanfor PythonAnywhere

Lokale serverkopiar vernar ikkje mot tap av heile kontoen. Last ned ein kopi
jamleg og lagre henne sikkert utanfor PythonAnywhere. Proton Drive kan nyttast,
helst med ein konto laget eig. Slett lokale nedlastingar når dei ikkje lenger trengst,
og avtal ei avgrensa lagringstid også for eksterne kopiar.
På produksjonsserveren går Proton-overføringa automatisk med eit eige skript;
sjå [PROTON-BACKUP.md](PROTON-BACKUP.md). `backup.py` lagar berre lokale kopiar.

## Dersom den aktive databasen må gjenopprettast

Ikkje prøv dette medan appen tek imot endringar. Stopp/deaktiver webappen og
backupoppgåva først. Ta vare på den noverande databasen og eventuelle tilhøyrande
`-wal`/`-shm`-filer for undersøking. Verifiser vald backup i ei separat mappe før
han vert sett inn som `medlemsregister.db`, med filrettar 600 og utan gamle
WAL/SHM-filer frå den førre databasen. Start appen att og kontroller data og innlogging.
Backupen inneheld styrekontoane slik dei var då kopien vart teken; kontoar som vart
sperra seinare må sperrast på nytt. Roter øktnøkkelen for å avslutte gamle økter.
Gjennomfør sjølve byteoperasjonen med hjelp dersom du er usikker.

## Gamal backup-kommando

`backup.sh` kallar no same konsistente backup gjennom `backup_kommando.py`.
Han les `.env` med python-dotenv i staden for å køyre innhaldet som shell-kode.
Bruk `BYGDELISTA_PYTHON` for å velje Python frå eit virtuelt miljø. Den daglege
PythonAnywhere-oppgåva kan framleis køyre `backup.py` direkte når bilagsmappa
er standard eller gitt med `--bilag-dir`. Ved oppsett i `.env`, bruk
`backup_kommando.py` slik at den rette bilagsstien blir lesen.

## Manuell kryptert kopi til Proton Drive

Installer oppdaterte `requirements-common.txt` i appens virtuelle miljø. Frå
`medlemsregister`, med det same miljøet aktivert:

    python -m flask --app app okonomi-backup --directory /home/oslobygda/bygdelista-data/backup
    python -m flask --app app okonomi-krypter-backup /sti/til/komplett-backupsett --output /home/oslobygda/bygdelista-data/backup-eksport.bygdebackup

Bruk den konkrete settmappa frå første kommando. Vel eit nytt filnamn for kvar
eksport; eksisterande filer blir ikkje overskrivne. Passfrasen blir etterspurd skjult,
må ha minst 16 teikn og skal oppbevarast separat frå backupfilene, tilgjengeleg for
styret. Tap av passfrasen gjer kopien ubrukeleg.

Eksporten bruker AES-256-GCM og scrypt og prøver faktisk dekryptering og isolert
gjenoppretting før fila blir ferdig. Lokale originalsett er framleis ukrypterte.
Last ned berre eksportfila og last henne manuelt opp til laget sin Proton Drive.
Last så fila ned att og køyr, i eit miljø med dei same modulane installerte:

    python -m flask --app app okonomi-prove-kryptert-backup /sti/til/nedlasta.bygdebackup

Prøva endrar ikkje aktiv database. Noter dato og resultat. Først etter denne prøva
kan den eksterne kopien reknast som kontrollert. Den automatiske produksjonsjobben
utfører opplasting og nedlastingsprøve sjølv; manuell eksport er eit alternativ.
Sjå også [SLUTTKONTROLL.md](SLUTTKONTROLL.md).

## Automatisk Proton-overføring

Sjå [PROTON-BACKUP.md](PROTON-BACKUP.md) for oppsett og kontrollert aktivering.
Den daglege lokale backupen held fram uendra; Proton-jobben er eit tillegg.
