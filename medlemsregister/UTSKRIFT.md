# Utskrift og PDF frå nettlesaren – steg 9

Kvar lagra årsmeldings-, rekneskaps- eller budsjettversjon har lenkja
**Utskriftsvising / lagre som PDF**. Ho opnar ei eiga side, utan administrasjonsfelt,
køstatus eller interne opplysningar. Utskrift er lesing: inga bokføring, kølegging
eller publisering blir utført.

1. Opne den faste versjonen de skal sende ut. Kontroller rapport-/budsjettår,
   møteår, status og eventuell vedtaksdato.
2. Opne utskriftsvisinga. Trykk «Skriv ut / lagre som PDF».
3. Vel A4, 100 % skala og «Lagre som PDF» som skrivar. Slå av nettlesaren sine
   topp-/botntekstar dersom dei legg til nettadresse og dato.
4. Sjå gjennom alle sidene i førehandsvisinga, særleg lange transaksjonslister,
   før lagring eller utsending. Kontroller at alle beløp og siste avsnitt er med.

URL-ar (styreinnlogging er påkravd):

- `/arsmote/utskrift/arsmelding/<versjons-ID>`
- `/arsmote/utskrift/rekneskap/<snapshotnummer>`
- `/arsmote/utskrift/budsjett/<snapshotnummer>`

Visingane bruker berre den lagra offentlege dokumentkopien. Årsmeldingsteksten blir
ikkje henta på nytt frå kalenderen, og økonomital blir ikkje rekna om frå levande data.
Ei utskrift av ein tidlegare versjon er dermed uendra etter nye føringar. Eit lagra
førebels rekneskapssnapshot kan òg skrivast ut og er tydeleg merkt «Førebels».

## Innhald og oppsett

- Oslobygda kulturlag, dokumenttittel, rapport-/budsjettår, møteår, versjon og status.
- Vedtaksdato berre når dokumentet er godkjent.
- Årsmelding med all lagra tekst og avsnitt, med HTML-escaping av fri tekst.
- Rekneskap med kategorisummar, resultat, inngåande/utgåande balanse og offentlege
  transaksjonsdetaljar. Kontingent er framleis berre samla årssum.
- Budsjett med førre års tal, status på samanlikningsgrunnlaget, summer og offentlege
  føresetnader. Manglande rekneskap blir ikkje framstilt som stadfesta nulltal.
- A4-oppsett og printmargar. Balansen blir halden samla. Transaksjonar blir viste
  som sjølvstendige postar med dato, offentleg bilagsnummer, beløp og skildring,
  slik at tolkinga ikkje er avhengig av gjentekne tabelloverskrifter.

Programmet genererer ikkje ei eiga PDF på serveren. Nettlesaren står for PDF-fil
og endeleg paginering. Utskrifts-CSS finst i `fast/arsmote-utskrift.css`. Ingen nye
Python-pakkar, eksterne skrifttypar eller PDF-tenester er nødvendige i produksjon.
Automatisk samanslått årsmøtepakke er framleis eit mogleg seinare tillegg.

## Verifikasjon og attståande visuell kontroll

Automatiserte testar i `tests/test_arsmote_utskrift.py` kontrollerer alle tre
visingane, innlogging, manglande versjonar, uendra tekst etter redigering, lange
avsnitt, escaping, dato/status, eksakte budsjettbeløp og fråvær av interne data.
Utskriftsrutene skriv ikkje til database eller publiseringskø.

Safari-PDF er visuelt kontrollert med fiktive data 29. oktober 2026: årsmelding
på to sider, budsjett på éi side og rekneskap på sju sider med 40 lange prøvepostar
og eitt ekstra utlegg. Alle detaljpostane og siste avsnitt er med. Balansen er samla,
og transaksjonane blir ikkje delte ved sideskift i denne prøva.

Kontroller endelege dokument på nytt før utsending: anna innhald, svært lange
enkeltpostar, nettlesar og utskriftsinnstillingar kan endre pagineringa.
