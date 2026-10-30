# Oslobygda kulturlag

Repoet inneheld nettsida på <https://oslobygda.no> og medlemsregisteret
**Bygdelista** på <https://bygdelista.oslobygda.no>. Dei deler nokre malar og
stilar, men blir køyrde og publiserte kvar for seg.

## Kva som er bygd

- **Nettsida:** Jekyll genererer statisk HTML frå Markdown, Liquid, YAML og SCSS.
  Ho har framside, tilskipingskalender med historikk og abonnement, pøbbgalleri,
  informasjon om laget, styret, lover, dokument og kontaktinformasjon.
- **Bygdelista:** Flask og SQLite på PythonAnywhere. Personlege styrekontoar med
  passord, TOTP og e-poststadfesting; medlemsliste, betalingar, eksport,
  årsavslutting og personvernsletting. Offentleg innmelding og personleg fornying
  med Vipps, stadfestingsmail og valfritt nyhendebrev. Styret kan publisere
  tilskipingar til kalenderdatafila gjennom GitHub API.
- **Nyhendebrev:** GitHub Actions køyrer eit Ruby-skript dagleg. Brevo sender
  brevet sju dagar før neste ikkje-avlyste pøbb med `pobb-` i UID-en.
  Kalenderen er felles datakjelde for nettside, kalenderabonnement og brev.

## Årsmøte og økonomi i Bygdelista

- **Årsmelding:** hent tilskipingar frå kalenderen, stadfest gjennomføring eller
  avlysing, legg til gjesteoverslag og tekst, og hent styret for rapportåret.
  Nøkkeltal og portrett blir viste i førehandsvising og PDF.
- **Rekneskap og bilag:** spørsmålsbasert føring, Vipps-oppgjer, private utlegg,
  balanse, retting ved reversering og privat dokumentlagring. Årssluttslista viser
  kva saldokontrollar som er ferdige og kva som står att.
- **Budsjett:** utkast, samanlikning med rekneskap og faste versjonar.
- **Styret:** årsfesta registrering av namn, verv og portrett. Årsmeldinga lagrar
  ein kopi; seinare endringar i styret endrar ikkje gamle dokumentkopiar.
- **Offentleg vising:** berre tillatne felt blir eksporterte. Medlemspengar blir
  viste samla; medlemsidentitetar, interne merknader og originalbilag er interne.
  Kølegging er ikkje det same som stadfesta offentleg publisering.

Kode for dette er slått saman til `main`. Det betyr ikkje at PythonAnywhere er
oppdatert eller at integrasjonar er aktiverte. Følg
[utrullingsplanen](medlemsregister/UTRULLING.md) før serveroppdatering.

### Rettleiingar

- [Årsdokument og versjonar](medlemsregister/ARSDOKUMENT.md)
- [Rekneskap og bilag](medlemsregister/REKNESKAP.md)
- [Budsjett](medlemsregister/BUDSJETT.md)
- [Medlemsbetaling og kjeldekontroll](medlemsregister/BETALINGSIMPORT.md)
- [Offentleg publisering](medlemsregister/PUBLISERING.md)
- [Utskrift og PDF](medlemsregister/UTSKRIFT.md)
- [Backup og kryptert eksport](medlemsregister/BACKUP.md)
- [Isolert lokal prøving med Nidarosbygda](medlemsregister/NIDAROSBYGDA-TEST.md)
- [Sluttkontroll](medlemsregister/SLUTTKONTROLL.md) og
  [kontrollert utrulling](medlemsregister/UTRULLING.md)

Hjelpesidene inne i Bygdelista forklarer den daglege arbeidsrekkjefølgja.
Styret-sida gir ein nedlastbar nettsidepakke; ho publiserer ikkje automatisk til
GitHub. Offentleg årsmeldingseksport er tekstbasert; intern vising og PDF bruker
utforminga med nøkkeltal og bilete.

## Finn fram og endre innhald

- `index.md` og undermapper med `index.md`: sidetekst og sidemetadata.
- `_data/kalender.yml`: alle tilskipingar, også historiske.
- `_data/nav.yml`: felles meny for nettsida og innmeldingsflyten.
- `_data/styre.yml`: årsfesta styre med namn, verv, portrett og gjeldande styreår.
- `_data/dokument.yml`: dokumentkort på «Om laget».
- `_utforming/`: sidemalar. `_tillegg/`: gjenbrukbare Liquid-/HTML-komponentar.
- `lutar/stilar.scss` og `lutar/stilar/`: stilane til nettsida.
- `lutar/topp.css` og `lutar/kolofon.css`: felles stil for topp og footer.
- `lutar/bilete/pobb/`: alle JPG-, PNG-, WebP- og AVIF-bilete blir viste i
  pøbbgalleriet, sorterte etter filnamn. Bruk gjerne dato først.
  `_data/pobb_bilete.yml` gir valfrie bildetekstar og alternativ tekst.
- `lutar/bilete/styret/` og `lutar/dokument/`: portrett og nedlastbare dokument.
- `_config.yml`: domene, språk, eksterne appadresser og byggjeinnstillingar.
- `kalender.ics` og `_tillegg/icalendar.html`: kalenderstraumen.
- `api/tilskipingar.json` og `.txt`: statiske tilskipingseksportar frå same data.
- `medlemsregister/`: Python-kode, eigne HTML-malar, CSS, testar og driftsrettleiingar.
- `skript/`: lokal førehandsvising, nyhendebrev, oppdatering av Bygdelista og testar.

Jekyll les malar frå `_utforming/` og komponentar frå `_tillegg/`, slik det er
sett i `_config.yml`. `medlemsregister/`, `skript/` og `arkiv/` er ekskluderte
frå nettsidebygget. `_site/` er generert utdata og skal ikkje redigerast.

### Kalender

Behald `uid` når ei tilskiping blir flytta eller endra; elles kan abonnentar
få duplikat. Ved avlysing: behald rada og set `avlyst: true`. Behald historiske
tilskipingar. `sluttdato` kan brukast for fleire dagar; sluttklokkeslett før start
blir elles tolka som neste dag. `lutar/kalender.js` flyttar avslutta hendingar til
historikken etter Oslo-tid, også mellom Jekyll-bygg.

`/kalender.ics` omfattar alle tilskipingar. Abonnement via HTTPS eller `webcal://`
blir oppdatert når kalenderappen hentar straumen; filimport gir berre ein kopi.
Straumen føreslår seks timar mellom oppdateringar, men klienten avgjer sjølv.
Styret kan òg bruke [tilskipingsskjemaet i Bygdelista](medlemsregister/TILSKIPINGAR.md).

## Lokal utvikling og kontroll

Frå rotmappa, med Ruby og Bundler installerte:

```bash
bundle install
bundle exec ruby skript/forehandsvis.rb
```

Opne <http://localhost:4000/>. Skriptet byggjer på nytt ved filendringar;
last nettlesarsida på nytt. Start skriptet på nytt ved endring i `_config.yml`.
Stopp med Ctrl+C. Byggfiler blir lagra mellombels utanfor repoet.
På Mac-en dette vart utvikla på kan Homebrew Ruby brukast direkte:
`/opt/homebrew/opt/ruby/bin/ruby skript/forehandsvis.rb`.

[Bygdelista sin README](medlemsregister/README.md) forklarer Python-miljø og lokal
oppstart. Ein lokal Jekyll-server startar ikkje Flask-appen; innmeldingslenkjene
peikar som standard til produksjon.

Kontrollar frå rotmappa:

```bash
node skript/test_kalender.js
ruby skript/test_nyhendebrev.rb
python3 -m unittest discover -s skript -p 'test_*.py'
cd medlemsregister
python -m unittest discover -s tests
```

Python-testane krev appavhengnadene i eit virtuelt miljø. Testane bruker
mellombelse databasar og simulerte integrasjonar og sender ikkje betalingar eller
e-post. Bruk Homebrew Ruby dersom system-Ruby er for gammal.

## Publisering og drift

**Nettsida:** push til `main` er den etablerte GitHub Pages-flyten. Pages-kjelde
og publiseringsstatus blir administrerte under GitHub → Settings → Pages og
Actions; det ligg ingen eigen Pages-workflow i repoet. `CNAME` set domenet.

**Bygdelista:** ein push oppdaterer ikkje PythonAnywhere-appen. Følg
[oppdateringsrutinen](medlemsregister/PYTHONANYWHERE.md): køyr oppdateringsskriptet
på serveren og deretter Web → Reload. Skriptet tek kodebackup og kopierer berre
kode og godkjende fellesfiler; database og løyndomar blir verande på serveren.
Endra Python-avhengnader må installerast før Reload.

**Fellesfiler:** Flask les `_data/nav.yml` og `_tillegg/kolofon.html` frå repoet
og leverer `lutar/kolofon.css` og `lutar/topp.css` under `/felles/`.
Desse må følgje med appen. Ikkje lag eigne kopiar i Flask-mappene.

**Nyhendebrev:** `.github/workflows/nyhendebrev-brevo.yml` køyrer dagleg kl. 07.19
UTC og kan startast manuelt. Testliste og tvungen sending blir valde i Actions.
Sjå [nøklar, mottakarlister og utsending](skript/NYHENDEBREV.md).
`brev/tekstgenerator.md` er eit separat hjelpemiddel for manuell tekst.

## Overlevering til ny ansvarleg

Overfør tilgang gjennom tenestene og ein trygg passorddelar, aldri gjennom Git:

- GitHub-repoet, Pages-innstillingar og Actions-secrets for Brevo.
- Domeneforvaltar/DNS og PythonAnywhere-kontoen `oslobygda` (EU).
- Vipps, Brevo og SMTP-kontoen som sender stadfestings- og innloggingsmail.
- Personleg styrekonto i Bygdelista og tilgang til tryggingskopiar.

Løyndomar og medlemsdata er ikkje del av repoet. Bygdelista les `.env` på serveren;
Vipps-test brukar eiga `.env.vipps-test`. Behald filrettar 600. Kontroller at
backup- og vedlikehaldsoppgåvene på PythonAnywhere køyrer, og prøv gjenoppretting
av ein kopi før du treng henne. Sjå [backuprettleiinga](medlemsregister/BACKUP.md).

Start med [Bygdelista](medlemsregister/README.md), deretter
[PythonAnywhere](medlemsregister/PYTHONANYWHERE.md),
[styrekontoar](medlemsregister/STYREKONTOAR.md), [Vipps](medlemsregister/VIPPS.md)
og [årlege satsar og fornying](medlemsregister/FORNYING.md).
Årsavslutting og opning av nytt kontingentår er separate handlingar.
2027 er stengt utan vedtekne satsar. Full fornyingsprøve med Vipps-testappen
står att før første verkelege kontingentutsending; nytt profilsamtykke frå Vipps
må òg kontrollerast i ein ny betalingsflyt.

## Eldre filer og valfrie verktøy

`arkiv/brevo-skjema/` inneheld utgåtte skjema. Dei blir ikkje publiserte eller
brukte av den aktive innmeldinga. Historikken finst i Git.
`skript/forehandsvising_nyhendebrev.html` er ei manuell skisse med eksempeldata,
ikkje ei generert førehandsvising av neste utsending.
`skript/publiser_nye_tilskipingar_til_folkarr_aktivioslo.py` er eit separat
Playwright-verktøy med `publisering_krav.txt`; ingen workflow køyrer det.
Det har plattformavhengige skjema og må kontrollerast før eventuell bruk.

## Lisens

Sjå [LICENSE](LICENSE).

### Felles dokumentvising og PDF

Årsmelding, rekneskap og budsjett bruker same dokumentmal i Bygdelista og på
nettsida. `medlemsregister/dokumentvising.py` tek berre imot den validerte
offentlege eksporten og lagar sjølvstendig HTML med dokumentstilane innebygde.
Førehandvisinga er isolert frå menyane sine stilark.

Etter publisering byggjer GitHub Actions (`arsdokument.yml`) HTML og ekte
A4-PDF-ar frå `_data/arsdokument/`. Filene ligg i `lutar/arsdokument/ÅR/`.
Nettsida viser HTML-fila og lenkjer til PDF-en frå same bygg. Bygginga kan ta
nokre minutt. Inntil filene er klare, viser sida den eksisterande eksporten.
Originalbilag, medlemsnamn og interne notat blir ikkje sende til PDF-jobben.

Lokal kontroll: installer `requirements-common.txt` og `playwright`, køyr
`python -m playwright install chromium` og `python skript/bygg_arsdokument.py`.
Bygdelista sine faste dokument blir ikkje endra i databasen av dette.
