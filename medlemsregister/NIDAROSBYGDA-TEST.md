# Nidarosbygda kulturlag – isolert testmiljø

Status: førebuing. Lokal branch `test/nidarosbygda` er oppretta. Ingen push,
serverendring, produksjonsdatabase eller integrasjon er endra. Dagens lokale
prøveapp er framleis ein mellombels prøveapp; han er ikkje det ferdige testmiljøet.

## Først: avklar kapasitet på PythonAnywhere

Opne Web-fana og sjå om kontoen kan ha ein ekstra webapp. Ikkje endre den
noverande webappen, WSGI-fila, virtuelle miljøet eller dei statiske koplingane.
Noter eventuell tilgjengeleg ekstra appadresse. Ikkje del passord, nøklar eller .env.
Ingen ny konto, abonnement eller DNS-endring treng gjerast før kapasiteten er avklart.

## Mål for oppsettet

- Namn: Nidarosbygda kulturlag, med tydeleg TESTMILJØ på alle sidene.
- Kode: eiga utsjekking av `test/nidarosbygda`, skild frå produksjonsmappa.
- Data: eiga privat mappe, eigen database, bilag og backup; berre fiktive data.
- App: eiga adresse, WSGI-fil, virtuelt miljø, øktnøkkel og test-styrekontoar.
- Integrasjonar: ekte Vipps, SMTP/Brevo, GitHub-publisering og produksjonskalender
  skal vere sperra. Testpålogging skal ikkje gi tilgang til produksjonsregisteret.
- Drift: ingen kopi av produksjons-.env, database, bilag eller planlagde jobbar.
  Testjobbar skal aldri bruke produksjonsmapper eller produksjonstoken.

Føreslegne servermapper, ikkje oppretta enno:

- `/home/oslobygda/nidarosbygda-kode`
- `/home/oslobygda/nidarosbygda-data`
- `/home/oslobygda/.virtualenvs/nidarosbygda`

## Arbeid før oppstart

1. Legg til eksplisitt miljøval med separat konfigurasjonsfil og database-/bilagssti.
   Dagens app lastar medlemsregister/.env og brukar ein fast DB_PATH; dette må endrast
   før ein separat teststart kan godkjennast.
2. Gjer lagsnamn og testmerking konfigurerbare. Testnamn skal ikkje krevje endring
   av alle malar eller skrivast inn i produksjonsinnstillingane.
3. Sperr utgåande integrasjonar i testmiljøet, også ved CLI-køyring. Manglande
   produksjonsnøklar åleine er ikkje nok som vern mot utilsikta feilkonfigurasjon.
4. Lag trygg oppretting av fiktiv database og eigne testkontoar utan å lese
   produksjonsdata. Testkontoen skal følgje vanleg innlogging, ikkje demo-omgåinga.
5. Test isolasjonen: ingen skriving utanfor testmappa, ingen innlasting av
   produksjons-.env, ingen utgåande produksjonskall og inga delt innloggingsøkt.
6. Commit/push og opprett ekstra webapp først når isolasjonen er implementert og
   kapasiteten er stadfesta. Bruk eiga WSGI-fil og eigne statiske filkoplingar.
7. Prøv heile arbeidsflyten med fiktive data før eventuell utrulling til Oslobygda.

## Git og seinare overføring

Ein branch skil kjeldekode, ikkje data eller tenestetilgang. Dei eksisterande
lokale endringane følgjer arbeidsmappa over på testbranchen og er enno ikkje committa.
Generelle funksjonar og feilrettingar skal seinare kunne takast inn i produksjon;
testnamn og testdata skal styrast gjennom konfigurasjon og privat datamappe.
Produksjonsoppdateringa frå main ventar medan dette blir sett opp.

## Lokalt testmiljø er no implementert

Køyr `medlemsregister/lokal_test.py` som eigen prosess. Standardadresse er
http://127.0.0.1:8877/testkonto og standard datamappe er
`~/Documents/Codex/nidarosbygda-test`. I denne arbeidsøkta er miljøet starta med:

    /private/tmp/bygdelista-nyinnmelding-venv/bin/python medlemsregister/lokal_test.py

Denne Python-stien er mellombels. For eit varig oppsett kan ein opprette eit eige
virtuelt miljø utanfor repoet, installere requirements-pythonanywhere.txt der og
bruke Python frå det miljøet til same startkommando. Ingen PythonAnywhere-app trengst.

- `/testkonto` viser berre dei lokale testinnloggingsopplysningane og gjeldande
  TOTP-kode. Opne vanleg innlogging og kopier opplysningane. Sida er medvite open
  på loopback for enkel testing; ikkje bruk verkelege data eller eksponer porten.
- Vanleg passord-/TOTP-innlogging er bevart. Ingen automatisk styreinnlogging.
- Tre fiktive medlemmar er oppretta med example.invalid-adresser. Rekneskapen er
  tom, slik at ein kan prøve frå inngåande balanse. Data blir bevarte ved omstart.
- Kalenderen blir lesen og lagra i testmappa, utan GitHub. Han startar tom.
- Lagsnamn i malane og testbanner er sette av den lokale startaren. Produksjonsmalar
  og produksjonsnamn er ikkje erstatta globalt.
- Produksjons-.env blir ikkje lasta. Arva Vipps/GitHub/Brevo/SMTP-innstillingar blir
  fjerna. Ekte Vipps-innmelding er avslått.
- Prosessen avviser utgåande nettverk (inkludert eksterne namneoppslag), eksterne
  prosessar, databaseopning og filskriving utanfor den private testmappa. Serveren
  bind berre loopback. Dette er vern mot feilkonfigurasjon i lokal testing, ikkje
  ei løysing for å køyre ukjend eller fiendtleg kode.
- Offentleg publisering og eksterne integrasjonar kan ikkje prøvast ende til ende
  her. Skjema, interne kopiar og utskrift kan prøvast; ekte tenester er sperra.

For isolasjonskontroll, bruk ei eiga tom prøvemappe (kommandoen opprettar fiktive data):

    python medlemsregister/lokal_test.py --data-dir /sti/til/ny-tom-provemappe --check

Kontrollen prøver vanleg innlogging, sentrale sider, sperra nettverk, sperra
filskriving og sperra database utanfor testmappa. Ei ikkje-tom mappe utan testmarkør
blir avvist. `testkonto.json` inneheld berre lokale testløyndomar og har filrettar 600.

Første prøverunde: logg inn → opne Hjelp → registrer null opningsbalanse → last opp
fiktivt bilag → før privat utlegg → kontroller gjeld/balanse → lag budsjett → legg
inn ei lokal tilskiping og hent henne til årsmeldinga. Ikkje bruk ekte kvitteringar.
Den tidlegare mellombelse prøveappen på port 8767 er stoppa.

## Styret

Lokal side: http://127.0.0.1:8877/styret. Endringar blir lagra i testmappa/styre.yml
og testmappa/styreportrett, ikkje i nettsiderepoet. Årsmeldinga hentar desse dataa
med «Hent styret». Nettsidepakken kan lastast ned frå Styret-sida. Pakken inneheld
YAML og bilete; inga automatisk GitHub-publisering skjer. Den oppdaterte backuprutinen tek med styredata og portrett. Den lokale kalenderfila
er framleis testdata; produksjonskalenderen blir bevart i Git.
