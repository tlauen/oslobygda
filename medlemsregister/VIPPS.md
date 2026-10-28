# Nye medlemmar med Vipps – testversjon

`ny_innmelding.py` har eige skjema på `/bli-medlem`, status på
`/bli-medlem/status` og styreoversikt på `/innmeldingar`. Flyten er stengd som
standard (`VIPPS_SIGNUP_MODE=disabled`). Den gamle offentlege innmeldingssida er
ikkje lagd om; ikkje lenk til den nye før full test og produksjonsaktivering.

Produksjonsnøklar er stadfesta av brukaren. Den komplette betalingsflyten er
lokalt testa med simulerte Vipps-svar; verkeleg testapp/testbetaling står att.

## Test på PythonAnywhere

1. Køyr `konfigurer_vipps.py` med den vanlege venv-Pythonen. Vel `test`, og legg
   inn alle fire verdiane frå testsalseininga. Dei blir lagra i `.env.vipps-test`
   (600); produksjonsnøklane i `.env` blir ikkje endra.
2. Frå medlemsregister-mappa, med venv aktiv:

   ```bash
   python -m flask --app app innmelding-testmodus
   ```

3. Trykk **Web → Reload**. Opne `https://bygdelista.oslobygda.no/bli-medlem`.
   Det skal tydeleg stå TEST. Bruk fiktive kontaktopplysningar og Vipps sin testapp.
4. Registrer test-webhook og trykk **Web → Reload** på nytt:

   ```bash
   python -m flask --app app innmelding-webhook
   ```

5. Test fullført betaling, avbrot, gjenteken statuskontroll, og at lukka nettlesar
   ikkje hindrar behandling via webhook/vedlikehald. Ingen testdata blir lagra som
   verkelege medlemmar eller sende til Brevo. Testar blir viste separat i
   styreoversikta. Nøklane blir aldri sende til nettlesaren.

## Betaling og gjenoppretting

Ordre med kontaktopplysningar, medlemsår, beløp og faste idempotensnøklar blir
lagra før betalingsoppretting. Nettverksfeil blir prøvde igjen på same ordre.
Ein retur-GET har ingen betalingssideeffektar. Statusknappen gjer ein CSRF-verna
POST som hentar status frå Vipps, trekkjer heile reservasjonen med fast nøkkel,
hentar status igjen og bokfører først når fullt trekk i NOK er stadfesta.

Webhooks har HMAC-kontroll av rå body, path/query, host og dato, med fem minutt
klokkeslingringsmonn. Verken webhook-payload eller retur frå nettlesaren blir brukt
som prov på betaling: status blir henta direkte frå Vipps. DB-lås/lease vernar
mot samtidige arbeidarar, og medlem/betaling/ordrestadfesting blir lagra i same
transaksjon. Refusjon etter bokføring blir flagga for manuell avstemming; ingen
betaling eller medlemsdata blir automatisk sletta ved refusjon.

Legg òg inn ein **timeleg Scheduled task** på PythonAnywhere som reserve ved
manglande webhook og for Brevo-køen:

```bash
cd /home/oslobygda/oslobygda/medlemsregister && /home/oslobygda/.virtualenvs/bygdelista/bin/python -m flask --app app innmelding-vedlikehald
```

Køyringa viser berre tal, ikkje personopplysningar/nøklar. Ho prøver høgst 100
uferdige betalingar og 100 Brevo-kontaktar per gong. «review» i styreoversikta
krev manuell kontroll. Hald oversikta under oppsyn, særleg etter driftsavbrot.

## Nye medlemmar og Brevo

Eksisterande e-postadresser og andre pågåande innmeldingar med same adresse blir
stoppa før betalingsoppretting. Det blir aldri gjetta medlem ut frå Vipps-betalaren.
Dersom adressa blir registrert av styret medan betaling pågår, blir ei stadfesta
betaling sett til manuell kontroll utan å endre det eksisterande medlemmet.

Eige valfritt nyhendebrevsamtykke blir lagra med tidspunkt. Berre stadfesta
produksjonsmedlemskap med samtykke blir sende til Brevo. Køen sender berre namn
og e-post, med upsert for trygg gjentaking og utan å nullstille avmeldingsstatus.
Dette krev `BREVO_API_KEY` og `BREVO_INNMELDING_LIST_ID` (evt. `BREVO_LIST_ID`).
SMTP-nøkkelen kan ikkje brukast som Brevo API-nøkkel. Manglande Brevo-oppsett
stoppar ikkje medlemsregistrering; kontakten ventar i køen.

## Før produksjonsaktivering

- Verifiser heile flyten mot testappen, også webhook og reservejobb.
- Kontroller Brevo API-oppsett, liste og nyhendebrevsamtykke.
- Ta databasebackup. Stadfest pris, salsvilkår og faktisk medlemsår i skjemaet.
- Set `VIPPS_SIGNUP_MODE=production` uttrykkeleg, registrer produksjonswebhook,
  Reload, og gjer ein kontrollert produksjonstest før den offentlege lenkja blir endra.
- Lenker og den gamle manuelle API-flyten er oppdaterte i koden. Publiser nettsida først etter produksjonsprøva.
- Sletting av medlemmar fjernar persondata i ordrehistorikken og køar sletting hos Brevo.
  Rekneskapssummar blir bevarte anonymt. Ufullførte ordre utan tilknytt medlemskap
  må følgjast opp i styreoversikta; dei blir ikkje automatisk sletta.
- Refusjon og avstemming blir handterte av styret. Denne versjonen har ikkje
  ein refusjonsknapp eller automatisk fornying av eksisterande medlemskap.

## Eksisterande medlemmar – separat seinare arbeid

Direkte push (`PUSH_MESSAGE`) krev særskild godkjenning og har bruksavgrensingar.
Avklar med Vipps at kontingentinnkreving er tillate før dette blir implementert.
Ingen oppkrav til eksisterande medlemmar blir sende av denne versjonen.

## Offisiell dokumentasjon

- https://developer.vippsmobilepay.com/docs/APIs/epayment-api/api-guide/operations/create/
- https://developer.vippsmobilepay.com/docs/APIs/epayment-api/api-guide/operations/get_info/
- https://developer.vippsmobilepay.com/docs/APIs/epayment-api/api-guide/operations/capture/
- https://developer.vippsmobilepay.com/docs/APIs/webhooks-api/request-authentication/

## Kontrollert produksjonsprøve

Kommandoen under gjer skjemaet tilgjengeleg **berre for innlogga styret**.
Dette brukar verkelege produksjonsnøklar og er ei ekte betaling når du godkjenner
henne i den vanlege Vipps-appen. Ingen betaling blir oppretta av oppsettet:

```bash
python -m flask --app app innmelding-produksjonsprove
python -m flask --app app innmelding-webhook
```

Trykk Web → Reload, logg inn som styret og opne `/bli-medlem`. Bruk kontaktdata
for ei ny medlemsadresse, ikkje ein medlem som alt finst. Fullfør betalinga sjølv,
og kontroller medlemsliste, betalingsreferanse, webhook og nyhendebrevval før
`VIPPS_SIGNUP_MODE` blir sett til `production`. Modusen `production-preview`
er stengd for publikum. Testnøklane blir bevarte separat.

Reservejobben gjer ein lesekontroll av Brevo-lista kvar 30. dag, slik at API-nøkkelen ikkje blir inaktiv ved få innmeldingar. Ingen testkontakt eller e-post blir oppretta av denne kontrollen.

## Betalaropplysningar og stadfesting

Nye betalingsførespurnader ber om `profile.scope: name phoneNumber`.
Betalaren samtykkjer i Vipps. Berre namn og telefon frå det kontrollerte
betalingssvaret blir lagra i ordren; medlemsopplysningane frå skjemaet blir
ikkje overskrivne. Eldre betalingar får ikkje profilopplysningar i etterkant.
Styret ser betalar og telefon under «Nye innmeldingar».

Etter stadfesta betaling blir ein transaksjonsmail send til e-postadressa i
innmeldingsskjemaet via eksisterande SMTP-oppsett. Mailen inneheld år, beløp,
betalingsreferanse, kontakt og lenkje til salsvilkåra. Nyhendebrev er uavhengig.
Testbetalingar sender ikkje mail. Eldre innmeldingar blir merkte `skipped`,
slik at ei utrulling ikkje sender gamle stadfestingar automatisk.

Ordren har `confirmation_status`: `pending`, `sending`, `sent`, `review` eller
`skipped`. Atomisk krav på sendinga hindrar parallelle utsendingar. Ved ein
kjend avvisingsfeil prøver `innmelding-vedlikehald` på nytt. Ved uvisst SMTP-utfall
(`review`), eller prosessavbrot under `sending`, må administrator kontrollere
leveringsloggen i Brevo før eventuell ny sending. SMTP garanterer ikkje nøyaktig
éi levering. Ikkje nullstill denne statusen blindt.

Ved personvernsletting blir òg Vipps-betalarnamn og telefon sletta, og ventande
stadfestingsmail stoppa. Sletting blir avvist medan ei sending pågår.
