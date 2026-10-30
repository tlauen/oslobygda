# Sluttkontroll før produksjonsbruk

Status 29. oktober 2026: lokal implementasjon, ingen utrulling eller reell publisering.
Alle 154 Python-testar passerer med fiktive data. SQLCipher er ikkje testa eller
støtta av den nye standard-SQLite-backuprutinen.

## Attståande i prioritert rekkjefølgje

1. **Endelege PDF-ar:** lokal Safari-prøve er kontrollert for alle tre dokumenttypar.
   Den lange rekneskapen har no samla balanse og sjølvstendige transaksjonspostar;
   alle sju sider er inspiserte. Kontroller dei endelege reelle sakspapira på nytt.
2. **Utsjånad:** årsmelding, rekneskap og budsjett er kontrollerte ved 393 px breidd
   i Safari si responsive vising. Økonomitabellane passar sida; på smal skjerm
   blir kvar kategori vist over tala. Kompakt vising er valfri på større skjerm.
   Årsmeldingslagring er prøvd på datamaskin. Brukaren si vurdering av utsjånaden og eventuell prøve på faktisk telefon står att.
   Tastaturprøve i Safari er utført for dei sentrale skjemaa; sjå nedanfor.
3. **Før oppdatering:** ta og verifiser eksisterande databasebackup. Kontroller at
   bilag og backup ligg utanfor repo og offentlege statiske mapper. Kontroller 5 GB-kvoten.
4. **Utrulling:** gjennomgå diff, installer avhengnader i rett virtuelt miljø,
   køyr den dokumenterte databaseinitialiseringa og last webappen på nytt. Køyr
   innlogging, lagring og bilagskontroll. Avtal produksjonsoppdateringa særskilt.
5. **Ekstern backup:** oppbevar passfrase separat, lag kryptert eksport, last opp
   til laget sin Proton Drive, last ned att og prøv dekryptering/gjenoppretting.
   Lokal kryptering, feil passfrase og manipulerte filer er testa; Proton-rundtur står att.
6. **Reelle tal:** Torbjørn fører opningsgrunnlag, inntekter og private utlegg med bilag.
   Avstem bank og Vipps; kontantbetaling vidareført via Vipps skal berre telje éin gong.
   Refusjon av private utlegg reduserer gjeld og er ikkje ny kostnad.
7. **Publisering:** set opp avgrensa dokumenttoken og offentlege sidestubbar etter
   PUBLISERING.md. Kontroller offentleg innhald før aktivering. Stadfest både lagra
   GitHub-data og synleg nettside. Ingen verkeleg publisering er testa enno.
8. **Betalingsjobb:** prøv lesetilgang mot rett produksjonssalseining etter
   BETALINGSIMPORT.md. Aktiver først etter opningsavstemming. Historiske samlepostar,
   refusjonar, gebyr og oppgjer krev framleis manuell kontroll.
9. **Årsmøtet:** stadfest datoar med Kaffistova. Lag faste framlegg når innhaldet er
   kontrollert; årsmøtet godkjenner rekneskapen. Lag godkjende versjonar etter vedtak.

Ingen lokale prøveappar eller fiktive testdatabasar skal kopierast til produksjon.

## Tastaturkontroll 29. oktober 2026

Prøvd i lokal prøveapp med berre fiktive data:

- Navigasjon fram og tilbake med Option+Tab / Option+Shift+Tab i Safari-oppsettet
  som er i bruk. Vanleg Tab flyttar mellom tekstfelta, men tek ikkje med alle lenkjer
  og knappar i dette oppsettet. Ingen nettlesarinnstilling vart endra.
- Budsjett: rekkjefølgje gjennom navigasjon, felt, tabell og knappar; synleg blå
  fokusmarkering; avkryssing med mellomrom og lagring med Enter. Revisjon vart oppdatert.
- Årsmelding: gjennomgang til aktivitetar, statusval, kommentarar, avslutning og
  lagringsknapp; aktivitetsval av/på med mellomrom; lagring med Enter stadfesta.
- Rekneskap: tilgang til årsfelt, lenkjer og bilagsveljar; balansepanelet kan opnast
  og lukkast med mellomrom og felta kan nåast utan fokusfelle. Ingen bokføring utført.
- Ved 393 px breidd vart det opphavlege rulleoppsettet testa. Etter designendringa
  passar tabellen breidda, og kategori og tal er kontrollerte utan sidelengs rulling.

Ingen tastaturfeil vart funnen i desse flytane, så kodeendring var ikkje nødvendig.
Dette er ein avgrensa manuell funksjonskontroll, ikkje ei full tilgjengelegheits-
sertifisering eller skjermlesartest. Betalingsaktivering, faktisk filopplasting og
publisering vart ikkje utløyste av denne testen.

## Samla lokal sluttkontroll – 29. oktober 2026

- 153 eksisterande Python-testar passerte samla. Ein ny oppstartstest passerte
  etterpå: dobbel initialisering bevarer styrekontoar, bokførte postar, faste
  dokument, publiseringskø og innstillingar. Ho aktiverer ikkje betalingsimport.
- To testar av oppdateringsskriptet, fullt Jekyll-bygg og diff-kontroll passerte.
- Eit separat Jekyll-bygg med fiktivt budsjett og rekneskap kontrollerte også
  publikumsmalane med reelt strukturert innhald: kategoriar, notar og delsummar på
  rett plass. Ingen testtal er skrivne til repoet sine offentlege datafiler.
- Bilagsvern, balansering, autentisering, CSRF, immutable historikk, opt-in,
  kryptert eksport og isolert gjenoppretting er dekte av testane. Dette er ingen
  garanti for feilfri drift; faktiske tenestekontoar og servermiljø er enno ikkje prøvde.
- Hjelpesida og siste språk-/designendringar er inkluderte i lokal kontroll.

**Resultat:** klar for neste steg, kontrollert serveroppdatering med verifisert
backup først. Ikkje ferdig godkjent for aktivering av offentleg publisering eller
betalingsautomatikk. Kontroller endelege PDF-ar på nytt med dei nye kategoriane
og faktiske tala før utsending; dei tidlegare Safari-prøvene brukte eldre fiktive kategoriar.

## Konkret rekkjefølgje ved oppdatering

1. Kontroller gjeldande serveroppsett og Python-versjon. Bruk eksisterande
   virtuelle miljø; ikkje opprett det på nytt. Ta konsistent backup av eksisterande
   database med den noverande rutinen, og prøv kopien før skjemaendringar.
2. Gjer den lokale leveransen tilgjengeleg i Git etter gjennomgang. Oppdater
   serverkopien av oppdateringsskriptet etter PYTHONANYWHERE.md. Den nye fila
   `_data/rekneskapskategoriar.json` må vere med før Reload; gammalt skript tek
   henne ikkje med. Køyr ny skriptversjon før appen blir lasta på nytt.
3. Installer `requirements-pythonanywhere.txt` i det eksisterande appmiljøet.
   Dette tek med cryptography til kryptert eksport. Kontroller at importane fungerer.
4. Stadfest privat bilagsmappe utanfor repo og statiske mapper. Last webappen på
   nytt. WSGI kallar `init_db()`; nye tabellar blir oppretta ved oppstart. Ingen
   prøveapp eller lokal database skal kopierast til serveren.
5. Kontroller innlogging, hjelpeside, kategoriar, lagring og bilag. Ta eit nytt
   komplett økonomibackupsett og prøv gjenoppretting. Kontroller diskbruk.
6. Prøv kryptert eksport og ekstern Proton-rundtur før reelle økonomidata blir lagde
   inn. Publisering og betalingsimport blir verande avslått fram til eigne prøver.

Dersom oppstart feilar: stopp vidare innlegging, les feilen utan å dele løyndomar,
og undersøk kode/avhengnader før ny Reload. Kodebackup er ikkje databasebackup.
Ikkje rull databasen tilbake medan appen tek imot endringar.
