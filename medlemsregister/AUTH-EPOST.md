# Arbeidar for eingongskodar på e-post

Implementert lokalt 26. november 2026. Ikkje sett i drift som del av kodearbeidet.
Denne kodeversjonen krev ein eigen køarbeidar før offentleg innmelding,
medlemsinnlogging, registrering av styrekonto og passordbyte blir tekne i bruk.
Den gamle timevise vedlikehaldsjobben er ikkje rask nok: kodane går ut etter
10 eller 15 minutt.

## Oppstart og utrulling

1. Ta og prøv eksisterande databasebackup. Bevar `.env` og nøklane separat.
2. Installer den samla kodeversjonen, inkludert nye modular, malar og felles CSS.
   Oppdateraren må ta med `lutar/arsmelding-tilskipingar.css`. Ingen nye
   produksjonspakkar er nødvendige.
3. Start ein eigen, overvaka prosess med appen sitt virtuelle miljø og same
   `.env`, database og øktnøkkel som webappen. Frå `medlemsregister/`:

   ```bash
   python -m flask --app app auth-epost --loop
   ```

   Kommandoen køyrer databasemigreringane før arbeidaren startar. Migrering 2
   legg til køa og kodane for nyinnmelding. Ho endrar ikkje eksisterande
   medlemmar, betalingar eller TOTP-nøklar. Verifiser prosessoppsett og automatisk
   omstart på driftsplattformen før Reload. Ein ny køyring utan `--loop` sender
   éin batch; slik køyring må i så fall planleggjast minst kvart minutt.
4. Last webappen på nytt. Prøv medlemsinnlogging og dei andre kodeflytane med
   eigne kontrollerte testadresser. Kontroller også at ukjend og kjend adresse
   får same offentlege svar, og at ingen SMTP-sending skjer i HTTP-rutene.
5. Kontroller at arbeidaren held fram å køyre etter første sending og etter
   prosessomstart. Ta ny backup. Ikkje slå av kodearbeidaren medan denne
   webversjonen er i bruk.

Ved tilbakeføring skal eldre kode ikkje køyrast mot skjemaversjon 2; den gamle
migreringskontrollen avviser ukjende versjonar. Ikkje gjenopprett ein eldre
produksjonsdatabase over nye innbetalingar. Avklar ei eventuell tilbakeføring
før utrulling.

## Vern og feilhandtering

- HTTP-rutene legg kodar i kø og ventar aldri på SMTP. Arbeidaren sender berre
  dersom utfordringa framleis er gyldig og høyrer til rett konto eller adresse.
- Køinnhaldet er autentisert kryptert med ein nøkkel avleidd frå appen sin
  eksisterande øktnøkkel. Ein databasekopi åleine røper ikkje kodane. Arbeidaren
  og webappen må bruke same nøkkel. Nøkkelbyte opphevar køinnhaldet.
- Ein atomisk reservasjon hindrar to arbeidarar i å sende same jobb. Ved
  avbrot etter reservasjon blir jobben ikkje send automatisk på nytt; dette
  unngår ukontrollerte dobbelsendingar ved uvisst leveringsutfall.
- Ved sendefeil blir utfordringa fjerna. Brukaren kan be om ny kode. Ein
  arbeidar som blir avbroten midt i sending kan etterlate ei reservert jobb;
  ho blir sletta når gyldigheitstida går ut. Ei utgått kode blir aldri send.
- Jobbar og kryptert innhald blir sletta etter handtering eller utløp. Kodar,
  e-postadresser og leverandørfeil blir ikkje skrivne i loggen.
- Rategrenser, nettlesarbinding, forsøkstak og kontroll mot tilbakekalla
  tilgang gjeld framleis. Medlemsinnlogging gir aldri styretilgang.

Lokal testkøyring behandlar køa eksplisitt med simulerte sendarar. Den isolerte
Nidarosbygda-appen sperrar ekte e-post og eksterne kall.
