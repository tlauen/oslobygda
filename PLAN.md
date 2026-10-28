# Opprydding og ny nettside – 28. oktober 2026

- [x] Verifisert databasebackup og kodebackup på PythonAnywhere.
- [x] Felles footer, CSS og menydata; felles Python-pakkeliste.
- [x] Gammal innmelding avvikla; gamle skjema arkiverte.
- [x] Brevo-import krev eiga medlemsliste; nyhendebrev er ikkje medlemsregister.
- [x] Vipps-bokføringar kan ikkje slettast som manuelle registreringar.
- [x] Persondata og styretilgang blir sletta, rekneskap blir anonymisert, Brevo-sletting blir køa.
- [x] Valfrie felt kan tømmast, og CSV-formlar blir skjerma.
- [x] Databasekoplingar blir lukka; utrygg krypteringsmigrering blir stoppa; éin konsistent backupmetode.
- [x] Avlyste tilskipingar blir ikkje annonserte; HTML i nyhendebrev blir skjerma; Google-sluttdato tek omsyn til midnatt.
- [x] Fornamn–mellomnamn–etternamn, telefon på neste rad.
- [x] Rett innmeldingsadresse i meny og gamle lenkjer.
- [x] Automatisk pøbbgalleri, styremodul og dokumentkort.
- [x] Frilynt-forklaring på «Om laget»; synleg fireval-meny på mobil.
- [ ] Portrett av styret må leggjast til av laget; modulen har namn, rolle og initialar.
- [x] Kontrollert ekte produksjonsbetaling på 6 kr utført av brukaren; medlem, betaling og Superkul-type stadfesta.
- [x] Stadfesta medlemsregistrering og Brevo-kontakt i rett liste med namn.
- [ ] Offentleg opning av innmeldingsskjemaet: produksjonsmodus er lagra på PythonAnywhere; ventar på Web → Reload og anonym kontroll av den køyrande sida.

## Kontroll og utrulling

- 71 Python-testar bestått; Ruby-testar køyrde med Homebrew Ruby; kalendertestar og `git diff --check` bestått.
- Jekyll-bygg og visuell kontroll av mobilmeny, galleri, forklaring og innmeldingsskjema gjennomførte.
- Bygdelista er oppdatert på PythonAnywhere. Ekte produksjonsbetaling og Brevo-overføring er stadfesta. Produksjonsmodus er no lagra; offentleg opning ventar på Web → Reload og anonym kontroll.
- Offentleg nettside er klar lokalt, men ikkje committa eller pusha.
- Lesekontroll av produksjon viste fungerande innlogging og felles CSS, og ingen ventande Brevo-kontaktar eller slettingar. Ingen produksjonssynkronisering vart starta manuelt.

- [x] Sjølvbetent «Gløymt passord?» med e-postkode og eksisterande TOTP; avsluttar gamle innloggingar. Utrulla og skjema kontrollert på PythonAnywhere. 77 Python-testar bestått. Ingen passord er endra eller e-post send under utrullinga.

- Brevo-overføring blir no prøvd straks etter betalingskontroll/webhook, med vedlikehaldskø som reserve. 79 Python-testar bestått.

- [x] Stadfestingsmail etter betalt innmelding, separat frå nyhendebrev; varig sendestatus og vern mot doble callbacks.
- [x] Nye Vipps-betalingar ber om samtykke til namn og telefon, lagra separat som betalaropplysningar og tekne med i personvernsletting.

- Stadfestingsmail og betalarprofil er utrulla. SMTP aksepterte stadfestinga for 6-kronersprøva. 85 Python-testar bestått. Vipps-profilsamtykket må framleis prøvast i ein ny betalingsflyt; den gamle betalinga kan ikkje få nytt samtykke i etterkant.

## Kontingentår og fornying

- [x] Årlege satsar, vedtaksdato og opningsdato; personlege fornyingslenkjer og e-postsending per medlem.
- [x] 2027 er stengt utan satsar til årsmøtet i 2027; seinare år kan vedtakast året før og opne 1. januar.
- [x] Fornying bokfører på eksisterande medlem og rett år; Kul/Superkul kan variere, Styret blir bevart.
- 96 Python-testar bestått etter fornyingsendringa. Database- og kodebackup verifiserte før utrulling. Ingen innkrevingsmail send under utrulling.
- [ ] Full fornyingsprøve med Vipps-testappen før første verkelege kontingentutsending.
