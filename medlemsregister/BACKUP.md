# Backup på PythonAnywhere

Last opp `backup.py` i `/home/oslobygda/oslobygda/medlemsregister/`.
Skriptet brukar berre Python-standardbiblioteket og vanleg SQLite, ikkje SQLCipher.
Det les ikkje `.env`, skriv ikkje ut medlemsdata og endrar ikkje aktiv database.

## Første køyring og dagleg oppgåve

Køyr i Bash-konsollen:

    /home/oslobygda/.virtualenvs/bygdelista/bin/python /home/oslobygda/oslobygda/medlemsregister/backup.py

Forventa resultat er `Backup og prøve av gjenoppretting: OK` og filstigen.
Kvar kopi vert verifisert med integritets- og referansekontroll, og gjenoppretta
som ei mellombels database for ny kontroll. Den aktive databasen vert ikkje overskriven.

Legg same kommando i ei **Daily** oppgåve under **Tasks** på PythonAnywhere.
Vel eit tidspunkt om natta. Kontroller oppgåveloggen etter første automatiske køyring
og deretter jamleg; oppsettet sender ikkje eigne feilvarsel.

Standard mappe er `/home/oslobygda/Bygdelista-backup`. Dei 30 nyaste kopiane
vert behaldne (30 filer, ikkje nødvendigvis 30 dagar). Berre etter ein vellukka ny
backup vert gamle filer sletta. Mappa vert oppretta med tilgang berre for eigaren,
og backupfilene får rettar 600. Kopiane inneheld både medlemsdata og TOTP-nøklar.

## Test ein nedlasta kopi

Last ned ei ny backupfil via **Files**. Ho skal òg testast utanfor PythonAnywhere,
til dømes på Mac-en med kommandoen under (bruk faktisk filstig):

    python3 /sti/til/backup.py --verify /sti/til/medlemsregister-DATO.db

Denne testen prøver gjenoppretting i ei mellombels database og rører ikkje registeret.

## Kopi utanfor PythonAnywhere

Lokale serverkopiar vernar ikkje mot tap av heile kontoen. Last ned ein kopi
jamleg og lagre henne sikkert utanfor PythonAnywhere. Proton Drive kan nyttast,
helst med ein konto laget eig. Slett lokale nedlastingar når dei ikkje lenger trengst,
og avtal ei avgrensa lagringstid også for eksterne kopiar.
Dette er førebels ein manuell rutine; skriptet lastar ikkje opp til Proton.

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
PythonAnywhere-oppgåva kan framleis køyre `backup.py` direkte som før.
