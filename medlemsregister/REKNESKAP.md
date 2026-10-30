# Intern rekneskap og bilag – steg 5

Alle innlogga styremedlemmar har same tilgang på `/okonomi`, via «Årsmøte og
økonomi». Utforminga er førebels og skal få ein eigen sluttgjennomgang.
Dette er intern rekneskap. Offentleg eksport er implementert i steg 6, men
må konfigurerast og aktiverast særskilt; sjå PUBLISERING.md. Automatisk Vipps-import kjem
seinare. Ingen bankoverføring, Vipps-refusjon eller betaling blir utført frå skjemaet.

## Første oppsett

1. Ta databasebackup før oppdatering. Den nye koden opprettar `ledger_*`-tabellar
   ved vanleg initialisering. Han flyttar ikkje eksisterande medlemsbetalingar automatisk.
2. Set `BYGDELISTA_BILAG_DIR` til ei privat mappe **utanfor kode og statiske filer**.
   På PythonAnywhere er standarden `/home/oslobygda/bygdelista-data/bilag`.
   Mappa blir oppretta ved første opplasting/backup. Ingen statisk webkopling skal
   peike til mappa. Mapper får tilgang 700, filer 600. Bilaga er ikkje krypterte på disk
   av denne funksjonen. Filrettar og innlogging er tilgangsvernet.
3. Dokumenter inngåande balanse i første rekneskapsår. Nullsaldo er eit uttrykkeleg
   val som krev forklaring. Pengar og gjeld frå før bankkontoen vart oppretta må
   inngå. Skjemaet støttar éin namngitt kreditor per gjeldskategori i opningsbalansen.
   Ved meir samansett historikk må me utvide opningsrutinen før reelle tal blir importerte.
4. Før seinare feil i opningssaldo gjennom «Korriger inngåande balanse» i første
   året. Oppgi full korrekt saldo; programmet fører differansen og bevarer originalen.
   Seinare års opningssaldoar blir førte vidare frå tidlegare postar, utan ny duplisering.

## Registrering

Beløp er i NOK og blir lagra i heiltalsøre. Bruk dokumentert faktisk NOK-beløp;
original valuta og grunnlaget for beløpet kan noterast internt. Bruk rett kategori:
kontingent, gåver/tilskot, andre inntekter, domene, drift, e-post, arrangement og gebyr.

- **Inntekt:** bank/Vipps/kontantar mot inntektskategori.
- **Utgift betalt av laget:** kostnad mot bank/Vipps/kontantar.
- **Utgift betalt privat:** kostnad mot gjeld til namngitt intern utleggshavar.
- **Refunder privat utlegg:** reduserer gjelda og bank, utan ny kostnad. Refusjonen
  kan ikkje vere større enn registrert gjeld til vedkomande på oppgjersdatoen.
- **Ubetalt rekning / betal registrert rekning:** tilsvarande leverandørgjeld og oppgjer.
- **Vipps-oppgjer:** brutto blir redusert på Vipps, netto til bank og gebyr til kostnad.
  Dette føreset at bruttoinntekta alt er registrert. Har du alt ført gebyret særskilt,
  oppgir du null gebyr i oppgjeret, slik at det ikkje blir talt to gonger.
- **Overføring:** mellom bank, Vipps og kasse, utan ny inntekt.
- **Refusjon av inntekt:** viser til originalpost, held greie på delrefusjonar og
  hindrar at samla refusjon blir større enn originalinntekta. Dette er registrering
  av ei allereie utført tilbakebetaling, ikkje ein Vipps-refusjonsknapp.

Legg ved bilag eller forklar dokumentasjonsgrunnlaget. Offentleg eigna skildring
og intern merknad er separate. Alle registreringar får ansvarleg styrebrukar,
tidspunkt og fast intern post-ID. Kalender-UID kan knyte ein post til eit arrangement.

Betalings-ID frå Bygdelista kan koplast manuelt berre til ei medlemsinntekt med
same beløp. Den same betalinga kan ikkje bokførast på nytt. Manuelle medlemsbetalingar
som er kopla til rekneskap kan ikkje slettast frå medlemsregisteret. Refusjonar her
endrar førebels ikkje medlemsstatus eller Vipps-ordrar; dette må følgjast opp ved
avstemming og den seinare integrasjonen. Kontroller kjeldedato og historisk import
før kopling – systemet gjettar ikkje medlem ut frå Vipps-betalaren.

## Retting, periodisering og årsavslutning

Bokførte postar og linjer er verna mot endring og sletting i databasen. Reversering
lagar nye motpostar med årsak og kopling. Før deretter ny korrekt post. Oppgi ei
retterekneskapsdato som ikkje er før originalen; avslutta år må eventuelt opnast att.
Ved periodisert abonnement reverserer rutinen originalen og dei tilhøyrande
periodiseringane samla i éin transaksjon. Ho bevarer datoen for framtidige periodar
når dei er seinare enn vald rettingsdato. Dersom eit av åra er avslutta, blir heile
reverseringa avvist. Originalinntekt med registrerte refusjonar er sperra for enkel
reversering; slike samansette rettingar må gjennomgåast særskilt.

Abonnement med tenesteperiode over nyttår kan fordelast etter kalenderdagar, med
restøre i siste år. Perioden må byrje i utgiftsåret. Den framtidige kostnaden står
som forskotsbetalt og blir sleppt til kostnad 1. januar i kvart tilhøyrande år.
Dette er årleg fordeling, ikkje månadleg kostnadsføring. Andre periodetilfelle krev
særskild utforming før dei blir førte. Allereie reversert/periodisert utgift blir avvist.

Avstem bank, Vipps og private utlegg samla, og andre ikkje-null saldoar, ved årsslutt.
Årslukking krev dokumentert inngåande balanse og avstemming med null differanse
etter siste bokføring. Motpartsvis avstemming kan leggjast til, men erstattar ikkje
samla kontroll. Tidlegare opne år må avsluttast først. Gjenopning krev grunngiving;
seinare avslutta år må opnast først fordi balansen deira kan bli påverka.

Årslukking er skild frå medlemsår og frå årsmøtegodkjenning. Laget har ingen revisor.
Rekneskapsvisinga viser førebelse kategori-/kontosaldoar og resultat. Full offentleg
balanse og presentasjon kjem i steg 6. Eigenkapitalen omfattar inngåande eigenkapital
pluss akkumulerte resultat. Personlege motpartar er berre interne.

## Bilag

PDF, JPEG og PNG blir godtekne med kontroll av filending og signatur, inntil 10 MiB
per fil / 20 MiB per opplastingsførespurnad. Dette er ikkje full skadevareskanning.
Filene får tilfeldige lagringsnøklar og lagra SHA-256 og storleik. Nedlasting krev
styreinnlogging kvar gong, blir levert som vedlegg og har `no-store` og `nosniff`.

Ein post kan ha fleire bilag og eit bilag kan brukast av fleire postar. Nye vedlegg
kan leggjast til med postnummeret medan året er ope. Feil vedlegg kan erstattast av
eit nytt bilag med referanse og grunngiving; originalen og historikken blir bevarte.
Det finst inga vanleg sletting eller overskriving av originalbilag. Ved nødvendig
personvernretting må ein eigen kontrollert administratorrutine også ta omsyn til backup.

`flask --app app okonomi-kontroller-bilag` sjekkar dokumenterte filer og tel ukjende
filer. Han slettar ingenting. Dette kan finne foreldrelause filer etter prosessavbrot.

## Samla backup

Den vanlege `backup.py` oppdagar økonomitabellane og lagar då eit samla backupsett,
med database, alle registrerte bilag og manifest. Før økonomimodulen er initialisert,
beheld skriptet den gamle databasebackupen. `--verify` godtek både gamal databasefil
og ny backupmappe. Bruk same virtuelle miljø som appen.

Ved eigne bilagsstiar i `.env` bruker de `backup_kommando.py` eller gir `--bilag-dir`
uttrykkeleg til `backup.py`. Desse vala må samsvare med appen. Manglande bilag gjer
at backupen feilar; han rapporterer ikkje ein ufullstendig kopi som komplett.

Frå medlemsregister-mappa, alternativt med Flask:

```bash
python -m flask --app app okonomi-backup --directory /home/oslobygda/Bygdelista-backup
python -m flask --app app okonomi-verifiser-backup /sti/til/okonomi-DATO-ID
```

Backupjobben tek eksklusiv bilagslås, bruker konsistent SQLite-kopi, kontrollerer
alle referansar og filhashar, og prøver gjenoppretting i ei ny mellombels mappe.
Først etter vellukka kontroll blir settet ferdigstilt og gamle komplette sett roterte.
Standard er 30 komplette sett, ikkje 30 dagar. Gamle databasekopiar blir ikkje
slettautomatisk av den nye rotasjonen. Kontroller plassbruk innanfor 5 GB-kvoten.

**Setta er lokale og ukrypterte, med private filrettar.** Koden lastar ikkje opp til
Proton. Kryptert eksport og isolert gjenopprettingsprøve er implementerte; sjå
[BACKUP.md](BACKUP.md). Passfraserutine og faktisk Proton-rundtur må prøvast før
ekstern backup med verkelege data. SQLCipher er ikkje støtta av denne standard-SQLite-backupen.
Originaldata blir aldri bytte ut av verifikasjonskommandoane. Ei faktisk gjenoppretting
krev stansa app, verifisert sett og kontrollert bytte av både database og bilagsmappe.

## Verifikasjon

Nye testar i `tests/test_rekneskap.py` bruker isolerte databasar og fiktive vedlegg.
Dei dekkjer mellom anna private utlegg, refusjon utan ny kostnad, brutto/gebyr/netto,
partialrefusjon, balanserings- og historikkvern, periodisering/reversering, årsavstemming,
opningskorreksjon, bilagstilgang, feilformat, standardbackup, rotasjon, gjenoppretting,
filkorrupsjon og betalingskopling. Ingen faktisk bank eller Vipps blir kontakta.


## Oppdatering etter steg 8

Kontrollert medlemsinntektsimport er no tilgjengeleg frå økonomisida. Sjå
BETALINGSIMPORT.md for historisk attestering, kopling til eksisterande postar,
kjeldedato frå Vipps og opt-in for nye ePayment-inntekter. Ingen faktisk innhenting
eller bokføring er aktivert av utviklingsarbeidet. Refusjonar, gebyr og bankoppgjer
blir framleis avstemde manuelt.


## Utskrift etter steg 9

Faste versjonar har no eiga utskriftsvising for lagring som PDF i nettlesaren.
Sjå [UTSKRIFT.md](UTSKRIFT.md). Faktisk PDF-paginering skal kontrollerast visuelt
i sluttgjennomgangen før produksjonsbruk.

## Kategoriar før første produksjonsføring

Innkome: Medlemspengar, Tilskot, Gåver, Tilskipingar, Renteinnkome og Anna innkome.
Utgifter: Digitale tenester, Tilskipingar, Betalings- og bankgebyr og Andre utgifter.
Digitale tenester omfattar òg domene, PythonAnywhere og e-post. Dei tidlegare eigne
kategoriane er fjerna etter avklaring om at ingen reelle tal er førte enno.
Kategorinotar finst i `_data/rekneskapskategoriar.json`, og fila blir teken med av
oppdateringsskriptet. Renter blir registrerte som Innkome, Bank, Renteinnkome, med
beløp og bokføringsdato frå kontoutskrifta. Ingen automatisk renteimport er laga.
