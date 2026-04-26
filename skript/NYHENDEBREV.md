## Fullauto nyhendebrev via Brevo (aktiv)

Dette repoet sender nyhendebrev automatisk via Brevo API.

### Aktiv flyt

- Workflow: `.github/workflows/nyhendebrev-brevo.yml`
- Script: `skript/send_nyhendebrev_brevo.rb`
- Datakjelde: `_data/kalender.yml`
- Trigger: sender når dato er `7` dagar før neste `pobb-`-arrangement

### Nødvendige GitHub Secrets (Brevo)

- `BREVO_API_KEY`
- `BREVO_LIST_ID` – numerisk ID for hovudlista **«Nyhendebrev»** (alle som skal ha brevet i drift)
- `BREVO_TEST_LIST_ID` – numerisk ID for lista **«Test»** (berre brukt når du slår på testmodus under manuell køyring)
- `BREVO_FROM_EMAIL`
- `BREVO_FROM_NAME`
- `BREVO_REPLY_TO` (valfri)

I Brevo: **Contacts → Lists** – opprett/minn **Test** med t.d. berre di eiga e-post, og noter list-ID for `BREVO_TEST_LIST_ID`.

### Vanleg utsending vs. test

| Situasjon | Mottakarar | Miljø / GitHub |
|-----------|------------|----------------|
| **Cron + manuell utan test** | Lista med `BREVO_LIST_ID` («Nyhendebrev») | `BREVO_BRUK_TEST_LISTE` tom / `bruk_test_lista` av |
| **Teste auto-utsending** | Lista med `BREVO_TEST_LIST_ID` («Test») | `BREVO_BRUK_TEST_LISTE=1` eller **Run workflow** med **bruk_test_lista** på, pluss **force_send** viss i dag ikkje er 7 dagar før pøbb |

Test brukar eige kampanjenamn (`Test – nyhendebrev – …`) slik at det ikkje krockar med ordinar kampanje same dato.

### Kva scriptet gjer

1. Les komande arrangement frå kalenderen
2. Finn neste `pobb-` som trigger
3. Bygg emnefelt + HTML-innhald etter Oslobygda-malen
4. Opprett kampanje i Brevo mot valt liste-ID
5. Sender kampanjen (`sendNow`)

Scriptet brukar kampanjenamn med dato for å unngå dobbel utsending.

## MailerLite backup (dvale)

Dette ligg framleis i repoet for beredskap:

- Workflow (manuell): `.github/workflows/nyhendebrev.yml`
- Script: `skript/send_nyhendebrev_mailerlite.rb`
- Avansert tidlegare variant: `skript/send_nyhendebrev_mailerlite_advanced.rb`
- Manuell tekstbackup: `brev/tekstgenerator.md`
