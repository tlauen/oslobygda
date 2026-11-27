# Oslobygda – rettleiing for kodeagentar

Gjeld heile repoet. Les `README.md` og relevant driftsrettleiing før endringar.

## Prosjektet

- Nettsida er Jekyll; Bygdelista er Flask/SQLite i `medlemsregister/`.
  Dei blir køyrde og publiserte kvar for seg.
- Jekyll-malar ligg i `_utforming/`, komponentar i `_tillegg/` og stilar i
  `lutar/`. Ikkje rediger genererte filer i `_site/`.
- Bruk nynorsk. Skriv offentlege tekstar enkelt og kort.
- Følg eksisterande løysingar og hald endringane avgrensa til oppgåva.
  Behald andre lokale endringar, også filer som ikkje er spora av Git.

## Kode som menneske kan føre ettersyn med

- All kode skal vere forståeleg for menneske som skal kontrollere og vedlikehalde
  henne. Prioriter lesbarheit og ei tydeleg arbeidsrekkjefølgje.
- Bruk namn som forklarer føremålet med variablar, funksjonar og modular.
  Skriv éi logisk handling om gongen, med vanlege linjeskift og innrykk.
  Dette gjeld òg HTML, CSS, JavaScript, SQL og testar; ikkje pakk kjeldekode saman.
- Del lange funksjonar og malar etter tydelege ansvar. Hald dataflyt,
  tilstandsendringar og sideverknader synlege; unngå unødvendige abstraksjonar.
- Forklar kvifor ved kommentarar der reglar, avvegingar eller avgrensingar ikkje
  er sjølvsagde. Dokumenter særleg betalingsreglar, låsing, tilgang og sletting,
  slik at ein lesar kan vurdere konsekvensane av ei endring.
- Hald forklaringar og dokumentasjon i samsvar med koden. Ved endringar skal
  gjennomgangen gjere det lett å sjå kva som er endra, kvifor og korleis det er kontrollert.

## Felles kjelder og data

- Bruk `_data/nav.yml` og eksisterande fellesmalar og stilark for felles meny,
  topp og kolofon. Ikkje lag eigne kopiar i Flask-mappene.
- `_data/kalender.yml` er felles kalenderkjelde. Behald `uid`, stabile `slug`
  og historiske tilskipingar; marker avlysing med `avlyst: true`.
  Etter nye tilskipingar: `ruby skript/bygg_tilskipingssider.rb`.
- Kontingentsatsar skal kome frå same godkjende kjelde som betalinga gjennom
  `/api/kontingent`. Ikkje vedlikehald parallelle satsar i nettsidetekst.
- Hald løyndomar, medlemsdata, databasar og originale bilag utanfor Git og
  offentlege eksportar. Bruk testdata ved lokal prøving.
- Før opprydding: kartlegg kjelder og avklar kva som inngår. Respekter uttrykkelege
  unntak; la lokale tryggleikskopiar utanfor oppgåva liggje urørte.
  Følg `medlemsregister/BACKUP.md` og `medlemsregister/PROTON-BACKUP.md`.

## Lokal kontroll

- Førehandsvis nettsida: `bundle exec ruby skript/forehandsvis.rb`.
- Køyr relevante kontrollar frå rotmappa:
  `node skript/test_kalender.js`, `node skript/test_kontingent.js`,
  `ruby skript/test_nyhendebrev.rb` og
  `python3 -m unittest discover -s skript -p 'test_*.py'`.
- For Bygdelista: følg `medlemsregister/README.md` for virtuelt miljø og
  avhengnader; køyr `python -m unittest discover -s tests` frå `medlemsregister/`.
- Vel kontrollar etter endringa. Opplys kva som er kontrollert og kva som står att.

## Publisering

- Skil mellom lokale endringar, GitHub-push, installasjon på PythonAnywhere og
  offentleg verifisert resultat. Ikkje kall ein push ei stadfesta serveroppdatering.
- Nettsida bruker GitHub Pages frå `main`. Bygdelista krev eiga serveroppdatering
  og Web → Reload; fellesfiler må òg følgje med.
- Følg `medlemsregister/UTRULLING.md` og `medlemsregister/PYTHONANYWHERE.md`.
  Kontroller den aktuelle sida eller funksjonen offentleg før du melder henne publisert.
