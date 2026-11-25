# Mi side

Publisert på PythonAnywhere 25. november 2026. Offentleg innloggingsside,
tilgangsvern og sjølvhosta fontar er kontrollerte etter Reload. Full innlogging
med motteken e-postkode og eksisterande styreinnlogging må òg prøvast av laget.
Sjå PERSONVERN-DRIFT.md for personvernendringane.

## Medlemsflyt

Medlemmen går til hovudnettsida og vel Mi side. Eksisterande, aktive medlemsdata
blir brukte; det blir ikkje laga ein ny medlem eller eit nytt passord ved innlogging.
E-postadressa må vere registrert på nøyaktig éin medlem. Ukjende/delte adresser
og leveringsfeil får same svar. Delt e-postadresse, manglande adresse eller tapt
tilgang må avklarast med laget; ein e-postkode blir ikkje brukt til å velje mellom
fleire personar eller gi tilgang til familien sine opplysningar.

Ein åttesifra kode blir send gjennom eksisterande SMTP til den registrerte
adressa. Koden er nettlesarbunden, gjeld i ti minutt, kan brukast ein gong og
har fem forsøk. Han er lagra som HMAC med øktløyndomen, ikkje i klartekst.
Førespurnader er avgrensa per e-post og faktisk klient-IP. Innlogga medlemsøkt
varer høgst åtte timar. Ny innlogging roterer økta; medlemskode gir aldri
styretilgang. Eigne kontrollar vernar alle medlemssider, utskrifter og handlingar.

Medlemmen kan redigere namna og kontaktfelta som finst i innmeldingsskjemaet.
E-post er eit særskilt byte. Fødselsdato er framleis valfri og kan fjernast.
Rolle, betalingsstatus, medlemsår og medlem-ID kan ikkje endrast gjennom skjemaet.
JSON-nedlasting inneheld berre eigne medlemsopplysningar og eigne medlemsår.

## Byte av e-post

Byte krev både ein kode til den gamle adressa og ein til den nye, begge i same
innlogga nettlesar. Adressa blir ikkje endra før begge er stadfesta. Konflikt
med ein annan medlem/pågåande innmelding, endra innloggingsversjon, utløp eller
brukt kode stoppar bytet. Pågåande betaling/usikker stadfesting må avklarast først.
Medlem med styrekonto får beskjed om å kontakte styret for samordna byte, slik
at medlemsinnlogging ikkje kan endre ei administrativ innloggingsidentitet.

Vellukka byte opphevar andre medlemsøkter og gamle fornyingslenkjer. Ventande
stadfestingar blir adresserte til den nye, verifiserte adressa. Eldre finansielle
historikkopplysningar blir ikkje omskrivne. Nyhendebrev blir avmeldt på den gamle
adressa; ny påmelding på den nye krev eit uttrykkeleg val. Manuelt e-postbyte
frå styret opphevar også medlemsøkter og ventande innloggingskodar.

## Nyhendebrev

På-/avmelding blir lagra som eit uttrykkeleg medlemsval og køa varig. Den
same timelege innmeldingsjobben synkroniserer med Brevo. Ved feil blir jobben
liggjande for nytt forsøk; Mi side viser at synkronisering ventar.

Avmelding fjernar berre kontakten frå laget si konfigurerte nyhendebrevliste.
Ho slettar ikkje medlemskap eller andre lister. Berre eit nytt, uttrykkeleg
påmeldingsval kan oppheve Brevo si avmeldingsmarkering. Namneretting sender
berre namn og opphevar ikkje avmelding. Eksisterande signup-jobbar får ikkje
overstyre nyare medlemsval. Ved sletting under eit pågåande API-kall blir
Brevo-sletting køa på nytt etterpå.

Første innlogging på Mi side endrar ikkje eksisterande Brevo-påmelding. Om det
ikkje finst eit medlemsval på Mi side, seier sida dette uttrykkeleg; ho gjettar
ikkje abonnementstilstand frå ei gammal innmelding. Avmelding via lenkja i eit
nyhendebrev gjeld framleis, sjølv om det tidlegare valet på Mi side var påmelding.

## Medlemspengar og påminning

Kontingentknappen følgjer eksisterande `membership_periods`, faktisk kalenderår,
opningsdato, satsvedtak, betalingsmodus og registrert betalt/gratis medlemskap.
Ingen kan betale for eit år som ikkje er ope. Serveren hentar medlem og år frå
den innlogga økta og klokka, ikkje frå innsende ID-ar eller årstal.

Betaling bruker eksisterande Vipps-ordre og idempotens. Ein intern fornyingstilgang
blir laga på serveren og knytt til medlemsøkta; ingen personleg token blir sendt
som lenkje på e-post. Statussida krev framleis gyldig medlemsøkt for desse ordrane.
Å opne Mi side startar ikkje ei betaling eller ein utsending.

Styret sin Send påminning sender ei tenestemelding som ber medlemmen skrive
nettadressa sjølv og velje Mi side. Meldinga inneheld ingen betalings- eller
innloggingslenkje. Påminningar får eiga leveringshistorikk, utan å opprette eller
oppheve betalingslenkjer. Eldre e-postlenkjer blir bevarte for kompatibilitet
med eksisterande flytar; nye påminningar sender dei ikkje.

## Utrulling og røykprøve

1. Følg PERSONVERN-DRIFT.md først, inkludert separat TOTP-nøkkel, backup og
   kontrollert omlasting. Bruk den etablerte serveroppdateraren. Nye modular,
   malar og `fast/mi-side.css` må vere med før menyvalet blir publisert.
2. WSGI `init_db()` opprettar dei nye tabellane og migrerer `renewal_links`
   med tilgangstype. Eksisterande medlemmer/betalingar blir bevarte.
3. Prøv SMTP med eigne godkjende opplysningar. Kontroller kodeutløp, ny kode,
   logg ut og at vanleg medlem ikkje får styre-API eller andre profiler.
4. Prøv profilretting og byte mellom to adresser du kontrollerer. Prøv ein
   allereie innlogga annan nettlesar etter e-postbyte; økta skal vere oppheva.
5. Kontroller open/stengd kontingent, gratis/betalt status og éi kontrollert
   betaling. Reell betaling blir utført av brukaren i Vipps.
6. Prøv nyhendebrevval og den eksisterande timelege vedlikehaldsjobben. Kontroller
   overføring til rett Brevo-liste og at avmelding ikkje blir oppheva av profilretting.
7. Set `mi_side_publisert: true` i `_config.yml` og publiser hovudnettsida når
   appen er testa på serveren. Brytaren står av i denne leveransen, slik at
   første push til main ikkje annonserer ei innlogging før serveren er oppdatert.

Ingen ny masseutsending, planlagd jobb eller produksjonsbetaling er starta lokalt.
