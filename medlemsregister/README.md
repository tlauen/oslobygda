# Bygdelista (medlemsregister for Oslobygda)

Eit enkelt, **GDPR-sikkert** medlemsregister (Bygdelista) som køyrer **lokalt** med Flask. Inneheld også eit offentleg **innmeldingsskjema** som sender e-post til styret og registrerer i MailerLite.

---

## Starte appen (lokal køyring)

1. **Python 3.9+** – sjekk med `python3 --version`.
2. **Avhengigheter:**
   ```bash
   cd medlemsregister
   pip install -r requirements.txt
   ```
3. **Start:**
   ```bash
   python3 app.py
   ```
   Viss du har ei **`.env`**-fil i `medlemsregister/`, vert ho lasta automatisk (krev `python-dotenv`, som ligg i `requirements.txt`). Du treng ikkje køyre `export` først.
4. Opne **http://127.0.0.1:5001/** – logg inn med passord (standard: `admin`, endre det – sjå under).

- **Bygdelista (admin):** http://127.0.0.1:5001/
- **Innmeldingsskjema (offentleg):** http://127.0.0.1:5001/innmelding

Ved første køyring opprettast `medlemsregister.db` i same mappe (ikkje i Git).

---

## Miljøvariablar – kor set du dei?

Når du køyrer Flask **lokalt**, set du miljøvariablane i **samme terminal-vindu** som du startar `python3 app.py` i, eller du bruker ei **.env-fil**.

### Variant A: Direkte i terminalen

Før du køyrer `python3 app.py`, skriv (på éi linje eller fleire):

```bash
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=din@epost.no
export SMTP_PASSWORD=ditt-app-passord
export MAILERLITE_API_TOKEN=din-token
export MAILERLITE_GROUP_ID=gruppe-id
python3 app.py
```

### Variant B: .env-fil (raskt ved kvar start)

1. Lag ei fil **`.env`** i mappa `medlemsregister/` (same nivå som `app.py`). Fila er i `.gitignore` og kjem ikkje med i Git.
2. Skriv inn variablane, éin per linje (utan `export`):
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=din@epost.no
   SMTP_PASSWORD=ditt-app-passord
   INNMELDING_EPOST_TIL=folk@oslobygda.no
   MAILERLITE_API_TOKEN=din-token
   MAILERLITE_GROUP_ID=12345678
   BACKUP_DIR=/sti/til/backup-mappa
   MEDLEMSREGISTER_DB_KEY=din-sterke-passfrase-for-database-kryptering
   ```
3. Start appen som vanleg med `python3 app.py`. Appen lastar `.env` automatisk (via python-dotenv). Viss du ikkje har installert på nytt nylig, kjør `pip install -r requirements.txt` éin gong for å få med `python-dotenv`.

Du kan også bruke eit skript som les `.env` og startar appen, eller setje variablane i shell-profilen din (`.zshrc` / `.bashrc`) viss du alltid skal ha dei.

---

## Kva miljøvariablar gjer

### Passord og session (Bygdelista)

- **`MEDLEMSREGISTER_PASSWORD_HASH`** – passord-hash for innlogging. Lag med:
  ```bash
  python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('ditt-passord'))"
  ```
- **`MEDLEMSREGISTER_SECRET_KEY`** – ein lang, tilfeldig streng (for session). Viss ikkje satt, bruk ikkje appen opent på nett.
- **`BACKUP_DIR`** – mappe for database-backup (t.d. inni OneDrive). Brukt av `backup.sh`; viss ikkje satt, brukes `~/Bygdelista-backup`.
- **`MEDLEMSREGISTER_DB_KEY`** – (valgfritt) Passord/key for å kryptere databasen med SQLCipher. Når dette er satt, vert `medlemsregister.db` kryptert på disk, så persondata ikkje er lesbart i BBEdit eller andre teksteditorar. Appen migrerer automatisk frå ukyrptert til kryptert DB ved første køyring. Krev at `sqlcipher3` er installert (`pip install sqlcipher3`) og at **libsqlcipher** er på systemet (macOS: `brew install sqlcipher`). Lag ein sterk, lang passfrase og legg i `.env`. Utan key vert DB-fila ukyrptert; appen set då filrettar til berre eigar (chmod 600) for å redusere risiko.

### Innmeldingsskjema – e-post til styret (SMTP)

- **`INNMELDING_EPOST_TIL`** – Mottakar (standard: `folk@oslobygda.no`).
- **`INNMELDING_EPOST_FRA`** – Avsendar (valfritt).
- **`SMTP_HOST`** – t.d. `smtp.gmail.com`, `smtp.office365.com`.
- **`SMTP_PORT`** – vanlegvis `587`.
- **`SMTP_USER`** – e-postadresse / brukarnamn.
- **`SMTP_PASSWORD`** – passord eller app-passord (Gmail: Bruk Konto → Sikkerhet → App-passord).

Viss SMTP ikkje er satt, vert ikkje e-post sendt; MailerLite kan likevel brukast.

### Innmeldingsskjema – MailerLite

- **`MAILERLITE_API_TOKEN`** – API-token frå MailerLite.
- **`MAILERLITE_GROUP_ID`** – brukt ved «Hent nye frå MailerLite» (og ved Flask-innmeldingsskjema viss du bruker det).
- **`MAILERLITE_MEDLEMMAR_GROUP_ID`** – gruppe-ID for gruppa «Medlemmar» (t.d. `181371641813534665`). Brukes av «Hent nye frå MailerLite». Viss ikkje satt, brukes `MAILERLITE_GROUP_ID`.

### Tekst som visast etter innmelding

- **`INNMELDING_SUCCESS_MESSAGE`** – Meldinga brukaren får når alt gjekk bra (e-post + MailerLite). Viss ikkje satt, brukes standardtekst. Du kan setje din eigen tekst i `.env` eller som miljøvariabel, t.d.:
  ```
  INNMELDING_SUCCESS_MESSAGE=Takk! Du er meldt inn. Vi tek deg inn i Bygdelista så snart vi ser henne.
  ```
  Du kan også endre **standardteksten** direkte i **`app.py`**: søk etter `default_msg = "Takk for innmeldinga!` og rediger den strengen.

---

## Bruk lokalt med andre i styret

**Én kjører, andre går inn over nettverket:** Start med `MEDLEMSREGISTER_PRODUCTION=1 python3 app.py`. Da lyttar appen på `0.0.0.0:5001`. Finn IP-adressa til maskinen (t.d. `ipconfig getifaddr en0` på Mac) og del adressa + passord med styret. Bruk berre på eit trygt nett.

**Fleire med eiga kopi:** Database-fila `medlemsregister.db` kan delast over sikker kanal; den som har oppdatert kopi sender fila til den andre. Passord må vere kjent. Koordiner slik at ikkje begge endrar samtidig.

---

## Backup av databasen

Heile medlemslista ligg i **`medlemsregister.db`**. For å sikre dobbellagring kan du køyre backup til ei mappe som synkroniserer med **OneDrive** eller **Proton Drive**.

### Slik gjer du det

1. **Backup-mappa:** Legg `BACKUP_DIR="/sti/til/backup-mappa"` i **`.env`** i medlemsregister-mappa (t.d. ei mappe inni OneDrive eller Proton Drive). Scriptet les `.env` automatisk.
2. **Køyr backup** – stå inne i `medlemsregister/` og kjør:
   ```bash
   bash backup.sh
   ```
   Utan `BACKUP_DIR` i miljø eller `.env` går backup til `~/Bygdelista-backup`.
3. **Gjenta regelmessig** – t.d. etter at du har lagt inn nye medlemmar. Du kan automatisere med **launchd** (Mac) eller **cron**.

Viss du bruker **MEDLEMSREGISTER_DB_KEY**, er backup-fila også kryptert; du treng same key for å opne ho (t.d. i ein annan installasjon).

Scriptet lagar éi kopi per køyring med dato og klokkeslett i filnamnet (t.d. `medlemsregister-2026-03-08-1430.db`) og behald berre dei **30 nyaste** backupane, så mappa ikkje vaksar utan ende.

---

## GDPR

- **Samtykke** lagrast ved opprettelse av medlem.
- **Innsyn:** Bruk «Eksporter (GDPR)» på eit medlem for å laste ned data.
- **Sletting:** «Slett» fjerner medlem og data.
- Database-fila inneholder personopplysningar og skal ikkje i Git eller delast.

---

## Bruke MailerLite-skjema som innmeldingsskjema (gratis, utan server)

Du kan la **innmeldingsskjemaet** vere eit **skjema frå MailerLite** (embed eller lenke på nettsida). Da treng du ingen SMTP eller at Flask-appen køyrer offentleg for skjemaet.

1. **I MailerLite:** Opprett ei gruppe, t.d. «Medlemmar». Lag eit skjema som legg innmeldte i den gruppa (Subscribers → Forms, eller Groups → «Medlemmar» → Add form). Legg til dei felta du vil (namn, epost, telefon, adresse osb.). Ta med gruppa «Medlemmar» på skjemaet.
2. **På nettsida:** Sett inn MailerLite-skjemaet (embed-kode eller lenke) på oslobygda.no – t.d. på ei side «Bli medlem» som er statisk (Jekyll/GitHub Pages). Ingen Flask treng å køyre for at skjemaet skal fungere.
3. **Overføre til Bygdelista:** Når du (eller nokon i styret) er inne i Bygdelista (lokalt), klikk **«Hent nye frå MailerLite»**. Da hentar appen alle abonnentar i gruppa «Medlemmar» og legg til dei som ikkje allereie finst (sjekka på epost). Felt frå MailerLite vert mappa slik: **fornamn**, **etternamn**, **mellomnamn**, **adresse**, **medlemstype**, **fodselsdato** (Subscribers → Fields). Standardfelt som **name**, **last_name**, **phone**, **city**, **z_i_p**, **epost** brukast som fallback. Sett `MAILERLITE_MEDLEMMAR_GROUP_ID` og `MAILERLITE_API_TOKEN` i `.env`.

Du treng altså ikkje at innmeldingsskjemaet i Flask køyrer på ein server – du kan bruke berre MailerLite-skjema og så hente inn i Bygdelista når du opnar appen lokalt.
