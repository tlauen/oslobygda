# Sakliste og møtereglar

I Årsmøte og økonomi: vel **Sakliste og møtereglar**. Opne eit årsmøteår,
legg til saker og flytt dei med Opp/Ned. Kvar sak har tittel, omtale av saka, eige felt for forslag til vedtak
og valfri lenkje til årsmelding, rekneskap eller budsjett for eit valt år.
Nye saklister får standardmalen med organisering, årsmelding, rekneskap,
medlemspengar, planar, budsjett, ymse og val. Rapportane gjeld året før møtet,
medlemspengar året etter og planar/budsjett møteåret. Dokumentlenkjer blir
fylte ut når årssidene er klargjorde. Eksisterande utkast blir ikkje endra.
Undersaker blir skrivne éi per linje utan nummer; visinga nummererer automatisk
saker og undersaker (1.1, 1.2 osv.). Knappen for lovendringar legg ei valfri sak
før Ymse; seinare saker får automatisk nye nummer.

Saklista brukar møteåret; dokumentlenkjene kan vise til andre rapportår.

Møtereglane er felles for alle år og blir redigerte under saklisteoversikta.
Utgangspunktet er teksten i `_data/motereglar.json`, som berre blir lesen inn
ved første oppretting. Seinare oppstart overskriv ikkje redigerte reglar.
Bruk `## Mellomtittel` og tom linje mellom avsnitt. Teksten blir HTML-escapa.

Lagre, opne førehandsvisinga og vel **Publiser**. Publisering krev stadfesting,
frys den lagra revisjonen og brukar same GitHub-kø og vedlikehaldsjobb som dei
andre årsdokumenta. Feila sending kan prøvast igjen med publiseringsknappen.
Utkast er interne; lagring åleine oppdaterer ikkje nettsida. Køstatus skil
mellom sendt til GitHub (`stored`) og stadfesta synleg (`visible`).

Offentleg inngang: `/om/saklister/`, med publiserte saklister først og felles
møtereglar under. Nyaste publiserte revisjon blir vist. Gamle publiseringskopiar
blir bevarte i årsdata. Saklister blir viste som nettsider, utan PDF-generering.

## Nye år og utrulling

Sidestubbar for sakliste 2026 og 2027 er klargjorde. Ved nytt møteår: legg til
`om/saklister/<år>/index.md` med `meeting_year` som streng og include
`sakliste.html`, og `api/arsdokument/<år>.json` som for dei andre årsdokumenta.
Publiser desse før saklista blir send frå Bygdelista. Møtereglane bruker
inneverande år si API-fil, men krev ikkje ei årsfesta saklisteside.

`_data/arsmotesider.json` inneheld dokumentår som kan veljast i Bygdelista.
Oppdater denne når nye årssider for årsmelding, rekneskap og budsjett blir
klargjorde. Filene er inkluderte i oppdateringsskriptet for PythonAnywhere.

Databasetabellane `meeting_drafts` og `meeting_publication_queue` blir oppretta
av vanleg `init_db`; dei er med i ordinær databasebackup. Publiser nettsidekoden
og oppdater Bygdelista før den nye dokumenttypen blir brukt i publisering.

## Protokoll rett i Bygdelista

Opne ei lagra sakliste og vel **Før protokoll / sjå godkjenningar**. Første
protokollutkast er ein kopi av sakene og undersakene. Forslag til vedtak blir
tekne med som framlegg; vedtaksfeltet blir ståande tomt til møtet har avgjort saka. Fyll inn møtedato,
protokollskrivar og innleiing. Kvar sak har eigne felt for framlegg og
framleggsstillarar, dei som tok ordet, røysteresultat og vedtak. Skriv
«Ingen vedtak» når saka ikkje førte til vedtak. Lagre undervegs og kontroller
førehandsvisinga.

Styret kan sende protokollskrivaren ei personleg e-postlenkje med skrivetilgang
til berre protokollen for dette møteåret. Tilgangen gjeld i 30 dagar og krev
ikkje styrekonto. Styret kan sende ny lenkje eller trekkje tilgangen tilbake.
Den gir ikkje tilgang til medlemsregister, økonomi eller andre protokollar.

Protokollskrivaren registrerer namn og kvar si e-postadresse til dei to valde
protokollunderskrivarane og vel **Send personlege godkjenningslenkjer**. Begge
får den same faste kopien. Lenkjene gjeld i 14 dagar. Å opne ei lenkje gjer
ikkje vedtak; mottakaren må lese kopien, stadfeste og trykkje **Godkjenn**,
eller sende ei forklaring på kva som må rettast.

Endring i utkastet medan godkjenninga pågår avsluttar den gamle runda.
Begge må godkjenne ein ny kopi. Ein førespurnad om retting stoppar òg runda.
Ei tidlegare ferdig godkjend kopi blir verande som historikk; ny tekst blir
ikkje publisert før begge har godkjent den nye kopien.

Når den andre underskrivaren godkjenner, blir den faste kopien lagd atomisk i
publiseringskøa, og Bygdelista prøver å publisere han med ein gong. Ingen
publiseringsknapp eller konsollkommando er nødvendig. Publisert protokoll
blir vist på årssida under saklista, med lenkje frå oversikta. Berre namn og
godkjenningstidspunkt blir publiserte; e-postadresser, tilgangslenkjer og
merknader frå godkjenningsrunda blir verande internt.

### Automatisk nytt forsøk og førstegongsoppsett

Den automatiske GitHub Actions-jobben i `.github/workflows/protokoll-publisering.yml`
kallar eit avgrensa publiseringsendepunkt kvart kvarter. Han sender på nytt ved
mellombels feil og kontrollerer om GitHub Pages har fått den godkjende kopien.
GitHub kan forseinke planlagde køyringar. Han behandlar berre godkjende
protokollar, og brukar den eksisterande delte publiseringslåsen. Ingen treng
å starte ein konsollkommando for kvar protokoll.

Ved utrulling må desse innstillingane gjerast éin gong gjennom dei vanlege
innstillingssidene:

- Same tilfeldig løyndom på minst 32 teikn som `BYGDELISTA_PUBLICATION_TOKEN`
  i servermiljøet og i GitHub → Settings → Secrets and variables → Actions.
  Han er ein eigen jobbtoken, ikkje GitHub-dokumenttokenen.
- Aktiver GitHub Actions og den planlagde jobben på standardgreina.
- Behald eksisterande `GITHUB_DOCUMENTS_TOKEN` på serveren for GitHub-overføringa.
- Bruk eksisterande SMTP-oppsett: `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`,
  `SMTP_PORT` og `STYRE_EPOST_FRA`.
- Ved anna domene eller prefiks: set `BYGDELISTA_PUBLIC_ORIGIN` til fast HTTPS-origin,
  `BYGDELISTA_PUBLICATION_URL` som GitHub Actions-variabel til heile
  `/api/protokoll/publiser`-adressa, og appens vanlege URL-prefiks separat.

Skrivetilgang og godkjenningslenkjer bruker URL-fragment, som ikkje blir sendt
med vanlege HTTP-førespurnader. Berre kontrollsummen av den tilfeldige nøkkelen
blir lagra i databasen. E-postfeil og uvisst leveringsutfall blir viste i
Bygdelista; ny lenkje erstattar den gamle. Databasetabellane `minutes_drafts`,
`minutes_reviews`, `minutes_signers` og `minutes_writers` er med i ordinær backup.
Dei faste kopiane kan ikkje redigerast. Det blir ikkje generert PDF av protokollen.
