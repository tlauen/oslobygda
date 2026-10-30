# Årsmøte og økonomi – steg 3 og 4

Innlogga styremedlemmar finn **Årsmøte og økonomi** på medlemslista (`/arsmote`).
Alle styrekontoar har same tilgang. Årsmelding har innleiing, organisasjonsomtale,
avslutning, kalenderaktivitetar og manuelle aktivitetar. Rekneskap, bilag og budsjett
kjem i seinare steg.

1. Vel rapportår og møteår og opprett årsmeldinga.
2. Hent kalender for rapportåret, fyll inn tekst og vel aktivitetar. Lagre arbeidsutkastet.
3. Lagre ein fast versjon av sist lagra utkast som «Til årsmøtet».
4. Etter faktisk vedtak: lagre «Godkjend av årsmøtet», med vedtaksdato.
5. Opne ein fast versjon for førehandsvising. Etter kontroll av teksten kan han
   leggjast i intern publiseringskø. Ingen data blir sende til GitHub av steg 3.

Arbeidsutkast og faste versjonar er separate. Nye endringar endrar ikkje gamle
sakspapir eller godkjende versjonar. Retting krev nytt utkast og ny versjon.
Kvar tekstrevisjon blir lagra med ansvarleg styrebrukar og tidspunkt.
Ved samtidig redigering blir utdatert lagring avvist. Innsend tekst blir vist att;
kopier teksten før du opnar siste revisjon og flettar inn endringane.
Lagre endringar i utkastet før du bruker knappen for fast versjon.

## Drift

`init_db()` opprettar nye `annual_*`-tabellar og triggerar som vernar faste versjonar
og endringshistorikk. Gjenteken initialisering er testa. Eksisterande medlemstabellar
blir ikkje omskrivne av den nye modulen. Ta databasebackup før første serveroppdatering.
Eksisterande databasebackup tek med dei nye tabellane.

Modul og malar blir tekne med av eksisterande oppdateringsskript. Ingen nye pakkar er nødvendige. Kalenderimport bruker eksisterande GitHub-tilgang
(`GITHUB_EVENTS_TOKEN`); ingen skriving til kalenderen blir utført. Ingen produksjonsutrulling er utført.

Eksporten har eit eige avgrensa skjema utan interne brukarnamn eller betalingsfelt.
Frie tekstfelt krev menneskeleg kontroll før dei blir lagde i kø. Køpayload og hash er
faste; leveringsstatus kan oppdaterast av ein framtidig arbeidar. Nettverkspublisering,
løpande økonomisnapshot og køarbeidar kjem i seinare steg.

## Test

Frå `medlemsregister/`, med testavhengnadene installerte:

```bash
python -m unittest discover -s tests
```

`tests/test_arsdokument.py` bruker mellombelse databasar og testar versjonslåsing,
gjenteken initialisering, samtidige endringar, vedtaksdato, avgrensa eksport,
gjenteken kølegging, innlogging, CSRF og HTML-escaping.


## Kalenderimport og strukturert årsmelding (steg 4)

Lagre tekstendringar før du hentar kjelder eller legg til manuell aktivitet.
Skjemaet varslar ved ulagrede endringar når JavaScript er aktivt.
Import les eksisterande kalender frå GitHub og lagrar filrevisjon og arrangement
for rapportåret. Nye aktivitetar er ikkje valde automatisk, og gjennomføring må
stadfestast. Avlyst blir føreslått ved eige avlysingsfelt eller «AVLYST» i tittelen.
Gjennomførte arrangement og avlyste arrangement får ulik merking i årsmeldinga.

Ny import bevarer kommentar, deltakartal, gjennomføringsstatus og utval. Endra
kjeldefelt og oppføringar som manglar i året blir merkte for gjennomgang. Valde
oppføringar med uavklart status eller uavklart kjeldeendring sperrar fast versjon.
Ei kjeldeendring må stadfestast i skjemaet eller aktiviteten veljast bort.
Manuelle aktivitetar blir ikkje påverka av kalenderimport. Dei kan redigerast eller
veljast bort. Kalenderen blir aldri endra frå årsmeldingsmodulen.

«Hent betalingstal» bruker først eksisterande årsarkiv, elles talet på medlems-ID-ar
for medlemmar med positiv samla registrert betaling for medlemsåret. Dette er ikkje
medlemstal ved årsskiftet og omfattar ikkje gratis medlemskap. Talet blir teke med
berre etter uttrykkeleg henting og kan fjernast igjen. Arkivtal kan ha andre historiske
registreringsreglar; dei er ikkje ei ny historisk medlemsrekonstruksjon.

Faste versjonar inneheld både samla offentleg tekst og ein intern kopi av strukturen.
Køeksporten inneheld berre samla offentleg tekst, ikkje interne kjeldereferansar eller
aktivitetsnøklar. Gamle tekstutkast blir viste som innleiing ved første strukturerte
redigering. Gamle faste versjonar og køpayloadar blir ståande uendra.

Jekyll-malar er klargjorde under `/om/arsmeldingar/` og for rapportåret 2026.
Publiseringsformatet er `_data/arsdokument/<år>.json` med ei `versions`-liste av dei
validerte offentlege versjonane. Utan eksport viser sidene at ingenting er publisert.
Sidene blir ikkje fylte frå databasen eller intern kø. Faktisk kølevering til GitHub
blir implementert i publiseringssteget. Nye år treng ein sidestubb tilsvarande 2026.
Årslista viser år i fallande rekkjefølgje; årsvisinga viser nyaste versjon først og
bevarer eldre versjonar som eigne ankerlenkjer. All fri tekst blir HTML-escapa.


## Oppdatering etter steg 6

Publiseringsarbeidaren er no implementert; sjå PUBLISERING.md for oppsett.
Han sender òg årsmeldingsversjonar som alt er lagde i den interne køa, når ein
administrator uttrykkeleg konfigurerer og køyrer arbeidaren. Tidlegare omtale av
manglande kølevering gjeld steg 3–4. Ingen verkeleg publisering er aktivert av utviklinga.


## Budsjett etter steg 7

Inngangen «Budsjett og oppfølging» er tilgjengeleg frå årsmøteoversikta.
Sjå BUDSJETT.md for arbeidsutkast, faste forslag/vedtak og oppfølging mot faktiske
rekneskapspostar. Reelle rekneskapsdata kan fyllast inn når den samla løysinga er klar.


## Utskrift etter steg 9

Faste versjonar har no eiga utskriftsvising for lagring som PDF i nettlesaren.
Sjå [UTSKRIFT.md](UTSKRIFT.md). Faktisk PDF-paginering skal kontrollerast visuelt
i sluttgjennomgangen før produksjonsbruk.
