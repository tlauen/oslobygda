# Bygdelista

Flask-app for medlemsadministrasjon, årsmøte og økonomi på `https://bygdelista.oslobygda.no`.
Den offentlege nettsida blir bygd separat med Jekyll, men menydata og footer
har éi felles kjelde i repoet.

## Funksjonar

- Personlege styrekontoar med passord, TOTP og e-poststadfesting.
- Medlemsliste, innbetalingar, medlemsår, eksport og personvernhandtering.
- Nye medlemmar på `/bli-medlem`: Vipps, stadfesta trekk og valfritt nyhendebrev.
- Årlege kontingentsatsar og personlege fornyingslenkjer med Vipps.
- Innmeldingsoversikt for styret på `/innmeldingar`.
- Oppretting og redigering av komande tilskipingar på `/tilskipingar`.
- Årsfesta styre med namn, verv og portrett på `/styret`.
- Strukturert årsmelding med kalenderimport og faste versjonar på `/arsmote`.
- Rekneskap, bilag, balanse og stegvis årsslutt på `/okonomi`.
- Budsjett og oppfølging på `/budsjett`.
- [Sakliste, møtereglar og protokoll med to godkjenningar](SAKLISTE.md) på `/sakliste`.
- Offentleg eksport, utskriftsvising og kryptert backup med gjenopprettingskontroll.

## Kodar på e-post

Innmelding, medlemsinnlogging, styrekontoregistrering og passordbyte bruker
ein eigen utsendingsarbeidar. Sjå [oppsett og utrulling](AUTH-EPOST.md).
Arbeidaren må vere i drift før denne kodeversjonen blir teken i bruk.

## Årsmøte, økonomi og drift

Start med [rekneskap](REKNESKAP.md), [årsdokument](ARSDOKUMENT.md) og
[budsjett](BUDSJETT.md). Sjå også [betalingsimport](BETALINGSIMPORT.md),
[publisering](PUBLISERING.md), [PDF/utskrift](UTSKRIFT.md) og [backup](BACKUP.md).
Medlems- og økonomidelane har eigne hjelpesider i appen.

Bruk [Nidarosbygda-rettleiinga](NIDAROSBYGDA-TEST.md) for isolert lokal prøving.
Testdata, testkonto og prøvedato skal ikkje overførast til produksjon.
Følg [UTRULLING.md](UTRULLING.md) og [PYTHONANYWHERE.md](PYTHONANYWHERE.md)
ved serveroppdatering. Nye funksjonar i Git er ikkje prov på at dei køyrer på serveren.

Styret-sida lagrar ei privat arbeidskjelde. Årsmeldinga hentar ein kopi for året;
nettsida blir oppdatert via nedlastbar nettsidepakke. Ordinær økonomibackup tek
med database, bilag, styredata og portrett. Produksjonskalender og kode blir
bevarte i Git; konfigurasjonsløyndomar må sikrast separat.

Gamle `/innmelding` sender vidare til det nye skjemaet. POST `/api/innmelding`
er avvikla (410) og har ingen e-post- eller kontakt-sideeffektar.

## Lokalt miljø

Bruk Python 3.10 eller nyare og eit eige virtuelt miljø. Felles avhengnader:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-common.txt
python app.py
```

`requirements-common.txt` bruker `requirements-lock.txt` til å låse både direkte
og transitive fellesavhengnader til kontrollerte produksjonsversjonar. Dette gjeld
òg PythonAnywhere og dokumentbygginga. Ved pakkeoppdatering: oppdater låsefila,
installer i eit nytt virtuelt miljø, køyr `python -m pip check` og heile
testsamlinga før utrulling. Ikkje bruk `pip freeze` frå eit generelt utviklingsmiljø;
uvante ekstra pakkar skal ikkje inn i produksjonslåsen. SQLCipher-tillegget i
`requirements.txt` er ei separat lokal avhengnad og inngår ikkje i denne låsen.

Dette startar lokalt på `127.0.0.1:5001`. For ein eksisterande SQLCipher-database,
installer `requirements.txt` og libsqlcipher. Appen nektar å opne databasen dersom
krypteringsnøkkel er sett utan driver, og migrerer ikkje automatisk frå ukryptert
SQLite. Ta backup og migrer alle tabellane særskilt ved behov.

Testane lagar mellombelse databasar. Dei sender ingen betalingar eller e-post:

```bash
python -m unittest discover -s tests
```

## Felles nettsidefiler

- `_data/nav.yml`: same fire menyval på nettsida og i innmeldingsflyten.
- `_tillegg/kolofon.html`: éin footer-mal med ordforklaring og logo.
- `lutar/kolofon.css`, `lutar/topp.css` og `lutar/arsmelding-tilskipingar.css`: felles CSS, levert under `/felles/`.

Desse filene må følgje med serverkoden. Ikkje kopier berre `medlemsregister/`.

## Integrasjonar og drift

- [PythonAnywhere](PYTHONANYWHERE.md): mappar, HTTPS og WSGI.
- [Vipps](VIPPS.md): testmiljø, webhook, reservejobb og produksjonsprøve.
- [Styrekontoar](STYREKONTOAR.md): oppretting og sperring.
- [Tilskipingar](TILSKIPINGAR.md): GitHub-tilgang og kalenderpublisering.
- [Backup](BACKUP.md): konsistent SQLite-backup og testa gjenoppretting.
- [Fornying](FORNYING.md): vedtak, opning av kontingentår og personlege lenkjer.
- [Medlemsår](HUSK_MEDLEMSAR.md): årsavslutning.

Løyndomar ligg berre i `.env` og `.env.vipps-test` (600), aldri i Git eller
nettlesaren. Oppsettsskript for Vipps, Brevo, SMTP og GitHub les nøklar skjult.
`requirements-common.txt` er felles, medan dei to andre pakkelistene legg til
miljøspesifikke avhengnader.

Brevo-utgang er berre for betalte produksjonsinnmeldingar som vel nyhendebrev.
`BREVO_INNMELDING_LIST_ID` peikar til nyhendebrevlista. Eventuell manuell import
frå Brevo krev ei eiga, uttrykkeleg `BREVO_MEDLEMMAR_LIST_ID`; appen fell aldri
tilbake til nyhendebrevlista som medlemsregister.

## Sletting og rekneskap

Ved sletting blir medlemsopplysningar, ordredetaljar og tilknytt styrekonto fjerna.
Dersom medlemmen har innbetalingar, blir ein post utan kontaktopplysningar bevart for at summer,
medlemsår og betalingsreferansar skal kunne avstemmast. Han blir ikkje vist som
medlem. Pågåande produksjonsbetalingar eller `review` må avklarast før sletting.

Sletting hos Brevo blir lagd i `privacy_jobs`; den timelege reservejobben prøver
igjen til leverandøren stadfestar sletting eller at kontakten ikkje finst. E-posten
blir fjerna frå køen etterpå. Eldre backupkopiar følgjer backup-rotasjonen og må
ikkje brukast til å reaktivere sletta medlemskap eller nyhendebrevabonnement.

## Formatering av betalingskoden

Ruff-versjonen er låst i `requirements-dev.txt`, utan å leggje formatteren til
produksjonskrava. Installer utviklingsmiljøet og køyr frå rota av repoet:

```bash
python -m pip install -r medlemsregister/requirements-dev.txt
ruff format .
ruff format --check .
```

`ruff.toml` avgrensar førebels formateringa til `ny_innmelding.py`,
`kontingent.py`, `betalingsstatus.py`, betalingsreglane og migreringsmodulen
med tilhøyrande nye testar.
Fleire modular kan takast inn i eigne,
mekaniske endringar. CI køyrer same formatkontroll før testsamlinga. Dette er
formatkontroll; lintreglar og automatiske kodeendringar er ikkje aktiverte.

## Databaseskjema

`init_db()` køyrer nummererte migreringar via `migreringar.py` og tabellen
`schema_migrations`. Versjon 1 tek opp både nye og eksisterande databasar med
dei historiske skjema-/dataoppgraderingane. Seinare oppstartar hoppar over dei.
TOTP-validering og ordinær oppdatering av betalingsstatus køyrer framleis ved
oppstart. Sjå [UTRULLING.md](UTRULLING.md) før produksjonsoppgradering.

Nye skjemaendringar skal vere nye `Migration`-steg i `init_db()` med neste
samanhengande versjonsnummer og eit fast, unikt namn. Ikkje endre ei brukt
migrering eller dei historiske `init_*`-funksjonane som utgjer baselinen.
Ein migrering får ei tilkopling til den ytre transaksjonen; ho skal ikkje
committe, lukke, starte ein eigen transaksjon eller opne andre tilkoplingar.
Bruk `execute`, `executemany` eller migreringstilkoplinga sin `executescript`.
SQL-setningar, inkludert triggerar, blir køyrde utan SQLite sitt implisitte
`executescript`-commit. Registrering av versjonen og alle ventande steg blir
committa samla. Ukjend, omdøypt eller ufullstendig historikk stoppar oppstarten.

## Felles betalingsreglar

`betalingsreglar.py` eig desimalkonvertering, beløpsgrenser og regelen for
medlemskategori. Den eksisterande manuelle medlemsføringa tillèt 0,01 til
1 milliard kroner; vår offentlege Vipps-flyt tillèt 1 til 1 million kroner.
Dette er ulike eksisterande bruksgrenser, ikkje ei endring av satsane eller ein
påstand om Vipps sine generelle grenser. Null er berre tillate når styret set
kategorigrensa. Delar av eit øre blir avviste, òg når ein svært lang
inputstreng elles kunne blitt avrunda av Decimal-konteksten.

`kul` krev strengt meir enn terskelen; lik terskel gir `vanleg`. Ein manuelt
sett `styret`-kategori blir bevart. Manuell føring bruker summen for det aktive
medlemsåret. Vipps-innmelding og fornying bruker satsen som er lagra på ordren;
refaktoreringa endrar ikkje kva medlemsår eller sats som blir lagt til grunn.
Maksimumsfeltet i dei offentlege betalingsskjemaa kjem frå same grense som
servervalideringa. Ingen skjemaendring eller databasemigrering er nødvendig.

## CSRF-vern og maskinkall

`csrf.py` krev nettlesarøkt og korrekt CSRF-token for alle endrande metodar som
standard. Unntak blir merkte med `@csrf_exempt` på sjølve view-funksjonen,
under ruteregistreringa (`@app.route`/`@app.post`). Rutenamn blir ikkje brukte
som unntaksliste. Vanlege skjema, innlogging, medlemsendringar og betalingar
skal framleis ha CSRF-vern.

Dei tre eksisterande unntaka er Vipps-webhooken (HMAC-signatur), protokollen
si maskinpublisering (eige Bearer-token), og det avvikla innmeldings-API-et
(svarer alltid 410 utan sideeffektar). Dekoratoren erstattar ikkje autentisering.
Nye unntak krev ei konkret grunngiving og testar som viser at alternativt vern
framleis avviser uautoriserte kall. Nye CSRF-modular og testar blir òg formaterte
med Ruff.

## Modulansvar

`app.py` set saman Flask-appen, databaseopnaren, migreringane og dei ulike
modulane. Styret sine medlemsruter ligg i `medlemsruter.py`, inkludert manuelle
betalingar, medlemsårsoversikt, CSV-eksport og innsyn/sletting. Registreringa
får databaseopnar, tilgangsvern og års-/betalingsfunksjonar som argument.
Rutene har dei same URL-ane og endepunktnamna som før.

`brevo.py` eig HTTP-transporten og `BrevoContacts` for nyhendebrev, sletting og
den månadlege API-kontrollen. Transport, databaseopnar og logger blir sende inn
slik at testar kan bruke fiktive svar utan nettverk. Mi side si varige
nyhendebrevkø bruker framleis `medlem_nyhendebrev.py` og same transport.
Ingen av dei to nye modulane importerer `app.py` eller opprettar database,
sender e-post eller kontaktar eksterne tenester ved import.

Denne oppdelinga endrar ikkje skjemaversjonen eller dei historiske
migreringane. `wsgi.py`, lokale testar og CLI brukar framleis same appinngang.
Dei nye modulane og testane er med i Ruff-formatkontrollen.

## Databasekontekstar og lokal teststart

Alle vanlege databasetilkoplingar og verktøya for backup, import, lesekontroll og
migrering bruker `database.managed_db`. Standardmodus committar ved normal
retur og rullar tilbake ved feil. `commit_on_success=False` blir brukt der
flyten eig eksplisitte commit-punkt: ferdige kontrollpunkt blir bevarte, men
uferdig arbeid blir rulla tilbake før tilkoplinga blir lukka, òg ved tidleg
retur. Skrivelåsar blir frigjevne utan å vente på søppelinnsamling. Den lånte
migreringstilkoplinga lèt den ytre migreringskøyraren eige heile transaksjonen.

Appen har inga særskild `BYGDELISTA_LOCAL_TEST`-grein. `lokal_test.py` fjernar
arva produksjonsinnstillingar, set python-dotenv si innebygde
`PYTHON_DOTENV_DISABLED=1` og installerer sperrer før appimport. Appen bruker
same kode for både drift og lokal testing. WSGI avviser framleis teststartaren
som eit ekstra vern mot å eksponere eit lokalt testmiljø i produksjon.
Python-dotenv-kravet er minst 1.2.4, som alt er låst og installert i produksjon.


## Offentleg kontingentoversikt

`GET /api/kontingent` leverer berre inneverande medlemsår, valuta og om
betaling er open; ved open produksjonsbetaling kjem minimumssats og
Superkul-grense i øre. Ruta bruker same `kontingent.payable` og vedtekne
`membership_periods` som innmeldingsskjemaet. Ho viser ikkje utkast,
framtidige vedtak, medlemsdata eller satsar frå eit eldre år som reserve.
Svaret blir ikkje mellomlagra og kan lesast utan innlogging frå nettsida.

Salsvilkåra bruker `_tillegg/kontingent.html` og `lutar/kontingent.js`.
Ved nettverksfeil eller utan JavaScript står ei lenkje til betalingsskjemaet
att; ingen fast eller gamal pris blir vist som reserve. Kallet sender ikkje
øktkjeks. Pris og medlemsår på ei oppretta betalingsordre blir ikkje endra.
Ingen databasemigrering eller nye Python-pakkar er nødvendige, men serverkoden
må oppdaterast og Web Reload køyrast før prisruta er tilgjengeleg.

## Sidetekstar på framsida og Om-sida

Under **Nettsida → Sidetekstar** kan styret redigere overskrifter, knappetekstar,
søkemotortekst og lengre Markdown-tekstar. Utkast blir lagra i den eksisterande
appdatabasen og følgjer databasebackupen. Førehandsvisinga viser formatert tekst,
ikkje heile nettsideutforminga. Kalender, styreoversikt, satsar og lenkjemål blir
ikkje endra av redigeraren.

Oppdater Python-pakkane før omlasting på PythonAnywhere, i appen sitt virtuelle
miljø og frå reporota:

```bash
python -m pip install -r medlemsregister/requirements-pythonanywhere.txt
```

Redigeraren bruker den låste Markdown-pakka. Publisering bruker eksisterande
`GITHUB_DOCUMENTS_TOKEN`, `GITHUB_DOCUMENTS_REPO` og `GITHUB_DOCUMENTS_BRANCH` frå
årsrapportpubliseringa, og treng skrivetilgang til `_data/sidetekstar.json` i
nettsiderepoet. Nøklar skal berre liggje i serveroppsettet. Utan oppsett kan styret
lagre utkast og førehandsvise, medan publiseringsknappen er deaktivert.

Publisering krev eit lagra, uendra utkast og eksplisitt stadfesting. GitHub si
filrevisjon hindrar overskriving ved samtidige endringar. Ei endring på den andre
sida blir bevart, og eit nytt forsøk etter uvisst nettverksutfall opprettar ikkje
same endring på nytt. Ved konflikt må brukaren ta vare på teksten og hente nyare
publisert tekst. Tidlegare publiserte versjonar ligg i Git-historikken; denne
første versjonen har ikkje ein eigen historikkveljar i redigeraren.

Markdown-HTML blir filtrert med ei lita tillatingsliste, og rå HTML, bilete og
Jekyll/Liquid-kode blir ikkje køyrde. `[[frilynt]]` i Om-teksten gir den faste
ordforklaringa. Nettsida brukar dei publiserte tekstfelta utan å tolke dei som
Jekyll-malar. Etter publisering må GitHub Pages byggje før endringa blir synleg;
kontroller den offentlege nettsida etterpå.
