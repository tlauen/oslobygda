# oslobygda

Nettside for Oslobygda kulturlag (`oslobygda.no`), med informasjon om arrangement, kalender og praktisk kontaktinfo.

## Kva nettsida er

`oslobygda` er nettsida for eit lokalt kulturmiljø i Oslo. Prosjektet brukar Jekyll med sider, includes og datafiler for å halde innhald lett å vedlikehalde.

## Teknologi

- Jekyll (GitHub Pages-kompatibel)
- Markdown + HTML-layouts
- YAML-data i `_data/`

## Viktige mapper/filer

- `_config.yml`: Jekyll-konfigurasjon
- `_layouts/`: sidemalar
- `_includes/`: gjenbrukbare komponentar
- `_data/`: strukturerte data
- `kalender/`: kalendersider
- `assets/`: CSS, bilete og statiske ressursar
- `index.md`: framside
- `kalender.ics`: kalender-feed
- `CNAME`: custom domene

## Lokal utvikling

Installer avhengigheiter:

```bash
bundle install
```

Start lokal server:

```bash
bundle exec jekyll serve
```

Opne `http://localhost:4000/`.

## Publisering

Repoet er sett opp for GitHub Pages/Jekyll. Push til hovudbranch publiserer ny versjon når Pages er aktivert i repo-innstillingar.

## Nyhendebrev (full auto via MailerLite)

Repoet kan sende nyhendebrev automatisk via **MailerLite (ny plattform)** og GitHub Actions.

- **Workflow**: `.github/workflows/nyhendebrev.yml`
- **Script**: `scripts/send_nyhendebrev_mailerlite.rb`
- **Innhald**: blir generert frå `_data/kalender.yml` (komande tilskipingar)
- **Utsendingstidspunkt**: scriptet sender berre når det er **7 dagar før neste** tilskiping som matchar `TRIGGER_UID_CONTAINS` (standard `pobb-`)

### Secrets som må setjast i GitHub

Gå til `Settings → Secrets and variables → Actions` i repoet og legg inn:

- **`MAILERLITE_API_TOKEN`**: API-token frå MailerLite
- **`MAILERLITE_GROUP_ID`**: Gruppe-ID mottakarane ligg i (finn under `Integrations → API` i MailerLite)
- **`MAILERLITE_FROM_EMAIL`**: avsendaradresse (må vere verifisert i MailerLite)
- **`MAILERLITE_FROM_NAME`**: avsendar-namn
- **`MAILERLITE_REPLY_TO`** (valfri): svar-til-adresse

### Tilpassing

Du kan endre desse i `.github/workflows/nyhendebrev.yml`:

- **`TRIGGER_UID_CONTAINS`**: kva type tilskiping som triggar utsending (t.d. `pobb-`)
- **`DAYS_BEFORE_TRIGGER`**: kor mange dagar før trigger-tilskipinga ein sender
- **`UPCOMING_LIMIT`**: kor mange komande tilskipingar som blir lista i brevet

## Lisens

Sjå [LICENSE](LICENSE).
