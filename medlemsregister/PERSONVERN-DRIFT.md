# Personvernoppfølging

Status 25. november 2026. Kodegjennomgangen sine åtte hovudpunkt og ti
kodekvalitetspunkt er handterte gjennom implementering eller laget sitt
uttrykkelege val. Dette er driftsstatus, ikkje ei erklæring om at all
personvernoppfølging er avslutta.

## Avslutta og stadfesta

- Produksjon er oppdatert til 9dd397b. Førre appoppdatering 3dd5b6c er
  kontrollert med fungerande innloggingar, databaseintegritet, skjemaversjon 1,
  35 medlemmar og 31 betalingspostar. Bakgrunnsjobbane rapporterte returkode 0.
- TOTP-nøkkelen er lagra separat i Proton Pass, stadfesta av eigaren.
- PythonAnywhere og Umami er valde med EU-region, stadfesta av eigaren.
- Laget opplyser at det ikkje er bokføringspliktig og ikkje har tilskotsvilkår
  om oppbevaring av rekneskap. Ingen generell femårsfrist er lagt til grunn.
- Proton er ein eigen Oslobygda-konto.
- Brevo: full vilkårstekst versjon 1. oktober 2025 er motteken frå eigaren.
  [Tekstkopien](avtalar/brevo-tos-2025-10-01.txt) er arkivert uendra.
  Appendix 3 er DPA, Annex 1 skildrar behandling, Annex 2 underleverandørar
  og punkt 9 overføringsmekanismar. Dokumentet omtalar SCC-ar med tilleggstiltak
  og DPF der det gjeld. Dette er ikkje ei uavhengig stadfesting av at nettsida
  aldri er endra sidan kopien vart teken.
- Brevo-kontoen: eigaren har stadfesta lagra anonym sporing for både kampanjar
  og SMTP, éin månads transaksjonsloggar for alle avsendarar og «Never store
  previews» for nye tenestemeldingar. Dette anonymiserer ikkje automatisk eldre
  kampanjesporing. Skjuling av preview er ikkje åleine sletting av eldre innhald.

## Backuprotasjon og avgrensingar

Laget har godkjent daglege kopiar i 30 dagar og deretter vekentlege fram til
90 dagar. Dei to nyaste verifiserte kopiane og uavklarte eksportar blir bevarte;
avvik krev varsel og oppfølging. Dette gjeld ordinære komplette lokale sett,
krypterte eksportar og Proton-backup, ikkje aktive årsdokument eller rekneskap.
Sjå [PROTON-BACKUP.md](PROTON-BACKUP.md) for prosedyrar og kommandoar.

Eigaren køyrde lokal backup og Proton-jobben i produksjon 25. november.
Resultatet var `Backuprotasjon: rotated`, og opplasting, nedlasting og
isolert gjenoppretting var OK. Nyaste kopi vart verifisert 21:56:29 UTC.
Eigaren har deretter stadfesta tømming av papirkorga og sletting av dei to
eldre oppføringane i Proton-mappa `Tryggleikskopiar`. Kvitteringskommandoen
`--acknowledge-trash` er gitt, men konsollresultatet er ikkje motteke.

Rclone flyttar filer til papirkorga; permanent sletting krev menneskeleg
oppfølging. Proton oppgir i tillegg interne krypterte backupkopiar i opptil
30 dagar. Ikkje lov absolutt permanent sletting frå alle lagringslag innan 90 dagar.

### Inventering av dei 104 ukjende oppføringane

Eigaren leverte filliste. Av oppføringane låg 102 lokalt: 57 kodebackup-tararkiv,
18 eldre databasekopiar, 22 andre filer og fem manuelle backupmapper. Dei to
Proton-oppføringane var `nidarosbygda-20261029-230410.bygdelista-backup` og
mappa `Backup 2026 10 29`; eigaren har no stadfesta at desse er sletta.

Dei 22 andre lokale filene er 17 `.tgz`-arkiv, fire Python/HTML-filer og
`env-for-protokoll-20261031T095432Z`. Sistnemnde kan innehalde hemmelegheiter;
ikkje skriv innhaldet i logg eller chat. Dei fem manuelle mappene er
`etter-sakliste-protokoll`, `for-sakliste-protokoll`, `for-sletting-testdokument`,
`for-undersaksvedtak` og `for-vedtaksframlegg`. Innhaldet er ikkje kontrollert.
Oppført mappestorleik 0 i listeskriptet betyr ikkje at dei er tomme.

Eigaren avgrensa vidare rydding til Proton-mappa `Tryggleikskopiar` og bad
uttrykkeleg om at alt anna skulle liggje urørt. Lokale restfiler er derfor
ikkje sletta eller lagde inn i automatisk rotasjon. Dette er eit dokumentert
unntak, ikkje ferdig gjennomført sletting av alle eldre persondata.
`status.json` og `rotation.json` er nødvendige driftsfiler og skal bevarast.

## Opne oppfølgingar

- **PythonAnywhere:** eigaren har sendt spørsmål om gjeldande EU-avtale,
  underleverandørar, støttetilgang og behandlingsland. Ventar på svar.
- **GitHub:** privat Free-konto `tlauen`, ingen organisasjonskonto for laget.
  DPA-dekninga for publisert personinnhald/Pages er ikkje stadfesta. Spørsmål
  er førebudd og kontaktadressa dpo@github.com er gitt. Ingen konto er flytta
  eller abonnement kjøpt; supportsvaret står att.
- **Umami:** DPA er automatisk innlemma i vilkåra utan separat signatur.
  Punkt 10 og Schedule 3 regulerer relevante overføringar. Eigaren har sendt
  spørsmål om EU-regionen sine faktiske behandlingsland/underleverandørar og
  lagring av IP-adresser i driftsloggar. Ventar på svar. Generell liste over
  KI-leverandørar beviser ikkje at besøksdata blir sende til KI.
- Historisk kampanjesporing hos Brevo er ikkje dokumentert sletta.
- Refusjonsprøve i produksjon er utsett til ein legitim refusjon oppstår.
  Ingen testtransaksjon eller unødvendig refusjon skal opprettast for dette.
- Dei lokale eldre kopiane blir ståande etter eigaren sin instruks ovanfor.

## Avtalekjelder

- [Brevo vilkår](https://www.brevo.com/legal/termsofuse/) og den arkiverte kopien.
- [Umami vilkår](https://umami.is/terms), [DPA](https://umami.is/dpa),
  [personvern](https://umami.is/privacy), [underleverandørar](https://umami.is/subprocessors).
- [Proton DPA](https://proton.me/legal/dpa) og
  [Drive personvern](https://proton.me/drive/privacy-policy). Filinnhald blir
  kryptert lagra i Sveits/Tyskland/Noreg etter produktinformasjonen; konto-,
  betalings- og støttedata må vurderast separat frå filinnhaldet.
- [PythonAnywhere EU-vilkår](https://eu.pythonanywhere.com/terms_v2/).
- [GitHub avtaleoversikt](https://github.com/customer-terms) og
  [avtale for organisasjonar](https://docs.github.com/en/organizations/managing-organization-settings/upgrading-to-the-github-customer-agreement).

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
