# Kodegjennomgang oslobygda

> Historisk rapport. Fleire av punkta nedanfor er løyste. Sjå [oppdatert gjeremålsliste](Gjeremalsliste-kodegjennomgang-2026-11-25.md) og [driftsstatus](../medlemsregister/PERSONVERN-DRIFT.md) for gjeldande oppfølging.

Gjennomgang av `oslobygda`-repoet: det som er gjort, og det som er laget sitt valg. Skrevet for den som eier koden.

**Kort versjon:** Vipps-flyten er solid bygd. Betalinger verifiseres direkte mot Vipps, med idempotensnøkler, beløpskontroll og webhook-signatur. Det som gjenstår er stort sett *valg om persondata* og noen *kontroller på serveren*, ikke feil i betalingslogikken. Unntaket er punkt 8, som er bekreftet og bør fikses først.

Små, uomtvistelige endringer ligger i [PR #2](https://github.com/tlauen/oslobygda/pull/2). Alt på denne siden er bevisst *ikke* gjort, fordi det krever en avgjørelse fra deg eller laget.

## Oversikt

| # | Tema | Prioritet | Type |
| --- | --- | --- | --- |
| 1 | Profildeling fra Vipps (navn og telefon) | Middels | Beslutning |
| 2 | Lagringstid og opprydding av persondata | Høy | Beslutning |
| 3 | Innhold i personvernerklæringen | Høy | Beslutning |
| 4 | Produksjonsdatabasen er ikke kryptert | Middels | Beslutning |
| 5 | Google Fonts sender besøkendes IP til Google | Middels | Liten endring |
| 6 | Kontaktopplysninger kan ikke rettes før betaling | Middels | Beslutning |
| 7 | Svar på innmelding avslører om e-post er medlem | Lav | Beslutning |
| 8 | IP-basert rate limit bak proxy | Høy | Bekreftet feil |

## Beslutninger

### 1. Profildeling fra Vipps

Middels

#### Hva koden gjør

Når en betaling opprettes, sendes `profile.scope: "name phoneNumber"` til Vipps (`vipps_client.py:140`). Brukeren får da en egen samtykkeskjerm i Vipps. Navn og telefon fra Vipps lagres i `signup_orders.payer_name/payer_phone`.

#### Hvorfor det betyr noe

- Ifølge [Vipps' dokumentasjon](https://developer.vippsmobilepay.com/docs/APIs/epayment-api/api-guide/features/profile-sharing/) feiler betalingen hvis brukeren ikke samtykker. Noen som bare vil betale, men ikke dele telefonnummeret, faller fra.
- Skjemaet har allerede navn, e-post og telefon. Dette er i stor grad dobbel innsamling, og GDPR krever at man bare samler det man trenger (dataminimering).
- Betaleren kan være en annen enn medlemmet. Personvernerklæringen sier dette åpent, men da må laget kunne begrunne hvorfor opplysningene trengs.

#### Alternativer

- **A. Fjern** `profile`-linjen. Enklere betaling, mindre data. Refusjon går fortsatt via referanse og beløp.
- **B. Behold som i dag.** Skjemaet sier allerede at Vipps vil be om navn og telefon, og hvorfor (`ny_innmelding.html:22`). Det fjerner ikke frafallet hos dem som sier nei i Vipps.

**Anbefaling:** A, med mindre laget har et konkret behov for betalerens navn og telefon. Hvis A velges, kan feltene `payer_name`/`payer_phone` ryddes bort senere, og sletterutinen forenkles.

### 2. Lagringstid og opprydding

Høy

#### Hva koden gjør

Avbrutte og utløpte ordrer (`ABORTED/EXPIRED/TERMINATED`) beholder navn, adresse, e-post og fødselsdato i `signup_orders.details` uten tidsgrense. Dokumentasjonen sier at ufullførte ordrer «må følges opp» manuelt. Medlemmer som aldri fornyer blir også værende.

#### Hvorfor det betyr noe

Opplysninger man ikke lenger har bruk for skal slettes (lagringsbegrensning). Det er også de verste dataene å lekke: personopplysninger om folk som aldri ble medlemmer.

#### Alternativer

- **Ordrer:** slett eller anonymiser avbrutte ordrer etter f.eks. 30–90 dager. Kan legges inn i den eksisterende vedlikeholdsjobben `innmelding-vedlikehald`.
- **Medlemmer:** bestem en frist, f.eks. «slettes etter 2 år uten betalt medlemskap», og om det skal skje automatisk eller etter en påminnelse.

**Anbefaling:** Bestem fristene først (laget). Selve jobben er liten å lage når tallene er avklart.

### 3. Personvernerklæringen

Høy

#### Hva som mangler i `personvern/index.md`

- **Rettslig grunnlag** for behandlingen (f.eks. avtale/medlemskap, samtykke for nyhetsbrev).
- **Lagringstid** (henger sammen med punkt 2).
- **Tjenester som behandler data:** PythonAnywhere (hosting av Bygdelista) mangler. Vipps, Brevo og Umami er nevnt. GitHub hoster nettstedet og publiserte dokumenter (bl.a. navn på styret).
- **Overføring til land utenfor EØS**, hvis noen av tjenestene lagrer data der.
- **Fødselsdato:** hva den brukes til (aldersstatistikk?), og at den er valgfri.
- **Rettigheter** utover «innsyn, retting, sletting», og retten til å klage til Datatilsynet.
- **Google Fonts** (se punkt 5), hvis det beholdes.

**Anbefaling:** Dette er juridisk innhold som laget må stå inne for, så jeg har ikke skrevet det. Datatilsynet har veiledning om informasjonsplikten på [datatilsynet.no](https://www.datatilsynet.no/). Dette er ikke juridisk rådgivning.

### 4. Databasen er ikke kryptert i produksjon

Middels

#### Hva koden gjør

`app.py` støtter SQLCipher, men `wsgi.py:13` nekter oppstart hvis `MEDLEMSREGISTER_DB_KEY` er satt, og PythonAnywhere kjører vanlig SQLite. Medlemsdata og TOTP-hemmelighetene (styrets 2-faktor) ligger i klartekst i samme fil. Filen har rettighet 600, og det er en reell demper. Backup er bare delvis kryptert: lokale backupsett er ukrypterte, mens den manuelle eksporten til Proton Drive er kryptert (`BACKUP.md`). Men docstringen i `app.py` («GDPR-sikkert») gir inntrykk av mer enn det som kjører.

#### Alternativer

- **A. Godta og dokumenter.** Endre docstring og dokumentasjon til å si hva som faktisk gjelder.
- **B. Krypter bare TOTP-hemmelighetene** i databasen (liten kodeendring, en nøkkel i `.env`).
- **C. Full SQLCipher** på PythonAnywhere. Krever å få `libsqlcipher` til å fungere der, og en kontrollert migrering av hele databasen.

**Anbefaling:** A nå, B når det passer. C bare hvis laget faktisk krever kryptering i ro og det er gjennomførbart på hostingen.

### 5. Google Fonts

MiddelsLiten endring

#### Hva koden gjør

`_utforming/standard.html:48` laster fonten Fraunces fra `fonts.googleapis.com`. Hver sidevisning sender da besøkendes IP-adresse til Google, uten at det står i personvernerklæringen. (Umami er nevnt.)

#### Løsning

Last ned fontfilene (Fraunces er under åpen lisens), legg dem i repoet og pek `@font-face` dit. Ingen valg for laget, bare litt arbeid, og jeg har ikke gjort det fordi det krever visuell kontroll av at siden ser lik ut.

**Anbefaling:** Gjør det. Alternativt: nevn Google Fonts i personvernerklæringen, men selvhosting er enklere å forsvare.

### 6. Kontaktopplysninger kan ikke rettes før betaling

Middels

#### Hva koden gjør

Etter at skjemaet er sendt, vises statussiden (`innmelding_status.html`) med «Betal med Vipps». Siden viser medlemsår og beløp, men ikke navn, e-post, telefon eller adresse. Det finnes ingen vei tilbake til skjemaet: sendes det på nytt fra samme nettleser, returneres den gamle ordren (`ny_innmelding.py:176`), så en skrivefeil i kontaktopplysningene kan ikke rettes før betaling.

Salgsvilkårene §4 sier at man skal kunne «kontrollere medlemsopplysningane, medlemsåret og det samla beløpet, og rette eventuelle feil» før man betaler.

#### Alternativer

- **A.** Vis også kontaktopplysningene på statussiden, med en «Rediger»-knapp som er mulig så lenge status er `new` (ingen betaling opprettet).
- **B.** Vis dem uten redigering, og la brukeren starte på nytt.

**Anbefaling:** A. Det oppfyller det vilkårene allerede lover, og kutter supportsaker.

### 7. «E-posten finnes allerede»

Lav

#### Hva koden gjør

Hvis e-posten allerede er medlem eller har en pågående innmelding, svarer skjemaet med en egen melding (`ny_innmelding.py:203`). Det betyr at hvem som helst kan teste om en bestemt person er medlem.

#### Alternativer

- **A. Behold**: god brukeropplevelse, liten risiko for en kulturforening.
- **B. Generisk svar** og send informasjonen på e-post til adressen i stedet.

**Anbefaling:** A er forsvarlig, men vurder det mot hva medlemskap i laget røper om folk.

### 8. Rate limit bak proxy

HøyBekreftet

#### Hva koden gjør

Både innmelding (`ny_innmelding.py:183`, 10 forsøk per time) og innlogging (`styre_auth.py`, 30 per 5 min) bruker `request.remote_addr` som IP-bøtte. Det finnes ingen `ProxyFix` og ingen lesing av `X-Forwarded-For`/`X-Real-IP`.

#### Hvorfor det betyr noe

[PythonAnywhere bekrefter](https://help.pythonanywhere.com/pages/WebAppClientIPAddresses/) at `remote_addr` er lastbalansererens interne IP. Alle besøkende deler derfor *samme* bøtte: innmeldingen stopper for hele nettstedet etter 10 innsendinger i timen, og IP-grensene på innlogging (30 per 5 min) og styreregistrering (10 per time) deles av alle.

#### Løsning

Werkzeug `ProxyFix(app.wsgi_app, x_for=1)` i `wsgi.py`. Den bruker den siste oppføringen i `X-Forwarded-For`, som er den PythonAnywhere sier er pålitelig. Ikke les den første oppføringen eller headeren direkte, for den kan besøkende forfalske. Alternativet er `X-Real-IP`, som lastbalansereren setter.

**Anbefaling:** Fiks dette først. Endringen er liten, men den bør prøves på serveren, fordi den bare virker bak PythonAnywheres proxy.

## Kontroller på serveren

Dokumentasjonen (`VIPPS.md`, `UTRULLING.md`) er fra 28.–29. oktober og sier at testbetaling og produksjonsutrulling står igjen. Hvis løsningen allerede er i drift, er dokumentene utdaterte. Dette kan jeg ikke se fra koden:

- Finnes minst én ordre med `status=complete` og `environment=production` i `/innmeldingar`?
- Er webhooken registrert, og står `VIPPS_WEBHOOK_SECRET` i `.env`?
- Kjører den timevise Scheduled task-jobben `innmelding-vedlikehald` på PythonAnywhere? Uten den blir betalinger hengende hvis webhooken svikter eller brukeren lukker nettleseren.
- Er feilveiene prøvd i produksjon: avbrutt betaling og refusjon (som flagges til manuell kontroll)?
- Er `VIPPS_SIGNUP_MODE` faktisk `production`?
- Er `GITHUB_DOCUMENTS_TOKEN` et fine-grained token begrenset til dette repoet og bare *contents*?
- Oppdater `VIPPS.md` og `UTRULLING.md` så de stemmer med virkeligheten.

## Kodekvalitet (valgfritt, senere)

Ingenting her haster. Rekkefølgen er et forslag.

1. **Statusstrenger som konstanter.** `'new'`, `'CREATED'`, `'complete'`, `'review'`, `'redacted'` er hardkodet i SQL og Python, og Vipps sine (store bokstaver) er blandet med egne (små) i samme kolonne. En skrivefeil gir stille feil, ikke krasj. Gjør det før noen rører betalingslogikken.
2. **Formatter** (Ruff/Black) over alt, i CI. `ny_innmelding.py` og `kontingent.py` har tette semikolon-linjer som `db.commit();return old['reference']`, akkurat der man vil ha lesbar kode.
3. **Versjonerte databasemigrasjoner.** Hver modul har egen `init_*` med `ALTER TABLE` i try/except, kjørt ved hver oppstart. Et enkelt `schema_version` holder.
4. **Del opp `app.py`** (1142 linjer: skjema, medlems-CRUD, Brevo-klient, personvernjobber og ruter). Flytt Brevo-klienten og medlemsrutene til egne filer/blueprints.
5. **Duplisert logikk:** `_nok_to_ore` (`app.py`) og `amount_ore` (`vipps_client.py`) har ulike grenser. «kul/vanleg»-regelen står både i `finalize` (to steder) og i `_oppdater_fra_innbetalingar`.
6. **CSRF-unntak** er en liste med endepunktnavn (`styre_auth.py:89`). Hvis en rute omdøpes, forsvinner unntaket stille. Bruk en `@csrf_exempt`-dekorator.
7. **To måter å åpne databasen på** (`closing(get_db())` og `managed_db`), og flere steder avhenger rollback av at tilkoblingen lukkes.
8. **Testmodus i produksjonskode:** `BYGDELISTA_LOCAL_TEST` i `app.py`. `wsgi.py` blokkerer den, men den hører ikke hjemme der.
9. **Lockfile for avhengigheter.** `requirements*.txt` har bare nedre grenser, så serveren får alltid siste versjon.
10. **Åpne databasetilkoblinger i testene.** Kjøringen gir mange `ResourceWarning: unclosed database` (bl.a. `publisering.py:192`). Ufarlig i tester, men tyder på tilkoblinger som ikke lukkes.

## Hva som er gjort og ikke gjort

**I PR #2:** ingen kjent reservenøkkel for økter, `Referrer-Policy` og HSTS, tester i CI, Dependabot. 221 tester passerer på Linux. CI-jobben kjører først når eieren godkjenner den («Approve and run»), fordi PR-en kommer fra en fork.

**Ikke sjekket:** serveroppsettet (`.env`, PythonAnywhere-innstillinger, Scheduled tasks), live-test mot Vipps, og følgende filer er ikke lest i dybden: `protokoll.py`, `okonomi`/`rekneskap`/`budsjett`, `styre_registrering.py` (utenom rate limit), JavaScript i `fast/` og HTML-malene. Fravær av funn i disse betyr ikke at de er godkjent.

Dette er en teknisk gjennomgang, ikke juridisk rådgivning. Personvern- og vilkårsspørsmål bør avklares av laget.