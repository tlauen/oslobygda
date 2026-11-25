# Personvernoppfølging

Kodeversjon f1615c0 er installert og appen er omlasta på PythonAnywhere
25. november 2026. Backup med gjenopprettingsprøve var OK før oppdatering.
Separat TOTP-nøkkel er oppretta, og WSGI-oppstart og offentlege sider svarar.
Kontrollane nedanfor som krev faktisk styreinnlogging, e-post eller Vipps,
må framleis gjennomførast av laget.

## Betaling og bokføring

Vipps får ikkje lenger ein førespurnad om profildeling. Namn og telefon frå
medlemsskjemaet, betalingsreferanse, medlemsår, beløp og oppretta/bokført tidspunkt
blir viste i Innmeldingar. Referansen er den same som blir sendt til Vipps og
brukt i betalingskontrollen og rekneskapsimporten. Betalaren kan vere ein annan
enn medlemmen. Namn og telefon i Bygdelista dokumenterer kven medlemskapen gjeld,
ikkje identiteten til den som betalte. Kontroller faktisk trekt/refundert beløp
og referanse i Vipps før manuell bokføring. Etter utrulling: kontroller at
referansen kan finnast i laget si Vipps-oversikt før denne arbeidsflyten blir godkjend.
Eksisterande betalarfelt blir ikkje lenger fylte; dei blir tømde ved opprydding/sletting.

## Ordre og e-postvarsel

Den eksisterande timelege `innmelding-vedlikehald` gjer no òg dette:

- Etter 30 dagar frå oppretting: anonymiser avbrotne/utløpte/terminerte ordrar
  utan bokføring, og nye ordrar der betalingsoppretting aldri er forsøkt.
- Bevar referanse, medlemsår og beløp. Fjern kontaktopplysningar og nettlesartilgang.
- Ikkje anonymiser ukjent betalingsutfall, betalingar til kontroll eller usikker
  e-postlevering. Pågåande betalingslås blir respektert.
- Kø varsel til folk@oslobygda.no om `review`, usikker stadfestingsmail,
  stadfestingsmail som har stått i sending i over ein time, og betalingsforsøk
  som framleis er uavklarte etter 30 dagar.

SMTP blir prøvd igjen ved eksplisitt avvising. Uvisst leveringsutfall blir ikkje
automatisk sendt på nytt; status og knapp for kontrollert nytt forsøk finst under
Personvern og sletting. Varsel blir ikkje sende under lokale testar.

## Godkjend medlemssletting

To **heile kalenderår** utan betalt eller godkjent gratis medlemskap gir forslag
om sletting: sist dekt år 2026 -> tidlegast 1. januar 2029. For oppføringar utan
betaling blir innmeldingsåret brukt som tidlegaste utgangspunkt. Betalingar blir
summerte per medlemsår. Manuell Betalt-status og gratisvedtak blir lagra per år,
utan at det blir laga fiktive betalingspostar. Historisk Betalt- og gratisstatus
blir éin gong registrert for det aktive medlemsåret. Statusen blir ikkje automatisk
fornya ved oppstart eller årsskifte. Ved å lagre Gratis i medlemslista godkjenner
styret gratis medlemskap for det aktive medlemsåret. Vel Ikkje betalt for å
oppheve eit gratisvedtak for dette året.

Jobben sender namn og medlemsnummer til folk@oslobygda.no. E-posten lenkjer til
`/personvern-oppfolging`; vanleg styreinnlogging og CSRF-verna POST er påkravd.
Ein e-postlenkje/GET kan aldri slette data. Sletting krev ein stadfestingsboks og
knapp for kvar person, og er sperra til varselet er stadfesta sendt. Ny betaling,
nytt gratisvedtak, endra opplysningar eller pågåande betaling opphevar den gamle
godkjenninga. Aktive styrekontoar blir haldne utanfor automatisk framlegg.
Bokførte beløp blir bevarte utan kontaktopplysningar; Brevo-sletting blir køa.

E-postane med namnelister må handterast av laget, også etter godkjend sletting.
Eldre lokale backupsett roterer etter eksisterande oppsett. Proton-kopiar blir
ikkje sletta av denne endringa; sletting frå eldre tryggingskopiar og rotasjon av
Proton-arkivet må inngå i laget si eiga backupforvaltning. Ved gjenoppretting av
ein eldre kopi må seinare personvernslettingar gjennomførast igjen før drift.

## TOTP: separat nøkkel og kontrollert oppstart

Produksjonen bruker framleis vanleg SQLite. TOTP-felta i både styrekontoar og
pågåande registreringar blir krypterte med Fernet og **ein separat nøkkel**,
`MEDLEMSREGISTER_TOTP_KEY`. Namn, kontaktdata og økonomi får ikkje databasekryptering
av dette. Dette vernar ei databasefil utan nøkkelen; det vernar ikkje mot ein
angripar som òg kan lese .env eller køyre kode som appbrukaren.

Før Reload med ny kode:

1. Ta og prøv eksisterande databasebackup. Bevar .env privat.
2. Installer kode og avhengnader med den etablerte serveroppdateraren.
3. Køyr `konfigurer_totp.py` med appmiljøet. Programmet lagar nøkkelen éin gong
   i eksisterande .env (600) og viser aldri nøkkelen i konsollen.
4. Bevar den nye nøkkelen separat i laget sin passordhandterar. Vanleg
   databasebackup inneheld henne ikkje. Også ein dekryptert Proton-backup av
   databasen krev denne nøkkelen for styreinnlogging.
5. Reload. Oppstart krypterer eksisterande TOTP-felt i éin transaksjon og
   kontrollerer krypterte felt. Manglande eller feil nøkkel stoppar oppstart;
   ingen ny nøkkel blir generert automatisk og ingen konto blir nullstilt.
6. Prøv eksisterande styreinnlogging, registrering og passordbyte. Ta ny backup.

Ikkje fjern eller skift nøkkelen etter migrering. Ved tilbakeføring må koden
framleis kunne lese dei krypterte felta; ein eldre kodebackup åleine er ikkje
nok. Ikkje gjenopprett gammal database over nye innbetalingar.

## Proxy, fontar og personverntekst

WSGI stolar på siste X-Forwarded-For-verdi frå PythonAnywhere, og ingen andre
proxy-headerar. Lokal app får ikkje denne tilliten. Kontroller med to ulike
klientar etter Reload; ikkje legg klient-IP i ei offentleg feilsøkingsrute.

Fraunces ligg i `lutar/fonts/` med OFL-lisens. Oppdateraren må vere oppdatert
før installasjon, slik at fontfiler blir kopierte til PythonAnywhere.

Personvernsida er oppdatert med dei vedtekne fristane og fødselsdato til
aldersstatistikk. Aldersdokumentasjon for framtidige tilskot er ikkje aktivert:
laget må avklare ordninga, nødvendige data og behandlingsgrunnlag før slik bruk.
Leverandøravtalar, overføringsgrunnlag og backupfristar må kontrollerast før ei
fullstendig personvernerklæring kan godkjennast. Ingen tilskotssøknad eller
utlevering av fødselsdatoar blir utført av denne endringa.
