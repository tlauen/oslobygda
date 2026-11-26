# Gjeremålsliste etter kodegjennomgang av Oslobygda

Status 25. november 2026, kjeldekode ved Git-versjon `9777901`.
Samlar den breie kodegjennomgangen, Security Review og Bugbot. Dei fem første
oppgåvene gjeld stadfesta feil; resten gjeld testdekning og vedlikehald.
Oppdatert 26. november 2026: Punkt 1–13 er implementerte lokalt, og den samla
lokale sluttkontrollen i punkt 14 er gjennomført. Ingen produksjonsutrulling er utført.
Den nye e-postarbeidaren må setjast opp før denne kodeversjonen blir teken i bruk;
sjå `medlemsregister/AUTH-EPOST.md`.

Prioriteringsrekkjefølgja er 1–5 før større omstrukturering. Alle fem feil er
vurderte som P2: dei bør rettast, men gjennomgangen har ikkje stadfesta eit
kritisk innbrot eller ei generell omgåing av styreinnlogginga.

## Stadfesta feil

- [x] **1. Hindre at ein ustadfesta kladd sperrar andre si e-postadresse.**
  Kjelde: Security Review. `medlemsregister/ny_innmelding.py:209–219` og
  `medlemsregister/personvern_vedlikehald.py:122–129`.
  Ein uinnlogga person kan opprette ein `new`-ordre med ei anna si adresse,
  utan e-poststadfesting eller betaling. Den rette eigaren blir deretter avvist,
  også frå ein annan nettlesar og IP. Opprydding av ubrukte kladdar skjer etter
  30 dagar. Reprodusert med fiktive data.
  **Tiltak:** La ikkje ein ustadfesta kladd reservere adressa globalt. Skil dette
  frå vernet mot doble, faktisk påbegynte betalingar.
  **Ferdig når:** Eigaren kan starte innmelding trass i ein annan sin ubetalte
  kladd, medan gjentekne betalingsforsøk framleis ikkje gir doble trekk.
  Legg til testar for begge tilfella.
  **Utført 26. november:** Kladdar utan betalingsforsøk blokkerer ikkje ny
  innmelding eller redigering. Betalingsstart les ordren og reserverer adressa
  under same skrivelås. Testar dekkjer to konkurrerande kladdar, samtidig
  betalingsstart, uvisst Vipps-svar og frigjering etter stadfesta utløp.
  Alle 304 Python-testar og gjeldande formatkontroll bestod. Ingen utrulling.

- [x] **2. Lese og låse same ordreversjon ved betalingsstart.**
  Kjelde: Bugbot. `medlemsregister/ny_innmelding.py:385–442`.
  `create()` les ordren før `BEGIN IMMEDIATE`. Ei samtidig gyldig redigering
  kan endre beløpet før betalingsstarten tek låsen. Ved simulert endring frå
  100 til 200 kroner vart Vipps kalla med 100 kroner, medan databasen hadde
  200 kroner og `create_attempted=1`. Seinare beløpskontroll avviser samsvaret.
  **Tiltak:** Les ordren på nytt i transaksjonen som validerer og markerer
  betalingsstart. Ta eit konsistent øyeblikksbilete før nettverkskallet.
  **Ferdig når:** Ein deterministisk samtidstest viser at redigering anten
  vinn før betalingsstart og gir rett beløp, eller blir avvist etter at start
  er markert. Bevar idempotens og handtering av uvisse leverandørsvar.

  **Utført 26. november:** Betalingsstart les ordren under låsen. Ein deterministisk test legg ei gyldig beløpsendring inn før låsen og kontrollerer rett API-beløp; redigering etter reservasjon blir avvist.

- [x] **3. Samordne administrativt e-postbyte med ventande utsendingar.**
  Kjelde: Bugbot. `medlemsregister/medlemsruter.py:194–202`.
  Styret kan rette adressa på medlemmen utan å rette mottakaren i ventande
  innmeldingsstadfestingar. Reprodusert: etter adressebytet fekk den simulerte
  stadfestingssendaren framleis den gamle adressa. Medlemmen sin eigen
  e-postbyteflyt oppdaterer desse ordrane i `medlem_auth.py:208–213`.
  **Tiltak:** Bruk felles samordning av adressebyte for styret og Mi side,
  med uttrykkelege reglar for pågåande betaling, sending og usikker levering.
  Ta med tilbakekalling av tilgang og handtering av nyhendebrevkøer.
  **Ferdig når:** Ei ventande stadfesting går til den retta adressa, og ei
  samtidig eller uavklart sending blir handtert utan feil mottakar eller
  ukontrollert ny sending. Test både styreflyten og Mi side.

  **Utført 26. november:** Styret og Mi side bruker no same adresseoppdatering. Ventande stadfestingar blir retta; pågåande betaling og sending med uavklart utfall sperrar endringa. Gamle kodar, tilgang og nyhendebrevjobbar blir handterte samla.

- [x] **4. Skil profilredigering frå manuell godkjenning av betalt medlemsår.**
  Kjelde: Bugbot. `medlemsregister/medlemsruter.py:180–184` og
  `medlemsregister/malar/index.html:538–548`.
  Skjemaet sender alltid betalingsstatus. Når styret berre endrar telefonen på
  ein betalt medlem, blir det òg oppretta ei manuell godkjenning i
  `paid_membership_years`. Reprodusert: etter sletting av den manuelle
  betalingsposten viste medlemsrada «ikkje betalt», medan `member_paid()`
  framleis var sann. Mi side kan dermed sperre ny betaling.
  **Tiltak:** Gjer manuell godkjenning til ei uttrykkeleg handling. Vanleg
  lagring av kontaktopplysningar skal ikkje opprette eit medlemsårsvedtak.
  **Ferdig når:** Profilredigering ikkje lagar godkjenningar; sletting av siste
  betaling gir konsekvent status i medlemslista og Mi side dersom ingen
  reell manuell godkjenning finst. Bevar medvitne gratis- og betaltvedtak.

  **Utført 26. november:** Eit fullt profilskjema med uendra status opprettar ikkje vedtak. Statusendring, eit uttrykkeleg statuskall eller den nye avkryssinga gir manuelt vedtak. Regresjonstesten slettar siste betaling etter telefonretting og kontrollerer både medlemsrada og medlemsårsdekninga.

- [x] **5. Redusere røping av medlemskap gjennom offentlege skjema.**
  Kjelde: Security Review. `medlemsregister/ny_innmelding.py:209–219` og
  `medlemsregister/medlem_auth.py:112–125`.
  Innmelding gir ulikt svar for registrert adresse/ventande ordre og ukjend
  adresse. Innlogging gir lik svartekst, men berre kjende medlemmar ventar på
  synkron SMTP. Simulert SMTP-forseinking gav tilsvarande skilnad i svartid.
  Styrekontoregistrering og passordreset har same utsendingsmønster.
  **Tiltak:** Samordne med oppgåve 1. Gje generiske offentlege svar og legg
  utsending i ei varig kø, utan å gjere HTTP-svartida avhengig av medlemskap.
  **Ferdig når:** Svarinnhald, status og omdirigering ikkje røper registrering,
  og HTTP-førespurnaden ikkje ventar på SMTP berre for kjende adresser.
  Test med simulert treg eller utilgjengeleg SMTP; bevar rategrenser og
  nettlesarbundne eingongskodar.

  **Utført 26. november:** Offentleg innmelding tek imot kladdar utan å røpe medlemsstatus, og krev nettlesarbunden e-postkode før betalingsavklaring. Innlogging, styrekontoregistrering, passordreset og innmelding legg kodar i ei varig, kryptert kø. HTTP-rutene sender ikkje SMTP. Arbeidaren kontrollerer gyldigheit og reserverer jobbar atomisk. Migrering 2 og driftsrettleiing er lagde til. Arbeidaren er ikkje starta i produksjon.

## Testdekning før større opprydding

- [x] **6. Køyr alle eksisterande testgrupper i CI.**
  `.github/workflows/python-tests.yml:5–22,41–49` køyrer medlemsregistertestane
  og prisvisingstesten, men arbeidsflytane køyrer ikkje kalender-,
  nyhendebrev- eller oppdateringsskripttestane.
  **Tiltak:** Ta med `skript/test_kalender.js`, `skript/test_nyhendebrev.rb`
  og `skript/test_oppdater_bygdelista.py`, med rett Python-sti og moderne Ruby.
  Utvid utløysingsstiane slik at endringar i skripta og testane startar kontroll.
  **Ferdig når:** Ei relevant endring under `skript/` utløyser rett testgruppe,
  og alle gruppene blir køyrde utan produksjonsløyndomar eller eksterne kall.

  **Utført 26. november:** CI omfattar no alle skriptendringar, kalenderkontroll, nyhendebrev med Ruby 3.3 og Python-testane av serveroppdateraren.

## Lesbarheit og struktur

- [x] **7. Formater dei tettpakka HTML-malane.**
  Start med `medlemsregister/malar/okonomi.html` og `arsmote_utskrift.html`.
  Økonomimalen har linjer på over 3 000 teikn.
  **Tiltak:** Bruk normale linjeskift og innrykk. Del økonomimalen etter
  oversikt, registrering, bilag og avstemming der dette gir klare ansvar.
  **Ferdig når:** Nestinga kan lesast direkte, og rendera skjema, felt,
  CSRF-vern og vising er kontrollerte etter endringa.

  **Utført 26. november:** Økonomimalen er delt i fire namngjevne delar og formatert. Utskriftsmalen har fått linjeskift og innrykk. Økonomioversikt og registreringsskjema er prøvde i lokal Safari.

- [x] **8. Flytt JavaScript ut av medlemslistemalen.**
  `medlemsregister/malar/index.html` har 761 linjer, med ein JavaScript-blokk
  på om lag 575 linjer frå linje 183.
  **Tiltak:** Flytt oppførselen til `fast/medlemsliste.js`. Send nødvendig
  konfigurasjon og CSRF-token frå malen gjennom eit lite, tydeleg grensesnitt.
  Del eventuelt vidare etter tabell, profilskjema og betalingsdialog.
  **Ferdig når:** Medlemsliste, profilendring, betalingshistorikk, eksport og
  feilvising fungerer, også med URL-prefiks. Bevar escaping av medlemsdata.

  **Utført 26. november:** Medlemslista bruker `fast/medlemsliste.js` og les CSRF-token og API-prefiks frå escapede meta-felt. Lasting og lagring av ein fiktiv medlem er prøvd i Safari; prefikskonfigurasjonen er testa.

- [x] **9. Del innmeldingsfila etter ansvar.**
  `medlemsregister/ny_innmelding.py` har 1 208 linjer med skjema, validering,
  betalingsteneste, e-postoppfølging, nettruter og driftskommandoar.
  **Tiltak:** Etter oppgåve 1–5: skil først ut nettruter og CLI-kommandoar.
  Hald transaksjonar og betalingsstatus samla til ansvarsgrensene er tydelege.
  **Ferdig når:** Filene har klare ansvar, ingen nye sirkulære importbehov,
  og betalings-, fornyings-, webhook- og samtidstestane framleis består.

  **Utført 26. november:** Nettruter og CLI ligg i `innmelding_ruter.py` og `innmelding_kommandoar.py`. Betalingstenesta blir verande i `ny_innmelding.py`. Avhengnader blir sende inn, utan import tilbake frå dei nye modulane til appen eller betalingstenesta.

- [x] **10. Utvid Python-formatering gradvis.**
  `ruff.toml` avgrensar formatkontrollen til 20 filer og inneheld dupliserte
  oppføringar for `brevo.py` og `medlemsruter.py`.
  **Tiltak:** Fjern duplikata og ta inn samanhengande modular i små endringar,
  til dømes medlemsinnlogging, Mi side og styremodulen. Unngå å blande stor
  formatering med funksjonsrettingar.
  **Ferdig når:** Dei valde modulane har konsistent format og blir kontrollerte
  i CI. Formateringsendringar skal vere enkle å gjennomgå separat.

  **Utført 26. november:** Dupliserte Ruff-oppføringar er fjerna. Autentisering, Mi side, styremodul, nye innmeldingsmodular og tilhøyrande testar er formaterte og inkluderte i CI-kontrollen: 35 filer.

## Duplisering og ubrukt kode

- [x] **11. Bruk éi kjelde for dei identiske årsmeldingsstilane.**
  `lutar/arsmelding-tilskipingar.css` og
  `medlemsregister/fast/arsmelding-tilskipingar.css` er byte for byte like.
  **Tiltak:** Vel éi kjelde og server eller kopier henne automatisk til dei
  nødvendige stadene. Ta omsyn til nettstad, intern vising og sjølvstendig PDF-bygg.
  **Ferdig når:** Ei stilendring slår gjennom i alle tre utan manuell
  dobbelredigering, og serveroppdateraren tek med den nødvendige kjelda.

  **Utført 26. november:** `lutar/arsmelding-tilskipingar.css` er no kjelda for nettstad, Flask og sjølvstendige dokument. Kopien er fjerna, og serveroppdateraren og dokumentarbeidsflyten tek med kjeldefila.

- [x] **12. Fjern dei ubrukte dato- og aldersfunksjonane i appfila.**
  `medlemsregister/app.py:253–272`: ingen referansar vart funne til
  `_parse_dato_ymd` eller `_alder_år`. Aktiv aldersutrekning ligg i
  `aldersfordeling.py`.
  **Ferdig når:** Funksjonane og eventuelle import som då blir ubrukte er
  fjerna, og relevante eksisterande testar består.

  **Utført 26. november:** Dei to ubrukte funksjonane og den ubrukte date-importen er fjerna.

## Dokumentasjon og avslutning

- [x] **13. Merk den eldre gjennomgangen som historisk.**
  `arkiv/Kodegjennomgang oslobygda.md` skildrar fleire tidlegare problem som
  no er løyste. Bevar historia, men legg inn ein tydeleg peikar til denne lista
  og `medlemsregister/PERSONVERN-DRIFT.md` for nyare status. Historia i den gamle fila blir bevart.
  **Ferdig når:** Lesaren ikkje får inntrykk av at løyste gamle punkt framleis
  er opne, eller at dagens feil alt er retta.

  **Utført 26. november:** Den eldre rapporten har fått ei tydeleg historisk merking og lenkjer til denne lista og driftsstatus. Resten av historia er bevart.

- [x] **14. Verifiser rettingane samla før eventuell utrulling.**
  Køyr dei nye regresjonstestane frå oppgåve 1–5 og alle eksisterande grupper.
  Prøv dei endra brukarforløpa med fiktive data. Kontroller dokumentvising og
  bygg dersom malar eller felles ressursar er endra. Dokumenter faktisk
  testresultat og Git-versjon. Følg etablert backup- og utrullingsprosedyre
  ved ei seinare produksjonsoppdatering.
  **Utført 26. november:** 316 Python-testar, alle eksisterande skripttestgrupper,
  formatkontroll, Jekyll-bygg og isolert PDF-bygg bestod. Alle åtte PDF-sider
  vart inspiserte. Lokal Safari-prøve av medlemsliste, lagring og økonomiskjema
  bestod. Ein ekstra feil i PDF-byggaren vart retta: lazy-bilete blir no lasta
  før utskrift, med avgrensa ventetid på lasting. Ingen produksjonsdata eller
  genererte dokumentfiler i repoet vart endra av prøvene.

## Løyste punkt som ikkje skal opnast på nytt som kodefeil

Dette er stadfesta i dagens kode; produksjonsstatus må lesast i driftsdokumentasjonen.

- [x] Proxy-handtering med avgrensa tillit til siste `X-Forwarded-For` i WSGI.
- [x] Lokalt lagra Fraunces-skrifttypar.
- [x] TOTP-kryptering med separat nøkkel og kontrollert produksjonsoppstart.
- [x] Nummererte databasemigreringar og felles handtering av tilkoplingar.
- [x] Felles betalingsreglar og namngjevne ordrestatusar.
- [x] Dekorator for CSRF-unntak.
- [x] Låste felles Python-avhengnader.
- [x] Skilde modular for medlemsruter og Brevo; isolert lokal testoppstart.
- [x] Redigering av innmeldingsopplysningar før betalingsforsøk.
- [x] Rutinar for oppbevaring, sletting og backuprotasjon er implementerte.

Genererte tilskipingssider og offentlege HTML/PDF-kopiar har eigne føremål og
skal ikkje slettast som duplikat. `test_payment_rules.py` og
`test_betalingsreglar.py` testar ulike nivå. SCSS-importane i `stilar.scss` og
`grunnlag.scss` er heller ikkje dobbel import av same stilsett.

Full databasekryptering er eit driftsval, ikkje eit stadfesta nytt tryggleikshol.
WSGI avviser standard øktnøkkel og krev TOTP-nøkkel; standardnøkkelen i lokal
appoppstart er difor ikkje ført opp som eit produksjonshol.

Opne leverandør- og personvernoppfølgingar står i
`medlemsregister/PERSONVERN-DRIFT.md`. Eksisterande uttrykkelege avgrensingar
for lokale arkiv og backupopprydding skal respekterast.

## Verifikasjon ved gjennomgangen

- 302 Python-testar i `medlemsregister/tests` bestod i det eksisterande
  virtuelle testmiljøet med ResourceWarning-vising aktivert.
- To testar av oppdateringsskriptet bestod.
- Kalenderkontroll og tre testar av offentleg prisvising bestod med Node.
- To nyhendebrevtestar bestod med moderne Ruby. System-Ruby 2.6 manglar
  `YAML.safe_load_file` og kunne ikkje køyre heile denne testgruppa.
- Ruff sin noverande, avgrensa formatkontroll bestod for 20 filer.
- Bugbot reproduserte oppgåve 2–4 med isolerte testdata og simulerte eksterne
  tenester. Security Review reproduserte kladdsperra og tidskanalen i 1 og 5.

Gjennomgangen er kjeldekodeanalyse og lokale prøver. Han er ikkje ei ny
stadfesting av produksjonsoppsett, reelle Vipps-betalingar eller oppdaterte
sårbarheitsmeldingar for tredjepartspakkar.

## Samla kontroll 26. november 2026

- 316 Python-testar bestod samla med ResourceWarning-vising aktivert, utan nye
  ResourceWarning-meldingar. Dette inkluderer kodekø, e-poststadfesting,
  betalingslåsing, e-postretting, medlemsårsvedtak og migreringar.
- To oppdaterarskript-testar, kalenderkontroll, tre prisvisingstestar og to
  nyhendebrevtestar bestod.
- Ruff-kontrollen bestod for 35 filer, og Git-diffkontrollen fann ingen
  whitespace-feil. Python-pakkane i testmiljøet har ingen brotne avhengnader.
- Jekyll-bygget bestod med Ruby 3.3 og dei eksisterande låste pakkane i eit
  separat byggmål. Ruby 4 sitt globale pakkemiljø hadde ikkje desse versjonane.
- Lokal Safari: innlogging, lasting av medlemslista og lagring av ein fiktiv
  medlem bestod med JavaScript frå eiga fil og CSRF-vern. Økonomioversikt og
  det delte registreringsskjemaet vart kontrollerte. Ekte betaling, e-post og
  publisering var sperra i prøveappen.
- PDF-bygg bestod i ein isolert kopi med offentlege dokumentdata: rekneskap
  tre sider, årsmelding fire sider og budsjett éi side. Alle åtte sider vart
  inspiserte utan layoutfeil. Den eksisterande byggaren hengde først i
  `img.decode()` for lazy-bilete; han lastar no desse bileta før utskrift og
  har ei tidsgrense på ventinga. Testverktøy og resultat ligg berre i mellombelse
  mapper, og produksjonsavhengnadene er uendra.

Før produksjonsbruk: verifiser og start kodearbeidaren etter AUTH-EPOST.md,
installer den samla kodeversjonen og køyr migrering 2, Reload og røykprøve.
Eksterne tenester og faktisk e-postlevering er ikkje prøvde i denne økta.

## Oppfølging etter røykprøve av innmelding

Røykprøva avdekte at tilbakeknappen og ny innsending av hovudskjemaet kunne
bruke ein gammal kladd utan å lagre retta e-postadresse. Dette er retta:
«Bli medlem» opnar no den eksisterande kladden for redigering, og ei innsending
frå eit eldre hovudskjema oppdaterer kladden før kode blir køa. Ny adresse krev
ny stadfesting. Ordren blir framleis ikkje endra etter starta betalingsforsøk.
To regresjonstestar dekkjer retting av adresse, ny mottakar, ugyldig gammal kode
og vern av påbegynt betaling. Oppfølginga krev kodeoppdatering og Reload,
men ingen ny databasemigrering eller endring av arbeidarkommandoen.

Alle 318 Python-testar og formatkontrollen bestod etter denne rettinga.
