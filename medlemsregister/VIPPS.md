# Innmelding med Vipps – under utvikling

Status: berre API-klienten (`vipps_client.py`) er implementert og lokalt testa med
simulerte API-svar. Han er ikkje kopla til innmeldingsskjemaet eller publisert.
Ingen verkeleg betaling er oppretta. Dagens innmeldingsløysing er uendra.

## Det laget må ordne

Bestill **Integrert betaling** for Oslobygda i Vipps-bedriftsportalen, med eiga
API-integrering og nettstad `https://bygdelista.oslobygda.no`. Eksisterande
Vippsnummer med valfritt beløp er ikkje åleine nok.

Avklar avtale/pris i bestillinga. Brukaren har valt løysinga omtalt med standardpris
2,99 % + 1 kr per betaling; faktisk avtale er styrande.

Hent testtilgang og salseiningsnøklar frå portalen. Nødvendige verdiar er:

- Client ID → `VIPPS_CLIENT_ID`
- Client secret → `VIPPS_CLIENT_SECRET`
- Subscription key (primary eller secondary) → `VIPPS_SUBSCRIPTION_KEY`
- Merchant Serial Number (MSN) → `VIPPS_MSN`
- `VIPPS_ENVIRONMENT=test` (standard). Produksjon krev uttrykkeleg `production`.

Løyndomar skal leggjast direkte i serverkonfigurasjonen, ikkje i chat eller Git.
Ein testkonto/testapp og testnøklar må brukast under integrasjonstesten.

## Neste implementasjonssteg

- Same innmeldingsskjema for medlemsopplysningar og valfritt beløp i NOK.
  Beløpet må validerast i øre på serveren; Vipps krev minst 1 kr.
- Eiga innmeldings-/betalingsrad med medlemsår, beløp, unik referanse og faste
  idempotensnøklar vert lagra før API-kallet. Eit avbrot må ikkje lage dobbel betaling.
- Returner `redirectUrl` frå Vipps til nettlesaren uendra.
- Retursida skal berre vise status. Ein retur frå Vipps er ikkje prov på betaling.
- Verifiser webhook-signaturen og hent betalingsstatus frå Vipps på serveren.
  Godkjend reservasjon må trekkjast (capture). Kontroller faktisk trekt beløp før bokføring.
- Bokfør éin gong per referanse, atomisk med betalingsstatus og rett medlemsår.
  E-post/telefon til betalaren må ikkje brukast for å gjette kva medlem betalinga gjeld.
- Ikkje overskriv eksisterande medlemsopplysningar eller styretilgang frå offentleg skjema.
  Fornying av eksisterande medlemskap må få sikker kopling/eiga stadfesting.
- Handter avbroten/utgått betaling, forseinka og dupliserte hendingar, nettverksfeil,
  refusjon og avstemming også når nettlesaren aldri kjem tilbake.
- Nyhendebrev har eige valfritt samtykke. Meld inn i Brevo etter stadfesta innmelding;
  nyhendebrevfeil må ikkje miste ei betaling. Forbrukartekst/vilkår og personverntekst
  må spegle den faktiske løysinga før produksjonsstart.

## Før aktivering

Test full flyt mot Vipps sitt testmiljø, også dobbel innsending, avbrot,
refusjon, webhook-signatur og gjenoppretting. Fullfør Vipps si integrasjonssjekkliste.
Ta backup og legg berre om den offentlege innmeldingslenkja når heile flyten er verifisert.

## Offisiell dokumentasjon

- <https://developer.vippsmobilepay.com/docs/APIs/access-token-api/standard-authentication/>
- <https://developer.vippsmobilepay.com/docs/APIs/epayment-api/api-guide/operations/create/>
- <https://developer.vippsmobilepay.com/docs/APIs/epayment-api/api-guide/operations/capture/>
- <https://developer.vippsmobilepay.com/docs/APIs/webhooks-api/request-authentication/>
- <https://developer.vippsmobilepay.com/docs/APIs/epayment-api/checklist/>
