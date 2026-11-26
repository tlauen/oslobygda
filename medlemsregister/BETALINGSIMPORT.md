# Betalingsautomatikk og avstemming

## Implementert – må kontrollerast i drift

Koden for framdriftsplanen 1–7 er implementert: samla kontroll og godkjenning,
ePayment-kontroll, tidsstyrt bokføring med lås og nye forsøk, CSV-rapport,
gebyr/refusjonsforslag, bankkontroll og valfri Report API-henting. Ingen
produksjonsbetalingar er henta eller bokførte under utviklinga. Planen nedanfor
er framleis kontrollgrunnlag for utrulling; leverandørtilgang og faktiske tal er
ikkje stadfesta av utviklingstestane.

1. Oppdater serveren, og kontroller backup og dokumentert opningsbalanse.
2. På «Medlemspengar og betalingskontroll»: kontroller ei kjend
   produksjonsbetaling mot Vipps, førehandsvis og godkjenn dei eintydige forslaga.
3. Avstem tidlegare manuelle samleføringar. Vel startdato og aktiver automatikken
   først når desse ikkje kan bli førte på nytt. Av-knappen bevarer historikken.
4. Den eksisterande `innmelding-vedlikehald`-jobben køyrer automatisk kontroll,
   bokføring og oppfølging av autoriserte publiseringsjobbar. Ingen ny jobb er
   nødvendig dersom denne alt køyrer. Sjekk første periode mot kjeldene.
5. Under «Vipps-rapport»: last opp ny Vipps-CSV for eitt MSN og NOK om gongen,
   maksimalt 3 MiB / 10 000 rader. Overlappande rapportar blir gjenkjende med
   stabile kjelde-ID-ar. Kjeldeendringar blir stoppa til kontroll.
6. Vel medlem og medlemsår for direkte medlemspengar, eller inntektskategori.
   Kople eksisterande P-nummer dersom føringa alt finst. Kontroller refusjon mot
   originalpost. Stadfest faktisk bankoppgjer med dato, beløp og referanse, eller
   last opp bank-CSV med `Dato;Beløp;Referanse`. Automatisk bankkopling krev
   eintydig oppgjersnummer og beløp. Planlagd utbetaling åleine er ikkje bankbevis.
7. Valfri API-henting: set `VIPPS_REPORT_FETCH_ENABLED=1` og
   `VIPPS_REPORT_LEDGER_ID=<faktisk ledger-ID>` i servermiljøet, med eksisterande
   produksjonstilgang. Før henting blir NOK og eigarskap til éi salseining
   kontrollert. Bruk knappen «Hent rapport frå Vipps» eller Flask-kommandoen
   `hent-vippsrapport`. Faktisk tilgang må prøvast på serveren.

API-henting er lesande. Automatisk rapportføring krev òg aktivert
betalingsautomatikk og vald startdato. Berre API-kjelder med eintydig eksisterande
betalingskopling, gebyr eller bankstadfesta oppgjer blir behandla automatisk.
CSV-kjelder, direkte inntekter, refusjonar og ukjende typar krev godkjenning.
Gebyrlinjene er eigne kjelder; gebyrkolonnen på kvar betaling blir ikkje ført om
att. Ingen funksjon her overfører pengar eller utfører Vipps-refusjonar.

Ny kontroll av uendra betalingsgrunnlag oppdaterer kontrolltidspunktet utan å
lage ny kjeldeversjon. Reelle endringar bevarer tidlegare bevis. Ei batchgodkjenning
er atomisk og kan sendast på nytt utan ny bokføring. Nettverksfeil får ventetid,
og seinare betalingar blir ikkje blokkerte av dei første feila.

Implementasjonen byggjer på dei offisielle [rapporttypane](https://developer.vippsmobilepay.com/docs/APIs/report-api/api-guide/entry-types/)
og [API-spesifikasjonen](https://developer.vippsmobilepay.com/redocusaurus/report-swagger-id.yaml).
Den offentlege CSV-eksempelrapporten er brukt som formatgrunnlag; eigen eksport
og samsvarande kontoutskrift må framleis kontrollerast før ordinær drift.

## Tidlegare spesifikasjon og framdriftsplan


Inngang frå intern rekneskap til `/okonomi/betalingar`. Alle styrekontoar har same
tilgang. Ingen produksjonsdata er henta eller førte under utviklinga. Brukaren
fyller inn historisk rekneskap når den samla løysinga er klar.

## Prinsipp

Medlemsåret (`for_year`) er ikkje rekneskapsåret. Betalinga blir ført på dokumentert
betalingsdato. For ePayment blir faktisk CAPTURED-tidspunkt lese frå Vipps sin
hendingslogg og omrekna til dato i Europe/Oslo. Lokal behandlingstid (`paid_at`)
blir ikkje overskriven og blir ikkje brukt som fasit for Vipps-trekket.

Kjeldekontrollen lagrar berre beløp, trekkdato, konto, refunderte summar, kjeldetype,
intern referanse, ansvarleg og kontrolltidspunkt. Rå hendingslogg, betalarprofil og
kontaktdata blir ikkje kopierte inn i økonomikjelda. Kjeldehistorikk og kopling til
rekneskap er uforanderlege. Ny kontroll med endra opplysningar gir ny revisjon.

## Historiske/manuelle innbetalingar

1. Registrer medlemsbetalinga som vanleg i Bygdelista dersom ho ikkje finst frå før.
2. Kontroller beløp, faktisk dato og konto mot bank-/Vipps-rapport. Vel bank, Vipps
   til gode eller faktisk kasse, og legg inn internt dokumentasjonsgrunnlag.
3. Sjekk om inntekta alt er med i rekneskapen, også som del av ein større samlepost.
   Systemet viser nokre moglege enkeltpostar med likt beløp same år; dette er
   hjelp til kontroll, ikkje full duplikatdeteksjon.
4. Dersom ein eksisterande enkeltpost har same dato, konto og beløp, kan han
   koplast til betalinga utan ny bokføring. Ei samla inntektsføring med fleire
   medlemsbetalingar kan ikkje koplast automatisk med denne ein-til-ein-modellen.
   Slike historiske samlepostar må avstemmast særskilt; ikkje importer betalingane
   på nytt som nye inntekter.
5. Elles: stadfest at betalinga ikkje er bokført, og bokfør éi medlemsinntekt.

Kontantar som Torbjørn alt har betalt vidare gjennom Vipps skal ikkje reknast som
to inntekter. Kven Vipps-betalaren er, blir aldri brukt til å gjette medlem. Eigne
bankbetalingar kan stadfestast som bankinntekt. Historiske/manuelle kjelder går
ikkje inn i automatisk bokføring.

Ei betaling som er kopla til bokført post, kan ikkje slettast frå medlemsregisteret.
Ved ny import blir eksisterande kopling brukt. Dato-/beløpsavvik og reversert
originalpost krev manuell retting, ikkje ei stille ny inntekt. Anonymisering av
medlemsprofilen skal framleis bevare økonomibeløp og kjeldekopling.

## ePayment-kontroll

Knappen «Les status og kjeldetidspunkt frå Vipps» bruker berre GET for status og
hendingslogg. Tokenfornying kan krevje vanleg autentiseringskall. Rutinen kallar
ikkje innmeldingsflyten si `reconcile`, fordi den kan gjennomføre eit trekk.
Ingen create-, capture-, cancel- eller refund-operasjon blir utført av importen.

Testordre blir avviste. Produksjonsordren må ha ein registrert medlemsbetaling.
Fullt trekk og NOK-beløp må stemme, og éi vellukka CAPTURED-hending må gi eintydig
betalingsdato med tidssone. Identiske duplikathendingar blir ignorerte; motstridande
hendingar, fleire deltrekk, ufullstendig logg og observerte refusjonar krev kontroll.

Før bokføring må kjeldekontrollen vere mindre enn ein time gammal. Nye refusjonar
kan sjølvsagt skje etter kontrollen; seinare kontroller skal avdekkje dette. Originale
medlemsstatusar og Vipps-ordrar blir ikkje endra av rekneskapsimporten.

## Opt-in automatikk

Automatikk er avslått som standard. Før aktivering må opningsbalansen vere
registrert og historiske føringar gjennomgått. Vel startdato i dag eller seinare;
eldre trekk blir ikkje automatisk førte. Nye fulltrekte produksjonsbetalingar kan
førast når kjelda er fersk og eintydig, ordren ikkje står til kontroll, og det ikkje
er funne ei mogleg eldre manuell enkeltføring.

Etter oppsett kan ein administrator køyre, frå medlemsregister-mappa med appens
virtuelle miljø:

```bash
python -m flask --app app importer-medlemsbetalingar --hent-vipps
```

Dette les verkelege produksjonsopplysningar når rett nøkkeloppsett og eksplisitt
aktivering finst. Det kan bokføre kvalifiserte inntekter i opne år og dermed gi
nye tal i offentleg kø dersom løpande innsyn er aktivert. Det skal ikkje køyrast
med produksjonsoppsett som del av lokale testar. Utan aktivering gjer jobben ingen
Vipps-kall og bokfører ingenting. Utan `--hent-vipps` blir berre eksisterande
kjeldekontroll brukt, med same ferskheitskrav.

Jobben behandlar høgst 50 kjelder som standard (`--limit` kan justerast), og
prioriterer dei som er minst nyleg kontrollerte. Eksisterande kopla betalingar blir
kontrollerte utan ny inntekt. Feil blir viste internt med nøytral tekst. Ingen
leverandørrespons eller nøkkel blir skriven til logg. Ingen serverjobb er oppretta
eller aktivert av utviklinga; legg dette til timeleg vedlikehald først etter test.

## Refusjonar, gebyr og oppgjer

Observerte refusjonar stoppar automatisk bokføring og blir viste til manuell
avstemming. Importen fører ikkje ei nettoinntekt som skjuler brutto og refusjon.
Bruk den eksisterande økonomifunksjonen «Refusjon av inntekt», med originalpost og
faktisk refusjonsdato, og kontroller både Vipps og medlemsstatus. Uavklarte kjelder
kan framleis stå til kontroll sjølv om ei manuell refusjonsføring er utført; det er
ikkje levert automatisk lukking av slike avvik.

Gebyr og bankoppgjer blir framleis registrerte frå rapportar gjennom økonomiskjemaet.
Rapport API er undersøkt, men ikkje integrert: ePayment-/Recurring-salseiningar kan
ha tilgang med eigne nøklar, medan Vippsnummer-salseiningar ikkje har direkte tilgang.
Ingen kontotilgang er prøvd. Den historiske vanlege Vipps-flyten kan difor ikkje
føresetjast å vere dekt av den nye integrasjonen.

Planlagd utbetaling frå Vipps er ikkje prov på innbetaling til bank. Avstem med
kontoutskrifta før oppgjer blir registrert. I denne enkle modellen blir uoppgjorde
midlar haldne på Vipps til gode til faktisk bankoppgjer. Gebyr skal førast éin gong;
ikkje både enkeltvis og på nytt som del av oppgjeret.

## Kjelde og verifikasjon

Offisiell dokumentasjon undersøkt 29. oktober 2026:

- https://developer.vippsmobilepay.com/api/epayment/ – GET payment og event log.
- https://developer.vippsmobilepay.com/docs/APIs/report-api – tilgang per produkttype.
- https://developer.vippsmobilepay.com/docs/APIs/report-api/api-guide/settlement-process/ – gebyr og oppgjer.

`tests/test_betalingsimport.py` bruker mellombelse databasar og simulerte Vipps-svar.
Testane dekkjer årsskifte/tidssone, manuell attestering, eksisterande føring, testmiljø,
refusjon, duplikathendingar, feil/endra kjelde, reverserte postar, opt-in, gjenkøyring,
GET-only klientoperasjonar og tilgang/CSRF. Ingen nettverkskall blir utførte i testane.
Før produksjonsbruk står ein kontrollert lesetest mot faktisk salseining att.

## Fleire historiske betalingar i ein bankpost

For innsamling via privat Vipps/kontantar som er overført samla til bank: før
éin vanleg medlemspengepost til Bank med heile beløpet og bankdatoen. Opne
«Kople fleire betalingar til ein samlepost», vel dei aktuelle manuelle betalingane
med «Vel til samlepost» i kvar rad, og oppgi P-nummer og dokumentasjon.
Koplinga bokfører ingenting og bevarer betalingshistorikken. Beløpa må summere
nøyaktig til bankposten. Posten må berre innehalde Bank og Medlemspengar, og
medlemsåra må svare til året for posten. Skjemabetalingar med ePayment blir
framleis kontrollerte enkeltvis mot Vipps. Ei betaling eller ein post som alt er
kopla, kan ikkje brukast om att. Reversering eller endra betalingsbeløp viser
avvik og krev manuell oppfølging; samla koplingar blir ikkje sletta.

## Utforsking 26. november 2026

### Tilrådd første steg: skjemabetalingane

Den eksisterande ePayment-importen er det kortaste steget til mindre manuelt
arbeid. Innmelding/fornying registrerer medlemskap og betaling allereie;
rekneskapsimporten er separat og eksplisitt avslått som standard. Koden har vern
mot dobbeltføring, krev fersk Vipps-kontroll og stoppar ved refusjon eller tvil.
Det er ikkje undersøkt om funksjonen er aktivert på produksjonsserveren.

Før tidsstyrt drift bør vi leggje til ei førehandsvising som viser kva som vil
bli bokført utan å bokføre, og betre køa og avvikshandteringa:

- Stadfesta køproblem: Dersom 50 betalingar manglar kjeldekontroll og henting
  stadig feilar, blir dei same 50 valde på nytt. Seinare betalingar kan bli
  ståande ubehandla. To simulerte køyringar med 51 betalingar stadfesta dette.
  Prioritering må ta omsyn til mislukka forsøk, med rotasjon og ventetid.
- Betalingar før startdato bør skiljast frå reelle avvik, slik at historiske
  kjelder ikkje stadig fyller kontrollista.
- Styret bør få ei tydeleg oversikt over ubehandla betalingar og avvik, gjerne
  med varsling når noko krev handling. CLI-tal aleine er lite synlege i drift.

Etter dette: kontroller opningsbalanse, historiske føringar og startdato, gjer
kontrollert lesing mot eiga salseining og prøv ei avgrensa innføring før tidsstyring.
Dei 12 eksisterande importtestane bestod lokalt med simulerte svar. Dette provar
ikkje produksjonstilgang eller at alle kanttilfelle er dekte. Ingen import er
aktivert og ingen verkelege Vipps-kall er utførte under denne utforskinga.

### Direkte betaling til Vippsnummer: rapportimport

Vipps tilbyr oppgjørsrapport som CSV og XLSX. Ein første versjon kan bruke CSV
og vise ei førehandsvising av betalingar, refusjonar, gebyr og planlagde oppgjer.
Vippsnummer-rapporten kan òg innehalde namn, telefonnummer og melding dersom
«Personlig informasjon» er valt ved eksport. Desse opplysningane er interne og
skal ikkje følgje med offentleg rekneskapsinnsyn.

Vi bør fyrst kontrollere kolonnane i ein anonymisert faktisk eksport. Importen
må bruke stabile kjeldeidentifikatorar og salseining til duplikatvern, slik at
overlappande rapportperiodar kan importerast trygt. Beløp og namn aleine er ikkje
nok. Manglande eller uklare identifikatorar må stoppe automatisk føring.

Ei innbetaling er ikkje nødvendigvis kontingent, og betalaren kan betale for ein
annan. Systemet kan foreslå medlemskoplingar, men uvisse tilfelle må godkjennast.
Medlemsår og betalingstype må avklarast før oppdatering av medlemsstatus.
Skjemabetalingar som finst frå før må koplast, ikkje opprettast på nytt.

Rapporten viser rørsler i Vipps-balansen, ikkje alltid ei enkel gruppe betalingar
per bankutbetaling. Inntekta blir ført éin gong; bankoppgjer flyttar pengar frå
Vipps til bank. Gebyr og refusjonar må handsamast separat. Planlagt utbetaling må
avstemmast mot faktisk kontoutskrift før ho blir registrert som bankoppgjer.

### Full automatikk med Report API: eit seinare steg

Vipps si tilgangsside, oppdatert 4. november 2026, seier at ePayment og Recurring
kan bruke Report API med salseininga sine vanlege API-nøklar. Vippsnummer kan
ikkje bruke API-et direkte, men kan gi ein rekneskapspartnar tilgang. Det er
ikkje stadfesta kva rapporttilgang Oslobygda faktisk har.

For den eigne ePayment-salseininga kan API-et på sikt levere grunnlag for gebyr
og oppgjersavstemming. For direkte Vippsnummer er filimport eit mindre omfattande
første steg enn å etablere ei eiga partnarintegrasjon. Ingen ny leverandør er
nødvendig for å prøve filimport.

Offisielle kjelder kontrollerte 26. november 2026:

- [Report API: tilgang per produkttype](https://developer.vippsmobilepay.com/docs/APIs/report-api/api-guide/overview/).
- [Forstå oppgjørsrapporten](https://help.vippsmobilepay.com/nb-NO/articles/understand-the-settlement-report).
- [Vel rapportformat](https://help.vippsmobilepay.com/nb-NO/articles/find-the-right-report).

Dette er ei tilrådd utviklingsrekkjefølgje, ikkje ei aktivert produksjonsløysing.

## Framdriftsplan – 26. november 2026

Målet er at dokumenterte medlemsbetalingar frå innmeldingsløysinga kan bokførast
éin gong, at direkte Vippsbetalingar kan importerast utan dobbeltføring, og at
gebyr, refusjonar og bankoppgjer blir synlege for kontroll. Vi byggjer vidare på
importen som finst. Planen aktiverer ikkje produksjonsimport.

### 1. Gjere den eksisterande importkøa robust

Ansvar: utvikling.

- Rette blokkeringa der mislukka henting for dei første 50 betalingane kan
  hindre alle seinare betalingar. Bruk forsøkstidspunkt, rotasjon og ventetid.
- Skilje betalingar før startdato frå reelle feil og nye, ubehandla betalingar.
- Bevare seinare kontroll av allereie bokførte betalingar, slik at nye refusjonar
  eller endra kjelde blir oppdaga.
- Teste fleire køyringar, parallelle jobbar og avbrot utan dobbel bokføring.

Ferdig når ein feilande ordre ikkje blokkerer andre, og gjenteken køyring gir
same bokførte resultat. Kan gjerast utan produksjonstilgang.

### 2. Lage ein enkel kontrollflyt i Bygdelista

Ansvar: utvikling, deretter brukarkontroll av utforminga.

- Samle status på Økonomi → Medlemspengar: klare, bokførte og til kontroll.
- Lage førehandsvising av foreslåtte føringar utan å bokføre. Lesing frå Vipps
  skal vere tydeleg skild frå endring av rekneskapen.
- Vise beløp, betalingsdato, medlemsår, kjelde og eventuell eksisterande kopling.
- La brukaren godkjenne dei kontrollerte føringane samla; nye kjeldeendringar
  skal ugyldiggjere ei gammal førehandsvising.
- Gi ei kort, synleg melding når noko krev oppfølging, utan rå leverandørdata.

Ferdig når ein kan kontrollere og godkjenne ein avgrensa import frå grensesnittet,
og avvik har ei forståeleg forklaring og ei handling. Automatikk er framleis av.

### 3. Kontrollere oppstart mot verkelege opplysningar

Ansvar: styret kontrollerer dokumentasjonen; utvikling støttar samanlikninga.

- Kontrollere opningsbalanse og kva medlemsbetalingar som allereie er bokførte,
  også betalingar som inngår i historiske samlepostar.
- Avtale startdato for nye automatiske føringar. Historikken blir ikkje automatisk
  etterført som nye inntekter.
- Gjere kontrollert lesing av ei kjend produksjonsbetaling og samanlikne referanse,
  faktisk trekt beløp og betalingsdato med Vipps og medlemsregisteret.
- Godkjenne ei lita, tydeleg avgrensa bokføring gjennom kontrollflyten frå steg 2.
  Kontrollere også eventuell offentleg rekneskapsvising etterpå.

Ferdig når kjelde, medlemsbetaling og éi rekneskapsføring samsvarar, og ny køyring
ikkje opprettar ei ny inntekt. Dette er kontrollpunktet før automatisk drift.

### 4. Setje skjemabetalingane i automatisk drift

Ansvar: utvikling og driftsansvarleg; styret vel aktivering og startdato.

- Setje opp ein avgrensa, tidsstyrt jobb på PythonAnywhere når den kontrollerte
  manuelle flyten fungerer. Frekvensen blir vald ut frå tilgjengeleg driftsoppsett.
- Hindre overlappande jobbar og halde nettverksfeil til nye forsøk med ventetid.
- Vise siste vellukka køyring, tal på behandla betalingar og opne avvik.
- Ha ein enkel av-knapp. Stans skal stoppe nye automatiske føringar og bevare
  allereie bokførte postar, kjeldehistorikk og manuell kontroll.
- Kontrollere første driftsperiode mot Vipps og rekneskap før vi aukar omfanget.

Ferdig når nye, eintydige skjemabetalingar blir førte éin gong, og uvisse tilfelle
stoppar til kontroll. Dersom tidsstyring ikkje er tilgjengeleg, kan steg 2 brukast
manuelt i mellomtida.

### 5. Lage rapportimport for direkte Vippsnummer

Ansvar: styret leverer ein anonymisert faktisk eksport; utvikling lagar importen.
Dette kan spesifiserast parallelt med steg 1–4 når eksporten ligg føre.

- Kontrollere kolonnar og stabile identifikatorar i ein faktisk CSV-rapport.
- Lage opplasting og førehandsvising før noko blir registrert eller bokført.
- Skilje medlemsbetalingar, gåver, gebyr, refusjonar og oppgjersrørsler.
- Behandle uvisse medlemskoplingar manuelt. Betalarnamn eller likt beløp er ikkje
  åleine grunnlag for å tildele medlemskap.
- Kople skjemabetalingar som finst frå før, og hindre duplikat ved ny opplasting
  og rapportar med overlappande datoar. Uklare identifikatorar krev kontroll.

Ferdig når ein kontrollert rapport kan importerast to gonger utan nye duplikat,
og ingen uvisse medlemskap blir stadfesta automatisk.

### 6. Forenkle gebyr, refusjonar og bankavstemming

Ansvar: utvikling med kontroll mot rapport og kontoutskrift frå styret.

- Lage forslag til gebyr og oppgjer frå rapportgrunnlaget, med vern mot føringar
  som finst frå før. Bankutbetaling skal ikkje gi ei ny medlemsinntekt.
- Avstemme planlagt oppgjer mot faktisk innbetaling på bankkonto.
- Vise refusjonar som avvik med originalbetaling og eventuell eksisterande retting.
  Rekneskapsføring skal ikkje utføre sjølve refusjonen i Vipps.
- Vise kva som er avstemt, kva som manglar og kva som krev manuell avgjerd.

Ferdig når ei heil oppgjersperiode kan kontrollerast mot Vipps-rapport og bank,
med forklarte differansar og utan dobbeltførte gebyr, inntekter eller oppgjer.

### 7. Vurdere vidare API-automatisering

Ansvar: utvikling; styret vurderer nytte etter at filimporten er prøvd.

Undersøkje faktisk Report API-tilgang for den aktuelle salseininga og vurdere om
rapporthenting bør automatiserast. Behalde filimport som reserve. Eventuell
partnarteneste blir ei eiga avgjerd etter at behov og arbeidsmengde er kjende.

Ferdig når vi har eit konkret grunnlag for å velje vidare API-utvikling eller
halde fram med rapportimport. Dette er ikkje ein føresetnad for steg 1–6.

### Praktisk rekkjefølgje og bidrag

Start med steg 1 og 2. Dei kan utviklast og prøvast med simulerte data utan å
vente på nye leverandørsvar. Før steg 3 treng vi ei kjend produksjonsbetaling,
kontrollert opningsgrunnlag og vald startdato. Før steg 5 treng vi ein anonymisert
Vippsnummer-eksport; før steg 6 ei samsvarande kontoutskrift eller anonymiserte
oppgjerstal. Hemmelege nøklar skal framleis berre liggje i serveroppsettet.

Etter kvar milepåle skal løysinga kunne brukast, også om neste steg ventar.
Eksisterande bokføring blir ikkje omskriven automatisk som del av planen.
