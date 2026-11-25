# Automatisk backup til laget sin Proton Drive

Mål: `oslobygda@proton.me`, mappa `Tryggleikskopiar`.
Den vanlege lokale nattbackupen held fram; sjå tidsrotasjonen nedanfor. `proton_backup.py`
lastar opp siste ferdige, integritetskontrollerte økonomibackupsett. Det omfattar
database (inkludert medlemsdata, styrekontoar, rekneskap, saklister og protokollar),
bilag og dei styre-/kalenderfilene som finst i manifestet.

Nye filer i Proton Drive får lesbare namn, til dømes
`Oslobygda - tryggleikskopi - 2026-11-01 kl 04.15.00 - a1b2c3d4.bygdebackup`.
Dato og klokkeslett viser når backupsettet blei laga, i norsk lokaltid
(med automatisk sommar-/vintertid). Den korte ID-en skil kopiane frå kvarandre.
Eksisterande overføringar beheld namnet sitt. Lokale backupnamn er uendra.

Før opplasting blir settet kryptert med eksisterande AES-256-GCM/scrypt-format
(`.bygdebackup`) og testa ved dekryptering. Etter opplasting blir fila lasta ned
att, SHA-256 samanlikna, dekryptert og gjenopprettingsprøvd i isolert mappe.
Først deretter blir `verified_at` registrert. Ein kopi som er kontrollert før blir
ikkje lasta opp igjen. Feila nedlastingsprøve blir prøvd igjen utan ny opplasting.
Eldre skyfiler blir handterte av rotasjonen nedanfor. Løysinga stoppar om kjeldebackupen er meir
enn 36 timar gammal, nøkkelfila er lesbar for andre eller feil Proton-konto er sett opp.

## Avhengnader og kontotilgang

Offisiell rclone-binær blir installert som `/home/oslobygda/bin/rclone`, med
kontroll av SHA-256 frå produsenten. Proton-backenden i rclone er i beta.
Proton sin offisielle CLI blei prøvd, men krasja ved oppstart på PythonAnywhere.
Den alternative musl-utgåva kravde ein loader som ikkje var tilgjengeleg.
Den ekstra krypteringa og nedlastings-/gjenopprettingsprøva er difor påkravd,
og den eksisterande lokale backupen blir ikkje erstatta.

Innlogging krev brukaren sitt passord og eventuelt ein ny eingongskode i ein
interaktiv terminal. Dei skal aldri skrivast i chat, shellhistorikk eller Git.
`proton_backup_setup.py` spør skjult, krypterer rclone-konfigurasjonen og lagrar
henne med filrettar 600. Rclone får kontotilgang; han er ikkje teknisk avgrensa
til backupmappa. Oppsettet krev uttrykkeleg godkjenning før slik tilgang blir lagra.

## Førstegongsoppsett og aktivering

Etter godkjent kontotilgang, køyr interaktivt med appens virtuelle miljø:

    python proton_backup_setup.py

Backupnøkkelen og kontooppsettet ligg i den private mappa
`/home/oslobygda/bygdelista-data/proton-backup/`. Ta vare på `backup-key.txt`
separat frå PythonAnywhere, til dømes i laget sin passordhandterar. Tap av
nøkkelen gjer dei ekstra krypterte eksportfilene ubrukelege.

Ta deretter ein prøve med:

    python proton_backup.py --settings /home/oslobygda/bygdelista-data/proton-backup/settings.json

Aktiver først automatisk køyring etter faktisk vellukka opplasting, nedlasting
og gjenopprettingsprøve. Oppgåve på PythonAnywhere: **Hourly**, minutt
45, med full stig til appens Python og dette skriptet. Det fangar opp den
nattlege backupen kl. 03:15 UTC og prøver på nytt ved mellombelse feil.
Kontroller oppgåveloggen og `exports/status.json`; ein konfigurert jobb åleine
er ikkje bevis på vellukka offsite-backup. Dersom Proton krev ny innlogging,
køyr innloggingsoppsettet på nytt. Det endrar ikkje eksisterande backupnøkkel.

Status 31. oktober 2026: Aktivert på PythonAnywhere som Hourly, minutt 45,
oppgåvelogg `/var/log/schedule-log-28824.log`. Reell opplasting, nedlasting,
dekryptering og isolert gjenoppretting av ein fersk backup blei kontrollert
kl. 11:43 UTC. Den daglege lokale backupen går framleis kl. 03:15 UTC.
Separat oppbevaring av backupnøkkelen må gjerast av laget.

## Rotasjon: 30 dagar dagleg, deretter vekentleg til 90 dagar

Tidsrotasjon er installert i produksjon som 9dd397b. Eigaren stadfesta
vellukka lokal backup og Proton-køyring med `Backuprotasjon: rotated`
25. november 2026, ferdig om lag 22:02 UTC. Den nye Proton-kopien vart
verifisert 21:56:29 UTC. Eigaren har deretter stadfesta at papirkorga er tømd og dei to eldre
Proton-oppføringane er sletta. Konsollkvittering for --acknowledge-trash er
ikkje motteken.
Førehandskontrollen rapporterte 104 ukjende filer/mapper som ikkje vart rørte;
desse må inventerast separat. Standard nattbackup av komplette
økonomisett bevarer nyaste kopi per UTC-dag i 30 dagar og deretter nyaste kopi
per ISO-veke fram til 90 dagar. Dei to nyaste verifiserte kopiane blir alltid
bevarte. Eksplisitt `--keep` vel framleis eldre talrotasjon; fjern eit slikt
argument frå oppgåva dersom tidsrotasjon skal gjelde.

Vanleg køyring av `proton_backup.py --settings ...` køyrer no også rotasjon,
høgst éin vellukka gong per UTC-dag. Ho krev fersk backup og verifisering
(maksimalt 36 timar). Alle attkjende Proton-arkiv blir lasta ned, dekrypterte
og gjenopprettingsprøvde før noko blir rydda. Dette kan ta tid første gong.
Datoen kjem frå manifestet. Berre strengt attkjende filnamn i den avsette mappa
blir handterte. Ukjende eller skadde kopiar blir ikkje automatisk sletta.
Lokale eksportfiler utan ein kontrollert Proton-motpart blir bevarte og varsla.
Verifiseringshistorikk og ventande papirkorgkontroll ligg privat i `rotation.json`.

**Proton-sletting er ikkje permanent:** rclone sitt Proton-backend flyttar
konkrete filer til papirkorga. Rotasjonen sender difor e-post til
folk@oslobygda.no med filnamna som må slettast permanent der. Ikkje tøm heile
papirkorga dersom ho inneheld andre filer. Etter faktisk permanent sletting:

    python proton_backup.py --settings /home/oslobygda/bygdelista-data/proton-backup/settings.json --acknowledge-trash

Dette er mennesket si stadfesting, ikkje ei teknisk kontroll av papirkorga.
Proton sine eigne interne sikkerheitskopiar kan i tillegg bestå etter tenesta
sine vilkår. Ein absolutt lovnad om at alle kopiar er borte etter 90 dagar
ville difor vere feil. Påminning går ved dagleg rotasjon til kontrollen er
stadfesta. Gamle kopiar som må bevarast av tryggingsomsyn, ukjende filer og
feila backup/rotasjon krev òg manuell kontroll; feilvarsel blir forsøkt høgst
ein gong per UTC-dag. Kontroller oppgåveloggen om e-post ikkje kjem fram.

### Produksjonsutrulling

1. Ta ein fersk backup med den gamle, installerte `backup_kommando.py`.
2. Køyr den etablerte `oppdater-bygdelista.py`. Ingen nye pakkar er nødvendige.
3. Kontroller kandidatane utan sletting (bruk appmiljøet sin fulle Python-stig):

       python backup_kommando.py --rotation-preview
       python proton_backup.py --settings /home/oslobygda/bygdelista-data/proton-backup/settings.json --rotation-preview

4. Køyr vanleg `backup_kommando.py`, så vanleg `proton_backup.py --settings ...`.
   Kontroller resultat, eventuelt e-postvarsel og oppgåvelogg. Dei eksisterande
   oppgåvene tek deretter over; kontroller at nattjobben ikkje bruker `--keep`.
   CLI-jobbane krev ikkje Web Reload.
5. Slett berre dei varsla filene permanent frå Proton-papirkorga og stadfest
   med kommandoen ovanfor.

Eldre enkeltståande databasekopiar, kodebackup-tararkiv og manuelt nedlasta
kopiar er ikkje del av denne rotasjonen. Dei må inventerast separat: ei
kodebackup kan innehalde private data frå den aktive mappa. Ukjende filer
skal aldri slettast berre på grunnlag av namnet eller filsystemdatoen.

Ved gjenoppretting må personvernslettingar utførte etter backupdatoen
leggjast på att før databasen blir teken i bruk.
