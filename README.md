# oslobygda

Nettside for Oslobygda kulturlag (`oslobygda.no`) bygga med **Jekyll**.

Denne README-en forklarer kva ein utanfrå bør vite: kva som er statisk Jekyll-innhald, kva som blir generert av data, og at `medlemsregister/` er ein separat Flask-app som må setjast i drift for seg.

## Kva nettsida er (i praksis)

- **Jekyll** byggjer sidene til GitHub Pages (ingen eigen build-server nødvendig)
- Innhald er stort sett i `*.md` (frontmatter + Markdown) og inkluderer felles HTML-komponentar
- Kalender og abonnement blir styrt av datafiler (sjå `_data/` og `kalender/`)
- **Medlemsregisteret** er ikkje ein del av Jekyll-bygget: det er ein separat **Flask-app** i `medlemsregister/`

## Teknologi

- Jekyll (GitHub Pages-kompatibel)
- Markdown + `_utforming/` (sidemalar) + `_tillegg/` (gjenbruk)
- YAML-data i `_data/`

## Viktige mapper og sider

- `_config.yml`: Jekyll-konfig (inkl. kven som blir ekskludert frå bygg)
- `_utforming/`: sidemalar
- `_tillegg/`: gjenbrukbare HTML-komponentar
- `_data/`: data som driv ting som kalender/templating
- `kalender/`: sida “Kalender” + historikk (del av statisk innhald)
- `lutar/`: stilar/bilete/andre statiske ressursar
- `index.md`: framside
- `kalender.ics`: kalender-feed
- `medlemsregister.md`: statisk side på oslobygda.no med lenker til Flask-appen

## Medlemsregister (Flask-app)

- `medlemsregister/` inneheld ein **Flask-app** (Bygdelista) med styregrensesnitt og offentleg innmeldingsskjema.
- Jekyll ekskluderer Python-delen frå bygg (`exclude: ["medlemsregister"]` i `_config.yml`).
- Den statiske sida `medlemsregister.md` brukar ein konfigverdi (`medlemsregister_url`) for å peike inn til Flask-appen når han er sett i drift.

## Lokal utvikling

1. Installer avhengnader:

```bash
bundle install
```

2. Start lokal server:

```bash
bundle exec jekyll serve
```

Opne `http://localhost:4000/`.

## Publisering

Når du pushar til riktig branch, blir GitHub Pages oppdatert (Jekyll byggjer statiske sider).

Eige domene blir styrt av `CNAME`.

## Nyhendebrev (Brevo + GitHub Actions)

Det finst no ein fullauto-flyt som sender nyhendebrev via Brevo API:

- Aktiv workflow: `.github/workflows/nyhendebrev-brevo.yml`
- Aktivt script: `skript/send_nyhendebrev_brevo.rb`
- Innhald: blir generert frå `_data/kalender.yml` (same mal som tidlegare fullauto)
- Utsending: automatisk når det er “7 dagar før neste” arrangement (kan tvangskøyrast manuelt)

Backup:
- MailerLite manuell/backup workflow: `.github/workflows/nyhendebrev.yml`
- MailerLite backup-script: `skript/send_nyhendebrev_mailerlite.rb`
- Tekstgenerator for manuell backup: `brev/tekstgenerator.md`

## Lisens

Sjå [LICENSE](LICENSE).
