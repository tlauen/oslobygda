## Fullauto nyhendebrev via Brevo (aktiv)

Dette repoet sender nyhendebrev automatisk via Brevo API.

### Aktiv flyt

- Workflow: `.github/workflows/nyhendebrev-brevo.yml`
- Script: `skript/send_nyhendebrev_brevo.rb`
- Datakjelde: `_data/kalender.yml`
- Trigger: sender når dato er `7` dagar før neste `pobb-`-arrangement

### Nødvendige GitHub Secrets (Brevo)

- `BREVO_API_KEY`
- `BREVO_LIST_ID` (lista som skal få nyhendebrevet)
- `BREVO_FROM_EMAIL`
- `BREVO_FROM_NAME`
- `BREVO_REPLY_TO` (valfri)

### Testkøyring

Gå til **Actions → Send nyhendebrev (Brevo)** og bruk `force_send=true` for test.

### Kva scriptet gjer

1. Les komande arrangement frå kalenderen
2. Finn neste `pobb-` som trigger
3. Bygg emnefelt + HTML-innhald etter Oslobygda-malen
4. Opprett kampanje i Brevo mot `BREVO_LIST_ID`
5. Sender kampanjen (`sendNow`)

Scriptet brukar kampanjenamn med dato (`Nyhendebrev – tilskipingar – YYYY-MM-DD`) for å unngå dobbel utsending.

## MailerLite backup (dvale)

Dette ligg framleis i repoet for beredskap:

- Workflow (manuell): `.github/workflows/nyhendebrev.yml`
- Script: `skript/send_nyhendebrev_mailerlite.rb`
- Avansert tidlegare variant: `skript/send_nyhendebrev_mailerlite_advanced.rb`
- Manuell tekstbackup: `brev/tekstgenerator.md`
