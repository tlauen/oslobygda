# Årsmelding: lagring og publisering

Årsmeldingane ligg under **Årsmøte → Årsmelding**. Rapportåret er året teksten
handlar om; møteåret er året årsmøtet blir halde.

## Dagleg flyt

1. Opprett eller opne årsmeldinga. Hent kjelder og rediger teksten.
2. **Lagre utkast** tek vare på arbeidet internt. Nettsida blir ikkje endra.
   Lagringsoversikta viser tidspunkt og revisjon. Ulagrede endringar blir merkte
   i skjemaet; det er inga automatisk lagring.
3. Opne **Førehandsvis lagra årsmelding** og kontroller innhald og personvern.
4. **Lagre og publiser framlegg** lagrar skjemaet, lagar ein fast kopi og prøver
   å sende berre denne kopien til nettsida. Du kjem til kopien med resultatet.
5. Dersom sending eller bygg ikkje er ferdig, vent litt og bruk
   **Kontroller publisering / prøv igjen** på kopien. Opne deretter nettsida og
   kontroller sjølve visinga og PDF-en.
6. Etter faktisk årsmøtevedtak: lagre utkastet og bruk
   **Etter årsmøtet: publiser godkjend årsmelding**, med rett vedtaksdato.

## Kva statusen tyder

- **Ikkje sendt til nettsida:** fast kopi er lagra internt, utan publiseringsjobb.
- **Ventar på sending / Sending pågår:** jobben er kølagt eller under arbeid.
- **Sendt – ventar på nettsidebygg:** innhaldet er kontrollert i GitHub. Nettside
  og PDF kan framleis vere under bygging.
- **Publisering stadfesta:** kopien er funnen i den offentlege eksporten.
  Dette er ikkje ein visuell kontroll av HTML eller PDF.
- **Publisering feila:** kopien er teken vare på. Sjå feilmeldinga og prøv igjen
  etter at årsaka er retta.

Arbeidsutkast, faste kopiar og publisering er separate. Nye endringar i utkastet
endrar ikkje eldre kopiar eller ei publisert årsmelding. Oversikta merkar når
utkastet skil seg frå siste faste kopi. Same uendra innhald blir ikkje til ein
ny kopi berre fordi du trykkjer igjen.

Nettsida prioriterer godkjende årsmeldingar framfor førebelse framlegg. Ei ny
førebels utgåve erstattar difor ikkje ei eksisterande godkjend utgåve på årssida.
Historikken viser kvar kopi og sin eigen publiseringsstatus.

## Kjeldedata og vern

Lagre teksten før du hentar kalender, styre eller medlemstal. Import bevarer
kommentarar og val. Nye kalenderaktivitetar er valde som standard. Godkjend
årsmelding krev avklart status og gjennomgåtte kjeldeendringar for valde aktivitetar.
Faste kopiar bevarer strukturen og bileta som var valde då kopien vart laga.

Berre tillatne offentlege felt blir eksporterte. Intern brukarhistorikk,
medlemsidentitetar og betalingsdetaljar følgjer ikkje med. Fri tekst må kontrollerast
av styret. Ingen publisering blir starta berre ved å opne eller oppdatere ei side.
Sjå [PUBLISERING.md](PUBLISERING.md) for tilgang, kø og eventuell driftsjobb.

## Kontroll ved kodeendringar

Køyr `python -m unittest discover -s tests` frå `medlemsregister/`, med
avhengnadene i testmiljøet. Bruk fiktive data og simulerte publiseringsklientar.
Eksisterande migreringar og tryggleikskopiar omfattar årsdokumenttabellane.
