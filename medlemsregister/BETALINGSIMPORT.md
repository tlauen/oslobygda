# Medlemsinntekter og betalingsavstemming – steg 8

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
