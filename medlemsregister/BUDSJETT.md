# Budsjett og budsjettoppfølging – steg 7

Alle styrekontoar har same tilgang. Opne **Budsjett og oppfølging** frå «Årsmøte og
økonomi», på `/budsjett`. Utforminga er førebels fram til den visuelle sluttgjennomgangen.
Ingen reelle rekneskapstal eller budsjettbeløp er lagde inn av utviklingsarbeidet.

## Utan ferdig rekneskap

Det er mogleg å opprette og fylle inn budsjett før rekneskapen er registrert. Då
blir førre års samanlikningskolonne tydeleg merkt som ikkje registrert, med nulltal
som ikkje er ei stadfesting av aktivitet eller saldo. Brukaren kan vente med reelle
rekneskapsdata til den samla løysinga er klar.

Når rekneskapen seinare er fylt inn, trykk **Oppdater berre samanlikningstala**.
Det endrar ikkje budsjettbeløpa. Faste kopiar som alt er lagra, bevarer det gamle
grunnlaget; lag ein ny budsjettversjon dersom nye samanlikningstal skal med i sakspapira.

## Arbeidsutkast

1. Opprett eit år. Møteåret blir først sett til budsjettåret og kan redigerast.
2. Fyll inn beløp i NOK i dei same inntekts- og utgiftskategoriane som rekneskapen.
   Null er tillate; negative budsjettbeløp, uendelege tal og meir enn to desimalar blir avviste.
3. Legg inn offentleg omtale og føresetnader. Feltet er ikkje eit internt notatfelt.
4. Lagre arbeidsutkastet. Kvar revisjon får uforanderleg historikk med ansvarleg
   styrebrukar og tidspunkt. Samtidig redigering blir avvist med revisjonskontroll.
5. Førre års registrerte tal kan hentast som forslag til budsjett, etter ei uttrykkeleg
   stadfesting av at eksisterande beløp skal bytast ut. Negative kategorisummar blir
   sette til null som forslag og må vurderast. Kopiering blir avvist om rekneskapen
   ikkje er påbyrja/registrert.

Førre års tal blir henta berre frå bokførte rekneskapslinjer, ikkje frå rå
medlemsbetalingar. Dei blir merkte med rekneskapsår, rapportdato, tidspunkt for
henting og status (ikkje registrert, førebels eller avslutta). Framtidsdaterte postar
kjem ikkje med før rapportdatoen er nådd, i Europe/Oslo.

Lagre feltendringar før andre handlingar. Med JavaScript varslar skjemaet før ei
handling kastar ulagrede endringar. Ved konflikt blir innsend tekst og beløp viste
att; kopier dei før du opnar siste revisjon og flettar inn endringane.

## Styreforslag, vedtak og offentleg publisering

Lagre ein fast kopi av sist lagra utkast som «Styreforslag til årsmøtet». Dersom
årsmøtet gjer endringar, rediger arbeidsutkastet og lagre ein eigen fast vedteken
versjon med faktisk vedtaksdato. Framtidig vedtaksdato blir avvist. Ingen revisor
eller lukking av rekneskapsåret er nødvendig for å vedta eit budsjett.

Forslaget og vedtaket blir bevarte kvar for seg. Seinare redigering eller nye
rekneskapstal endrar ikkje kopiane. Sum inntekter, sum utgifter og resultat blir
rekna frå kategoriane; samanlikningstala har eigne kontrollerte summer.

Opne fast versjon for offentleg førehandsvising. Stadfest at teksten og tala kan
publiserast før versjonen blir lagd i publiseringskø. Eksporten inneheld berre faste
beløp, offentleg omtale, samla samanlikningstal og dokumentmetadata. Han inneheld
ikkje interne brukarnamn, betalingsdetaljar eller bilag. Fri tekst krev framleis
menneskeleg personvernkontroll.

Den eksisterande arbeidaren `flask --app app publiser-arsdokument` handterer no òg
budsjettkøa, med same låsing, hashkontroll, gjenforsøk og verifikasjon. Sjå
[PUBLISERING.md](PUBLISERING.md). Ingen reell publisering er aktivert under utvikling.

Offentlege sider er klargjorde på `/om/budsjett/` og `/om/budsjett/2027/`, med
JSON-stubb for 2027. Nyaste vedtekne budsjett blir framheva; før vedtak blir nyaste
publiserte forslag framheva. Alle gamle forslag og vedtak blir bevarte. Nye år treng
både budsjettårsside og JSON-stubb før publisering. Data deler det offentlege
årsformatet med rekneskap og årsmelding, utan å overskrive dei andre dokumenta.

## Oppfølging gjennom året

Oppfølginga bruker nyaste vedtekne budsjett når det finst. Seinare arbeidsutkast
endrar ikkje oppfølgingsgrunnlaget. Dersom det ikkje finst eit vedtak, blir
arbeidsutkastet brukt med tydeleg merking om at det ikkje er vedteke.

Faktiske tal kjem frå dei same bokførte postane som rekneskapen og blir rekna på nytt
ved vising. Private utlegg tel som kostnad når dei blir førte; refusjonen tel ikkje
som ny kostnad. Vipps-oppgjer tel ikkje som ny kontingent.

- Utgifter: «att» er budsjett minus faktisk kostnad; negativt tal tyder overskriding.
- Inntekter: avvik er faktisk inntekt minus budsjett; inga utgiftsliknande «att»-kolonne.
- Positivt avvik er dermed meir inntekt eller mindre kostnad enn heilårsbudsjettet.
- Budsjettert og faktisk resultat blir viste separat.

Dette er oppfølging mot heilårsbudsjett, ikkje månadleg eller sesongfordelt prognose.
Framtidige periodar og manglande rekneskapsgrunnlag er merkte. Oppfølginga er intern;
den offentlege budsjettversjonen er ein fast kopi.

## Drift og test

Nye `budgets`, `budget_edits`, `budget_versions` og `budget_publication_queue` blir
oppretta ved vanleg databaseinitialisering. Den eksisterande samla backupen tek
med tabellane. Det er ingen nye pakkar eller nøklar utover publiseringsoppsettet frå
steg 6. Ingen medlemsbetaling eller rekneskapspost blir oppretta av budsjettmodulen.

Testane i `tests/test_budsjett.py` bruker mellombelse databasar og fiktive data.
Dei dekkjer manglande rekneskap, samanlikningsoppdatering utan overskriving,
faste forslag/vedtak, revisjonskonflikt, ugyldige beløp, offentleg schema, køarbeidar,
tilgang/CSRF og reell budsjettoppfølging med private utlegg og refusjonar.


## Utskrift etter steg 9

Faste versjonar har no eiga utskriftsvising for lagring som PDF i nettlesaren.
Sjå [UTSKRIFT.md](UTSKRIFT.md). Faktisk PDF-paginering skal kontrollerast visuelt
i sluttgjennomgangen før produksjonsbruk.
