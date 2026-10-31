# Automatisk backup til laget sin Proton Drive

Mål: `oslobygda@proton.me`, mappa `Tryggleikskopiar`.
Den vanlege lokale nattbackupen skal halde fram uendra. `proton_backup.py`
lastar opp siste ferdige, integritetskontrollerte økonomibackupsett. Det omfattar
database (inkludert medlemsdata, styrekontoar, rekneskap, saklister og protokollar),
bilag og dei styre-/kalenderfilene som finst i manifestet.

Før opplasting blir settet kryptert med eksisterande AES-256-GCM/scrypt-format
(`.bygdebackup`) og testa ved dekryptering. Etter opplasting blir fila lasta ned
att, SHA-256 samanlikna, dekryptert og gjenopprettingsprøvd i isolert mappe.
Først deretter blir `verified_at` registrert. Ein kopi som er kontrollert før blir
ikkje lasta opp igjen. Feila nedlastingsprøve blir prøvd igjen utan ny opplasting.
Ingen eksisterande skyfiler blir sletta. Løysinga stoppar om kjeldebackupen er meir
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
