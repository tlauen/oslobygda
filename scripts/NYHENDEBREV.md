## Fullauto nyhendebrev via MailerLite

Dette repoet kan sende nyhendebrev automatisk via MailerLite sin **nyaste plattform** (Connect API).

### Kva som skjer

- Scriptet les komande tilskipingar frå `_data/kalender.yml`
- Det sjekkar om **i dag = 7 dagar før neste folkemusikkpøbb** (standardregel)
- Om ja: det lagar ein kampanje i MailerLite og sender han til ei gruppe
- Om nei: det gjer ingenting (workflowen køyrer likevel dagleg)

### 1) Lag ei gruppe i MailerLite

I MailerLite:

- Gå til **Subscribers → Groups**
- Lag ei gruppe, t.d. `nyhendebrev`
- Legg mottakarar i gruppa (eller bygg påmelding på nettsida)

### 2) Hent API-token og Group ID

- Gå til **Integrations → API**
- Lag/bruk eit API-token
- Finn **Group ID** for gruppa di (same stad viser dei gjerne som ein ID)

### 3) Legg inn GitHub Secrets

I GitHub-repoet:

`Settings → Secrets and variables → Actions → New repository secret`

Legg inn:

- `MAILERLITE_API_TOKEN`
- `MAILERLITE_GROUP_ID`
- `MAILERLITE_FROM_EMAIL` (må vere verifisert i MailerLite)
- `MAILERLITE_FROM_NAME`
- `MAILERLITE_REPLY_TO` (valfri)

### 4) Testkøyr manuelt

Gå til **Actions → Send nyhendebrev (MailerLite)** og trykk **Run workflow**.

- **Vanleg køyr**: Scriptet sender berre om det er 7 dagar før neste pøbb; elles avsluttar det utan å sende.
- **Testutsending uansett dato**: Kryss av for **«Send uansett dato (test – sender også om det ikkje er 7 dagar før pøbb)»** før du trykkar Run workflow. Da sendes e-post likevel (bruk ei lita testgruppe om mogleg).

Du kan også køyre scriptet lokalt med `OSLOBYGDA_FORCE_SEND=1` (samt alle MAILERLITE_*-variablane) for å sende ein test.

### Vanlege feil

- **Frå-adressa er ikkje verifisert**: `MAILERLITE_FROM_EMAIL` må vere godkjent i MailerLite.
- **Plan/innhald**: API-et prøver å setje `emails[0].content` (HTML). Om kontoen din ikkje tillèt dette via API, vil MailerLite svare med 4xx/422. Då må ein anten oppgradere, eller byggje ei alternativ løysing (t.d. RSS-kampanje).

