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
- **Hovudmottakarar:** Brevo-lista «Nyhendebrev» (`BREVO_LIST_ID`). **Test:** slå på `bruk_test_lista` i workflow og bruk secret `BREVO_TEST_LIST_ID` (lista «Test» i Brevo) – sjå `skript/NYHENDEBREV.md`

Backup:
- MailerLite manuell/backup workflow: `.github/workflows/nyhendebrev.yml`
- MailerLite backup-script: `arkiv/mailerlite/send_nyhendebrev_mailerlite.rb`
- Tekstgenerator for manuell backup: `brev/tekstgenerator.md`

## Lisens

Sjå [LICENSE](LICENSE).

## Kalenderabonnement

Kalender- og pøbbsida har abonnementsknapp og rettleiing for kalenderappar:

Éin felles straum, `/kalender.ics`, inneheld alle tilskipingar.

Straumen blir bygd av `_tillegg/icalendar.html` frå `_data/kalender.yml` ved publisering.
Det trengst ingen ny teneste eller server. Kalenderappen hentar oppdateringar på
sitt eige tidspunkt. Straumen føreslår seks timar, men klienten kan bruke lengre tid.

Behald `uid` når ei hending blir flytta eller endra; elles kan abonnentar få duplikat.
Ved avlysing: behald hendinga og set `avlyst: true`, slik at ho blir merkt CANCELLED
i straumen. Ikkje fjern gamle hendingar berre fordi dei har vore; historikken vert
bevart for abonnentane. `sluttdato` kan nyttast for fleirdagshendingar; sluttklokkeslett
før startklokkeslett blir elles tolka som neste dag.

`webcal://` opnar kalenderabonnement der appen støttar det. Google Kalender og
andre appar kan i staden abonnere på den offentlege HTTPS-adressa. Nedlasting og
import av ei fil gir berre ein eingongskopi, ikkje automatisk oppdatering.

### Lokal førehandsvising på denne Mac-en

Start frå prosjektmappa:

    /opt/homebrew/opt/ruby/bin/ruby skript/forehandsvis.rb

Opne <http://localhost:4000/kalender/>. Skriptet byggjer nettsida automatisk ved
endringar; last nettlesarsida på nytt etter lagring. Ved endring av `_config.yml`
må skriptet startast på nytt. Stopp med Ctrl+C. Byggfiler ligg mellombels utanfor
prosjektmappa. Dette viser Jekyll-nettsida; Bygdelista er ein separat Flask-app.

### Tilskipingar frå Bygdelista

Styret kan leggje inn nye tilskipingar i det innlogga skjemaet `/tilskipingar`.
Sjå [oppsett og bruk](medlemsregister/TILSKIPINGAR.md). Publisering legg til ei rad
med fast UID i GitHub-datafila, slik at nettside, kalenderabonnement og nyhendebrev
brukar same kjelde. GitHub-token skal berre liggje i `.env` på PythonAnywhere.

Den offentlege kalendersida brukar `lutar/kalender.js` til å flytte hendingar til
historikken når sluttida i Oslo er passert, uavhengig av når sida sist vart bygd.
Kontroller klokkefiltreringa med `node skript/test_kalender.js`.

## Felles kode for nettsida og Bygdelista

Footeren har éi kjelde: `_tillegg/kolofon.html` og `lutar/kolofon.css`.
Jekyll inkluderer malen direkte; Flask les han med namnerommet `nettstad/` og
leverer same CSS-fil frå `/felles/kolofon.css`. Ikkje opprett kopiar under
`medlemsregister/fast/` eller `medlemsregister/malar/`. Ved driftsetjing må
`_tillegg/kolofon.html` og `lutar/kolofon.css` liggje på serveren saman med appen.

Python-avhengnadene står i `medlemsregister/requirements-common.txt`.
`requirements.txt` legg til SQLCipher for lokal bruk, medan
`requirements-pythonanywhere.txt` brukar den felles lista utan SQLCipher.
Dei eksisterande installasjonskommandoane fungerer som før.

Frå `medlemsregister/` kan testane køyrast mot mellombelse testdatabasar med
`python -m unittest discover -s tests`. Kalenderklokka har eigne kontrollar:
`node skript/test_kalender.js`. Ingen av desse sender e-post eller betalingar.

## Bilete, styre og dokument

- Legg JPG, PNG, WebP eller AVIF i `lutar/bilete/pobb/`. Alle bileta i mappa blir
  viste på pøbbsida ved neste Jekyll-bygg, sorterte etter filnamn. Bruk gjerne
  dato først i namnet. Det trengst ingen registrering av kvart bilete.
- Valfrie bildetekstar og meir presis alternativ tekst kan leggjast i
  `_data/pobb_bilete.yml`, med filnamnet som nøkkel.
- Endre `_data/styre.yml` for namn, rolle og biletestig. Eit manglande portrett
  viser initialar; legg bilete i `lutar/bilete/styret/` når dei er klare.
- Dokumentkorta på «Om laget» kjem frå `_data/dokument.yml`.
- `_data/nav.yml` er felles menydata. Mobil viser alle fire vala, utan nedtrekk.
- Forklaringa av «frilynt» står éin gong i footeren. `kontekstlenkje.html` kan
  brukast fleire stader på sida og opnar same forklaringsboks.

Gamle Brevo-skjema og MailerLite-skript er flytta til `arkiv/`, som ikkje blir
publisert av Jekyll. Den manuelle MailerLite-workflowen peikar til arkivstigen.
