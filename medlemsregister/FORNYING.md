# Årlege medlemspengar og fornying

Styret finn **Kontingentår og fornying** frå medlemslista (`/kontingent`).
Det blir ikkje sendt e-post automatisk ved oppgradering eller årsskifte.

## Vedtak og opning

Kvart år har minimumssats i øre, Superkul-grense (strengt meir enn grensa),
opningsdato, vedtaksdato og ei uttrykkeleg stadfesting på at årsmøtet har vedteke
satsane. Tidlegare år blir ikkje overskrivne ved nytt vedtak.

2026 er migrert med minimum 5 kr og eksisterande Superkul-grense. **2027 er
stengt utan vedtekne satsar.** Vedtak for 2027 må ha dato i 2027; det kan ikkje
førehandsopnast i 2026. Etter årsmøtet fører styret inn dei nye satsane og set
opningsdato til årsmøtedagen eller seinare.

Årsmøtet i 2027 kan samstundes vedta satsane for 2028, med opning 1. januar 2028.
Det blir aldri tillate nye betalingar for eit framtidig eller passert kalenderår.
Årsavslutting i medlemsregisteret og opning av kontingent er separate handlingar.

Sperra og minimumssatsen blir kontrollerte både ved skjemainnsending og rett før
Vipps-betaling blir oppretta, også for nye medlemmar. Gamle opne faner kan ikkje
omgå sperra. Ein pågåande godkjend betaling blir framleis avstemd og bokført på
avtalt år om svaret frå Vipps kjem etter årsskiftet. Satsar blir låste etter første
forsøk på å opprette ei produksjonsbetaling; ta kontakt før korreksjon av eit år
som allereie er i bruk. Den eldre Superkul-innstillinga skriv til same årsdata.

## Personlege lenkjer

Vel medlem og år. **Lag testlenkje** er berre tilgjengeleg når Vipps står i
testmodus. **Send personleg e-post** sender éin transaksjonsmail til den valde
medlemmen, uavhengig av nyhendebrevsamtykke. Gratis eller allereie betalte
medlemskap blir ikkje sende oppkrav. Masseutsending er ikkje implementert.

Lenkja inneheld 256 bit tilfeldig kode. Berre SHA-256-hashen blir lagra i databasen.
Lenkja viser ikkje kontaktopplysningar og blir bytt mot ein sesjon før skjemaet
blir vist. Ho er avgrensa til éin medlem, eitt år og test/produksjonsmiljøet.
Deling av lenkja gir høve til å betale på vegner av medlemmen, aldri redigere
medlemsdata eller logge inn som styret. Ei ny utsending sperrar tidlegare lenkjer.
Lenkja fungerer berre innanfor det opne kontingentåret; sletting av medlemmen
sperrar lenkjene og anonymiserer også fornyingsordrane.

Medlemmen vel beløp på nytt kvart år. Før betalinga er starta kan beløpet endrast.
Når Vipps er kontakta, blir same ordre og beløp brukte ved nye forsøk for å unngå
dobbeltbetaling. Avbroten/utgått ordre kan erstattast med eit nytt forsøk. Ny lenkje
for ein pågåande ordre gir tilgang til same ordre, ikkje ein ny betalingsførespurnad.

Ved stadfesta trekk blir betaling, ordrestadfesting og medlemsstatus lagra atomisk.
Det blir ikkje oppretta ein ny medlem eller overskrive kontaktopplysningar eller
nyhendebrevsamtykke. Styret blir bevart som medlemstype; andre blir Kul/Superkul
etter årets grense. Dersom medlemmen allereie er betalt når Vipps stadfestar eit
anna trekk, blir ordren flagga til manuell kontroll i staden for dobbel bokføring.
Fornying går ikkje inn i Brevo-køen for nye nyhendebrevssamtykke.

## Test og drift

Bruk Vipps-testmodus, ein ikkje-betalt testmedlem og **Lag testlenkje**. Test
betaling med minimum, meir enn Superkul-grensa, avbrot og nye forsøk. Testbetaling
endrar aldri medlemsregisteret eller sender e-post/Brevo-data. Jan./feb.-sperra og
framtidige år er dekte av automatiske testar med simulert dato.

Webhook og `flask --app app innmelding-vedlikehald` avstemmer fornyingsbetalingar
på same måte som nye innmeldingar. Ved tvetydig SMTP-utfall viser administrasjonen
at sendinga må kontrollerast før ein prøver igjen; det blir ikkje gjort automatiske
nye utsendingar av personlege lenkjer. Vurder innhald i salsvilkår og e-posttekst
før dei første reelle oppkrava. Eksisterande Vipps-oppsett blir ikkje endra av
installasjonen av denne funksjonen.
