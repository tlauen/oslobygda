## Nyhendebrev via MailerLite (gratis-modus aktiv)

Dette repoet kan sende nyhendebrev automatisk via MailerLite sin **nyaste plattform** (Connect API).
Gratis-modusen er aktiv no: scriptet sender ein ferdig kampanje-ID frå MailerLite UI.

### Kva som skjer

- Skriptet les komande tilskipingar frå `_data/kalender.yml`
- Det sjekkar om **i dag = 7 dagar før neste folkemusikkpøbb** (standardregel)
- Om ja: det sender ein eksisterande `draft/ready` kampanje i MailerLite (via ID)
- Om nei: det gjer ingenting (workflowen køyrer likevel dagleg)

### 1) Lag kampanjen i MailerLite (UI)

I MailerLite:

- Gå til **Campaigns**
- Lag ny kampanje med innhald i editoren (builder)
- Vel mottakarar
- La kampanjen stå i `draft` eller `ready` (ikkje send manuelt)

### 2) Hent API-token og Campaign ID

- Gå til **Integrations → API**
- Lag/bruk eit API-token
- Finn **Campaign ID** for kampanjen du vil sende (frå URL eller API-listing)

### 3) Legg inn GitHub Secrets

I GitHub-repoet:

`Settings → Secrets and variables → Actions → New repository secret`

Legg inn:

- `MAILERLITE_API_TOKEN`
- `MAILERLITE_READY_CAMPAIGN_ID`

### 4) Testkøyr manuelt

Gå til **Actions → Send nyhendebrev (MailerLite)** og trykk **Run workflow**.

- **Vanleg køyr**: Scriptet sender berre om det er 7 dagar før neste pøbb; elles avsluttar det utan å sende.
- **Testutsending uansett dato**: Kryss av for **«Send uansett dato (test – sender også om det ikkje er 7 dagar før pøbb)»** før du trykkar Run workflow. Då blir e-post send likevel (bruk ei lita testgruppe om mogleg).

Du kan også køyre skriptet lokalt med `OSLOBYGDA_FORCE_SEND=1` (samt variablane over) for å sende ein test.

### Dvale: Advanced-varianten

Den gamle fullauto-varianten med generering av HTML via API er lagra i:

- `skript/send_nyhendebrev_mailerlite_advanced.rb`

Denne krev Advanced-plan (`emails[].content` via API). Han er lagt i dvale no.

### Vanlege feil

- **Feil campaign ID**: sjekk at `MAILERLITE_READY_CAMPAIGN_ID` peikar på ein eksisterande kampanje i kontoen til API-tokenet.
- **Campaign kan ikkje sendast (422)**: kampanjen må ha ferdig innhald og mottakarar i MailerLite UI før workflowen køyrer.
- **Allereie sendt**: scriptet avsluttar utan feil om kampanjen allereie er sendt.

