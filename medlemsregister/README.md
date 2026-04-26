# Bygdelista (medlemsregister for Oslobygda)

Bygdelista er eit enkelt, GDPR-orientert medlemsregister (Flask-app) som styret typisk køyrer **lokalt**.

Appen har:

- **Styremodus (styregrensesnitt)**: legg til/endre medlemmer, handter betalingsstatus og GDPR-funksjonar (eksport/sletting)
- **Offentleg innmelding**: skjema på `/innmelding` som registrerer/oppdaterer medlem og sender innmelding vidare (enten via SMTP og/eller Brevo)

## Kva roller ser du?

- **Offentlege brukarar** fyller innmeldingsskjemaet
- **Styret** loggar inn og vedlikeheld medlemslista

## Starte appen (lokal køyring)

1. **Python 3.9+** – sjekk med `python3 --version`.
2. Installer avhengnader:

```bash
cd medlemsregister
pip install -r requirements.txt
```

3. Start:

```bash
python3 app.py
```

Viss du har ei `.env`-fil i `medlemsregister/`, vert ho lasta automatisk (via `python-dotenv`, som ligg i `requirements.txt`).

4. Opne:

- **Bygdelista (styret):** `http://127.0.0.1:5001/`
- **Innmeldingsskjema (offentleg):** `http://127.0.0.1:5001/innmelding`

Ved første køyring blir `medlemsregister.db` oppretta (i same mappe, ikkje i Git).

## Miljøvariablar

Du set miljøvariablane anten:

- i same terminal-vindu som du startar `python3 app.py` frå, eller
- via `medlemsregister/.env` (anbefalt lokalt)

Hugs: `.env` inneheld hemmelege verdiar og skal ikkje committast.

## Kva miljøvariablar styrer

### Passord og økt (styregrensesnitt)

- `MEDLEMSREGISTER_PASSWORD_HASH`: passord-hash for innlogging
  - Generer med:
    ```bash
    python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('ditt-passord'))"
    ```
- `MEDLEMSREGISTER_SECRET_KEY`: lang, tilfeldig streng for økthandtering (set ved driftsetjing; ikkje bruk appen opent på nett utan)
- `BACKUP_DIR`: mappe for backup (brukast av `backup.sh`)
- `MEDLEMSREGISTER_DB_KEY` (valfritt): krypter `medlemsregister.db` på disk med SQLCipher
  - Krev `sqlcipher3` i Python og `libsqlcipher` på systemet
  - Utan key blir DB-fila ukryptert (men appen set filrettar til berre eigar)

### Innmeldingsskjema: e-post til styret (SMTP)

Brukast når du vil sende e-post ved innmelding:

- `INNMELDING_EPOST_TIL` (standard: `folk@oslobygda.no`)
- `INNMELDING_EPOST_FRA` (valfritt)
- `SMTP_HOST` (t.d. `smtp.gmail.com`, `smtp.office365.com`)
- `SMTP_PORT` (vanlegvis `587`)
- `SMTP_USER`
- `SMTP_PASSWORD`

Om SMTP ikkje er sett, blir ikkje e-post sendt (men nyhendebrevleverandør kan framleis brukast).

### Innmeldingsskjema og sync: Brevo (standard)

- `NEWSLETTER_PROVIDER` (`brevo` eller `mailerlite`, standard `brevo`)
- `BREVO_API_KEY`
- `BREVO_LIST_ID` (standard liste for nyhendebrev / kontaktar)
- `BREVO_INNMELDING_LIST_ID` (valfri eigen liste for innmeldingsskjema)
- `BREVO_MEDLEMMAR_LIST_ID` (valfri liste brukt ved import til Bygdelista)

### Alternativ: MailerLite (bakoverkompatibel)

- `MAILERLITE_API_TOKEN`
- `MAILERLITE_GROUP_ID` (brukast i flyt der appen hentar/oppdaterer)
- `MAILERLITE_MEDLEMMAR_GROUP_ID` (gruppe-ID for “Medlemmar” i MailerLite)
  - Viss ikkje sett, blir `MAILERLITE_GROUP_ID` brukt som fallback

### Tekst etter innmelding

- `INNMELDING_SUCCESS_MESSAGE`: melding som brukaren ser når innmelding fungerer

## Bruk lokalt med andre i styret

**Eitt maskinoppsett (anbefalt):** køyr app og la andre gå inn over nettverket.

Start då med:

```bash
MEDLEMSREGISTER_PRODUCTION=1 python3 app.py
```

Appen lyttar på `0.0.0.0:5001`. Del IP-adressa til maskina og passord med styret. Bruk berre på eit trygt nett.

**Offline-kopi (alternativ):** del `medlemsregister.db` over sikker kanal. Unngå samtidige endringar.

## Backup

Heile medlemslista ligg i `medlemsregister.db`.

Du kan køyre backup til ei mappe som synkroniserer med t.d. OneDrive/Proton Drive:

1. Set `BACKUP_DIR` i `.env`
2. Køyr:
   ```bash
   bash backup.sh
   ```

Skriptet lagar datomerka tryggingskopiar og beheld berre dei nyaste (for å hindre at mappa veks utan ende).

## GDPR

- Samtykke blir lagra ved oppretting av medlem
- “Eksporter (GDPR)” lastar ned data for eitt medlem
- “Slett” fjernar medlem og data

DB-fila inneheld personopplysningar og skal ikkje i Git eller delast ukryptert.

## Alternativ flyt: Brevo-skjema (ingen offentleg Flask nødvendig)

Du kan la innmeldingsskjemaet vere eit Brevo-skjema (innebygging eller lenke på nettsida).

Då kan Flask-appen vere berre lokalt for styret, og de hentar nye frå nyhendebrevleverandøren i styregrensesnittet når de opnar appen.
