# Offentleg rekneskap og årsdokument – steg 6

## Kva styret gjer

Frå intern rekneskap: opne **Førehandsvis offentleg rekneskap og kontroller publisering**.
Førehandsvisinga viser eksporten som går til nettsida, ikkje rå betalingsdata.

- Kontingent er éin samla årssum, også etter rettingar/refusjonar. Enkeltbetalingar,
  betalarnamn og betalingsreferansar følgjer ikkje med.
- Andre inntekter og utgifter viser dato, offentleg skildring, kategori, beløp og
  eit eige offentleg bilagsnummer. Dette gir ikkje tilgang til originalbilag.
- Oppgjer og balanseføringar er separate frå resultatet. Beløpet på slike detaljar
  er endringa på bankkontoen; null kan bety at føringa gjeld andre balansekontoar.
- Balanse viser eigedelar, samla gjeld og eigenkapital ved starten av året og
  rapportdatoen. Namn på kreditorar/utleggshavarar er interne.
- Frie offentlege skildringar må kontrollerast av styret. Programmet kan ikkje
  garantere at ein person ikkje er nemnd eller kan identifiserast i fritekst.

Første aktivering krev stadfesting av førehandsvisinga og at framtidige bokførte
postar skal publiserast etter same reglar. Seinare bokføring blir teken med i køa.
Vedlikehaldsjobben fangar òg opp nye postar som er registrerte utanfor økonomiskjemaet.
Framtidsdaterte postar kjem først med når rapportdatoen er nådd, i Europe/Oslo.
Førebels rapport viser dato for tala, genereringstidspunkt og avstemmingsstatus.

Ny førehandsvising er påkravd dersom rekneskapsrevisjonen eller rapportdatoen er endra
før aktivering. Stans av automatiske oppdateringar fjernar ikkje offentlege data
eller historikk. Ei allereie send GitHub-oppdatering kan ikkje trekkjast tilbake av pausen.

## Faste versjonar

Avstem og avslutt rekneskapsåret før du lagrar sakspapir eller godkjend rekneskap.
Godkjend versjon krev faktisk vedtaksdato etter rapportåret og ikkje i framtida.
Ingen revisor er påkravd. Styret kan lagre og sende framlegget og det endelege
vedtaket som ulike faste kopiar. Nye postar, gjenopning eller kalenderendring
endrar ikkje desse kopiane.

Godkjend versjon blir framheva på årsida. Løpande førebelse tal og eldre faste
kopiar blir viste ved sida av, med tydeleg merking. Retting etter godkjenning krev
ny intern føring og ny fast versjon; originalen blir verande. Rettinga kan forklarast
i offentleg skildring. Godkjenning av ein ny versjon må svare til eit faktisk vedtak.

## Teknisk publisering og oppsett før drift

Inga nøkkel, serverjobb eller verkeleg publisering er aktivert av utviklingsarbeidet.
Før drift:

1. Publiser kode og sidestubbar på GitHub Pages. For 2026 er både årsmelding,
   rekneskap og `/api/arsdokument/2026.json` klargjorde. Nye år krev tilsvarande
   sidestubbar før data kan sendast; arbeidaren kontrollerer at dei finst i repoet.
2. Set `GITHUB_DOCUMENTS_TOKEN` i serverens private miljøoppsett. Bruk ein eigen
   fine-grained token for `tlauen/oslobygda`, med berre nødvendig Contents read/write.
   Ikkje lagre han i Git, nettlesaren eller loggar. Appen avgrensar skrivesti til
   `_data/arsdokument/<år>.json`; GitHub-retten er framleis på repo-nivå.
3. Standard repo/branch er `tlauen/oslobygda` / `main`, eventuelt styrt med
   `GITHUB_DOCUMENTS_REPO` og `GITHUB_DOCUMENTS_BRANCH`. Offentleg data blir
   kontrollert under `https://oslobygda.no`, eventuelt `PUBLIC_DOCUMENTS_BASE_URL`.
4. Gå gjennom ein fiktiv eksport i eige testmiljø før reelle data blir publiserte.
   Aktiver deretter dei årstala styret faktisk vil ha løpande innsyn i.
5. Køyr følgjande frå medlemsregister-mappa, med appens virtuelle miljø:

   ```bash
   python -m flask --app app publiser-arsdokument
   ```

   **Dette er ein publiseringskommando:** Han skriv alle valde offentlege køjobbar
   til konfigurert GitHub-repo. Ikkje køyr han med produksjonstilgang under lokal testing.
6. Etter kontrollert første publisering kan same kommando leggjast i ein timeleg
   PythonAnywhere-jobb, eventuelt i den eksisterande vedlikehaldsrutinen. Dette er
   ikkje gjort automatisk. Kontroller oppgåveloggen og køstatus. Ingen e-postvarsel
   eller nye automasjonar er oppretta av denne funksjonen.

Årsfila har `schema_version`, `year`, `versions` og `ledger_latest`.
Alle nestla felt blir validerte; detaljar, kategorisummar, resultat og balanse må
stemme før eksport. Årsmeldingar, faste rekneskapsversjonar og budsjett deler `versions`;
berre førebels rekneskap ligg i `ledger_latest`. Ingen interne databaseobjekt blir
serialiserte direkte. Offentleg JSON har same informasjonsnivå som nettsida.

Arbeidaren tek ein varig databaselås med eigar og utløpstid. Han fornyar låsen før
nettverksoperasjonar. Revisjon, innhaldshash, fil-SHA og konfliktkontroll hindrar at
eldre løpande snapshots overskriv nyare eller at faste kopiar blir endra. Etter eit
uvisst svar kan same jobb prøvast igjen; arbeidaren les målfila først og oppdagar
om innhaldet alt er lagra. Andre dokumentversjonar blir bevarte ved samtidig endring.

Nyaste førebelse snapshot erstattar eldre leveringsjobbar for same år. Faste
versjonar blir ikkje slått saman eller sletta. Ved databasegjenoppretting må kø,
revisjonar og offentleg historikk avstemmast før publisering blir starta igjen;
arbeidaren skal ikkje tvingast til å overskrive nyare offentlege data.

## Køstatus

- `pending`: kølagt, ikkje sendt.
- `sending`: kravd av arbeidar; kan òg stå att etter avbrot. Same jobb blir teken opp igjen.
- `stored`: innhaldet er kontrollert i GitHub; offentleg bygg er ikkje stadfesta.
- `visible`: innhaldet eller eit nyare førebels snapshot er stadfesta i offentleg JSON
  frå same Jekyll-bygg som HTML-sidene. Dette er ikkje visuell nettlesarkontroll.
- `failed`: feil med forklaring, blir prøvd igjen ved seinare køyring.
- `superseded`: eldre førebels leveringsjobb er erstatta eller oppdatering er stansa.

Arbeidaren sender ingen GitHub-token til den offentlege nettsida, og følgjer ikkje
HTTP-redirectar. Feil i publisering rullar ikkje tilbake ei allereie bokført intern
utgift. Revisjonsklokka og innstillingane bevarer behovet for ny eksport.

## Verifikasjon

`tests/test_offentleg_rekneskap.py` bruker fiktiv SQLite-database og simulerte
GitHub-/nettverkssvar. Ingen verkelege kontoar blir kontakta. Testane kontrollerer
årleg kontingent, fråvær av interne felt, summer og balanse, versjonslåsing,
aktiveringskontroll, køsamanslåing, status, konflikt, gjenforsøk og låsing.
Jekyll-malane må òg byggjast med tomt datagrunnlag og fiktiv eksport før drift.
Visuell sluttgjennomgang og kontrollert produksjonsprøve står att.


## Budsjett etter steg 7

Arbeidaren inkluderer no `budget_publication_queue`. Budsjett bruker eigne faste
versjons-ID-ar og avgrensa, validert schema, med budsjettbeløp og samla samanlikningstal.
Sidene `/om/budsjett/2027/` og `/api/arsdokument/2027.json` er klargjorde i koden.
Nye budsjettår må ha tilsvarande sidestubbar før data blir publiserte.
Sjå BUDSJETT.md for forslag, vedtak og intern oppfølging.

## Utforming av offentleg årsmelding

Nye eksportar frå strukturerte årsmeldingar har eit avgrensa `presentation`-felt
med offentleg tekst, valde tilskipingar, gjesteoverslag, betalingstal og offentlege
styreprofilar. Interne kjelderevisjonar, oppdateringsbrukarar og uvalde tilskipingar
følgjer ikkje med. Feltet blir validert før overføring. Eldre teksteksportar kan
framleis lesast, men manglar datagrunnlaget for kort og nøkkeltal.
Etter oppdatering: lagre utkastet, lag ein ny førebels fast versjon, kontroller
innhaldet og legg denne i kø. Køyr publiseringsjobben. Gamle faste kopiar og
allereie kølagde eksportar blir ikkje omskrivne automatisk.

## Publiser årsmelding med knappen

På den faste årsmeldingsversjonen: kontroller innhaldet, kryss av for offentleg
publisering og vel «Publiser årsmeldinga». Knappen køyrer overføringa for berre
den valde versjonen med serverens GITHUB_DOCUMENTS_TOKEN. Andre køjobbar blir
ikkje sende. Eksisterande publiseringslås og idempotens blir brukte.
GitHub Pages må framleis byggje nettsida etter sending. Sida viser skilnad på
sendt og stadfesta synleg. Bruk «Kontroller publisering / prøv igjen» ved behov.
Ingen nettlesar-GET publiserer innhald. Manuell CLI og ein eventuell timeleg jobb
kan framleis brukast for heile køa og for statusoppfølging.

## Éi gjeldande årsmelding offentleg

Årssida og den aktive offentlege årsdatafila har berre siste førebelse
årsmelding, eller siste godkjende årsmelding når ei slik finst. Godkjend status
har prioritet; ny publisering av eit eldre framlegg erstattar ikkje vedtaket.
Rekneskap og budsjett i same datafil blir ikkje fjerna. Faste interne kopiar og
Git-historikken blir bevarte, så dette er ikkje permanent sletting frå historikk.

## Rekneskap og budsjett utan konsoll

Knappane for å publisere/aktivere rekneskap og lagre ein fast rekneskapsversjon
sender no den aktuelle versjonen direkte. Kølista har «Publiser / kontroller
status» for tidlegare lagra versjonar som ikkje er stadfesta synlege. Budsjettets
publiseringsknapp sender tilsvarande berre den valde budsjettversjonen.
Alle krev innlogging, CSRF og stadfesting. Nye løpande endringar som blir lagde i
kø utan eit publiseringsklikk treng framleis ein planlagd publiseringsjobb, eller
at brukaren trykkjer publiser. Nettsidebygg og overføring er ulike steg.
