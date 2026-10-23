# Styrekontoar med autentiseringsapp

Kvar person brukar eige passord og ein sekssifra tidsbasert kode (TOTP).
Styremedlemmar kan registrere seg med e-postadressa i medlemsregisteret.

## Registrering på nett

1. Ein administrator set medlemstype **Styret** på medlemskortet. E-postadressa
   må vere personleg og berre finnast på éin medlem.
2. Personen vel **Opprett styrekonto** på innloggingssida og skriv adressa.
3. Ein åttesifra stadfestingskode vert send til den registrerte adressa.
   Koden gjeld i 15 minutt og må skrivast i den same nettlesaren.
4. Personen vel eit passord på minst 14 teikn og skannar QR-koden i
   autentiseringsappen. Manuell oppsettsnøkkel finst som reserve. Kontoen vert først oppretta når ein kode frå appen er stadfesta.
5. Innlogging skjer med e-postadresse, passord og ein fersk autentiseringskode.

Ukjende adresser og eksisterande kontoar får same svar, slik at sida ikkje røper
kven som er medlem. E-post- og kodeforsøk er avgrensa. Ein eksisterande eller
sperra konto kan ikkje erstattast gjennom registrering.

Fjerning av medlemstype **Styret**, sletting av medlemmen eller endring av
registrert e-post stengjer tilgangen for den tilknytte kontoen, også i eksisterande
økter. Ved endra e-post må administrator hjelpe med kontoen; sjølvregistrering
flyttar ikkje ein eksisterande konto til ei anna adresse.

### Domeneshop / SMTP

Køyr `python konfigurer_epost.py` i det aktive Python-miljøet på serveren.
Skriptet spør etter server og port frå Domeneshop sitt kontrollpanel, brukarnamn,
avsendaradresse og passord. Det testar SMTP-innlogging før lagring i `.env`
(med filrettar 600), utan å sende e-post. Last webappen på nytt etterpå.

Bruk e-postkontoen sitt brukarnamn og passord, ikkje Domeneshop-kundepassordet.
Nye og eldre Domeneshop-oppsett kan ha ulike servernamn; bruk serverinnstillingane
frå e-posttenesta dykkar. Port 587 med STARTTLS eller 465 med SSL er støtta.

Innstillingar: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`,
`STYRE_EPOST_FRA`. Utan desse er registreringssida stengd med ei forklaring.
E-postlevering må testast ved ei ekte kontoregistrering etter konfigurering.

## Administrator frå konsollen

Konsollkontoar er eit administrativt unntak og er ikkje knytte til medlemstype.
Dette gjeld den eksisterande `torbjorn`-kontoen, slik at første administrator
framleis kan styre tilgang. Slike kontoar må sperrast med konsollkommandoen
under når dei ikkje lenger skal ha tilgang. Ikkje opprett vanlege styrekontoar
frå konsollen når sjølvregistrering er teken i bruk.

## Opprett konto

Aktiver Python-miljøet og stå i `medlemsregister/`:

```bash
python -m flask --app app styrekonto torbjorn
```

Vel eit personleg passord på minst 14 teikn. Konsollen viser ei hemmeleg
oppsettsnøkkel. Legg henne inn manuelt i autentiseringsappen som ei tidsbasert
konto med seks siffer, SHA-1 og 30 sekund (standard TOTP-innstillingar).
Ikkje bruk ei ekstern QR-teneste eller del nøkkelen i chat/e-post.
Stadfest med ein kode frå appen; kontoen vert først lagra når koden er godkjend.
Vent til neste kode før første innlogging.

Gjenta for kvar person. Brukarnamn skil ikkje mellom store og små bokstavar.
Passord og autentiseringsnøkkel bør oppbevarast separat.

## Mista telefon eller gløymt passord

Ein serveradministrator stadfestar identiteten til personen og køyrer:

```bash
python -m flask --app app styrekonto torbjorn --nullstill
```

Dette krev nytt passord og ny autentiseringsnøkkel med stadfestingskode,
og avsluttar alle gamle innloggingar. Det finst ikkje ei offentleg omgåing
eller sjølvbetent gjenoppretting. Sørg for at laget beheld tilgang til
PythonAnywhere-kontoen, også når styret skiftar.

## Fjern styretilgang

```bash
python -m flask --app app styrekonto torbjorn --sperr
```

Sperringa gjeld òg eksisterande innloggingar. Nullstilling kan opne kontoen att.

## Drift

- Bruk HTTPS. WSGI-oppsettet set sikre økt-informasjonskapslar.
- Innlogging varer høgst åtte timar frå innlogging; utlogging avsluttar økta i nettlesaren.
- Ein godkjend kode kan ikkje brukast på nytt. Eitt tidssteg slingringsmonn vert godteke.
- Fem mislukka forsøk per brukarnamn gir sperre til femminuttsvindauget sluttar.
  IP-adresser har i tillegg eit tak på 30 forsøk per fem minutt.
- Passordhashar og TOTP-nøklar ligg i medlemsdatabasen. Vern også tryggingskopiane.
- Det gamle fellespassordet er fjerna. Eksisterande økter frå den løysinga gir ikkje tilgang.

Implementasjonen brukar [PyOTP](https://pyauth.github.io/pyotp/).

## Brevo og fast testmelding

Domeneshop avviste SMTP frå PythonAnywhere si AWS-adresse i testen 23. oktober 2026.
Bruk Brevo SMTP for utsending frå appen:

- `SMTP_HOST=smtp-relay.brevo.com`
- `SMTP_PORT=465`
- `SMTP_USER`: Login frå Brevo si SMTP-fane
- `SMTP_PASSWORD`: eigen SMTP key for Bygdelista, ikkje API key eller kontopassord
- `STYRE_EPOST_FRA=ikkjesvar@oslobygda.no`

Konfigurer med `konfigurer_epost.py`. Avsendardomenet må vere autentisert i Brevo,
og transaksjonsutsending må vere aktivert. Vel «No expiration» om nøkkelen ikkje skal
ha fast utløpsdato. Vellukka sending gjennom denne nøkkelen må likevel skje innan 90 dagar.

Legg denne kommandoen i ei eiga **Daily** oppgåve på PythonAnywhere:

    /home/oslobygda/.virtualenvs/bygdelista/bin/python /home/oslobygda/oslobygda/medlemsregister/smtp_keepalive.py

Skriptet sjekkar dagleg, men sender berre kvar 30. dag. Første køyring sender med ein
gong når Brevo er konfigurert. Det brukar same SMTP-nøkkel som kontoregistreringa og
sender berre til `folk@oslobygda.no`, frå `ikkjesvar@oslobygda.no`.
Fast emne er:

    [BYGDELISTA-SMTP-KEEPALIVE] Automatisk e-posttest

Ein innboksregel kan slette meldingar med nøyaktig dette emnet og denne avsendaren.
Meldinga inneheld ingen medlemsdata. Sendetid vert lagra i
`/home/oslobygda/.bygdelista/smtp-keepalive.json` berre når SMTP-serveren godtek sendinga.
Ved feil vert sendinga prøvd igjen neste dag. Sjå oppgåveloggen ved feil; skriptet
sender ikkje eigne feilvarsel og SMTP-godkjenning garanterer ikkje innbokslevering.
