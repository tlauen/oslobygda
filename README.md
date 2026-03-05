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

## Lisens

Sjå [LICENSE](LICENSE).
