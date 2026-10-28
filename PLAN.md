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
- [ ] Kontrollert ekte produksjonsbetaling utført av brukaren.
- [ ] Stadfeste medlemsregistrering, Brevo-synkronisering og offentleg opning etter produksjonsprøva.

## Kontroll og utrulling

- 71 Python-testar bestått; Ruby-testar køyrde med Homebrew Ruby; kalendertestar og `git diff --check` bestått.
- Jekyll-bygg og visuell kontroll av mobilmeny, galleri, forklaring og innmeldingsskjema gjennomførte.
- Bygdelista er oppdatert på PythonAnywhere. Produksjonsprøve er tilgjengeleg for innlogga styremedlemmar; offentleg innmelding ventar på betalingsprøva.
- Offentleg nettside er klar lokalt, men ikkje committa eller pusha.
- Lesekontroll av produksjon viste fungerande innlogging og felles CSS, og ingen ventande Brevo-kontaktar eller slettingar. Ingen produksjonssynkronisering vart starta manuelt.

- [x] Sjølvbetent «Gløymt passord?» med e-postkode og eksisterande TOTP; avsluttar gamle innloggingar. Utrulla og skjema kontrollert på PythonAnywhere. 77 Python-testar bestått. Ingen passord er endra eller e-post send under utrullinga.
