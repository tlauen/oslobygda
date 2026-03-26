## Fullauto nyhendebrev via MailerLite

Dette repoet kan sende nyhendebrev automatisk via MailerLite sin **nyaste plattform** (Connect API).

### Kva som skjer

- Skriptet les komande tilskipingar frå `_data/kalender.yml`
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
- **Testutsending uansett dato**: Kryss av for **«Send uansett dato (test – sender også om det ikkje er 7 dagar før pøbb)»** før du trykkar Run workflow. Då blir e-post send likevel (bruk ei lita testgruppe om mogleg).

Du kan også køyre skriptet lokalt med `OSLOBYGDA_FORCE_SEND=1` (samt alle MAILERLITE_*-variablane) for å sende ein test.

### Design og stil

E-posten som blir send automatisk, bruker same **fargepalett og typografi** som nettsida (pastell: bakgrunn #FCF9F3, tekst #12110e, aksent #2f5d50 / #BFEAEE). HTML-en byggjest i skriptet (`send_nyhendebrev_mailerlite.rb`), så endringar av utsjånad gjer du der (eller ved å redigere variablane øvst i skriptet).

**MailerLite-mal:** Du kan lage ein **mal** i MailerLite (Campaigns → Templates) med same stil – nyttig for manuelle kampanjar og som referanse. Det automatiske nyhendebrevet bruker ikkje malen (API-et sender ferdig HTML), men du kan kopiere fargar og oppsett frå malen inn i skriptet om du vil halde alt likt.

**Logo i e-posten:** Nyhendebrevet bruker `lutar/bilete/logo_oslobygda.png` (200×200 px) nederst. PNG er meir kompatibel enn SVG i e-postklientar (Outlook, Gmail osb.). Lag fila ved å eksportere/konvertere frå `logo_oslobygda.svg` (200×200 px eller større for skarpt bilete), og legg han i `lutar/bilete/`. Utan PNG vil logoen ikkje visast (lenka peikar berre på .png).

### Vanlege feil

- **Frå-adressa er ikkje verifisert**: `MAILERLITE_FROM_EMAIL` må vere godkjent i MailerLite.
- **404 «Resource does not exist»** ved oppretting av kampanje: Scriptet sjekkar no at `MAILERLITE_GROUP_ID` finst i kontoen din. Om den ikkje gjer det, får du ei feilmelding som viser gyldige gruppe-ID-ar. Hent gruppe-ID i MailerLite under **Integrations → API** (eller **Subscribers → Groups** – ID står i URL eller gruppeinnstillingar). Bruk alltid tal/ID som høyrer til same konto som API-tokenet.
- **Plan/innhald**: API-et prøver å setje `emails[0].content` (HTML). Om kontoen din ikkje tillèt dette via API, vil MailerLite svare med 4xx/422. Då må ein anten oppgradere, eller byggje ei alternativ løysing (t.d. RSS-kampanje).

