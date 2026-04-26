# Hugs når medlemsåret går over (t.d. 2026 → 2027)

Bruk denne lista når styret skal starte **nytt innbetingsår** og samtidig bevare **oversikt for det avsluttande året** (i Bygdelista / `medlemsregister.db`).

## Før du lukkar året

1. **Backup av databasen** – kopier `medlemsregister.db` (og ev. nøkkel/`.env` om du bruker SQLCipher) til ei trygg mappe. Dette er ditt sikra utgangspunkt om noko skulle gå gale.

2. **Kontroll i styregrensesnittet** – opne Bygdelista, panel **Medlemsoversikt** (øvst):
   - sjekk at **totalt innbetalt** og tal på medlemmar med innbetaling samsvarar med konto/kassabok (cirka).

3. **Sjekk einskilde medlemmar** – der det er reklamasjonar eller særtilfelle (betaling for feil år, osb.), bør det rettast **før** du lukkar året, eller du noterer det for ettersyn.

## Når 2026 er ferdig og 2027 skal starte

1. I Bygdelista, bruk knappen **«Lukk medlemsår …»** (under **Medlemsoversikt**).
2. Les stadfestinga: du må skrive inn **medlemsåret som avsluttes** (t.d. `2026`) for å få lov til å gå vidare.
3. Etter lukking:
   - **Gjeldande medlemsår** blir **2027** (neste heiltal etter det du lukka).
   - Eit **sammendrag** for det avslutta året ligg i **Arkiv** (sum og tal) – eiga rad per avslutta år.
   - **Ingen betalingsrader** vert sletta; eldre innbetalingar ligg framleis i databasen med rett medlemsår.
   - **Betalingsstatus** vert sett til **«ikkje betalt»** for alle som *ikkje* har status **«gratis»** (gratis medlemmar vert ikkje endra).

4. **Oppfølging 2027** – registrer nye innbetalingar som vanleg; kvar ny rad vert knytt til medlemsår **2027** (så lenge ikkje noko anna er satt i innstillingane).

## Valfrie ting

- **`MEDLEMSBETALING_AR` i `.env`**: berre nødvendig som **standard** før fyrste køyring / om databasen ikkje har medlemsår lagra enno. Når knappen «Lukk medlemsår» er brukt, styrer **databasen** gjeldande år. Du *kan* likevel setja `MEDLEMSBETALING_AR=2027` i tråd med verkelege år for nye oppsett.

- **Dokumentasjon for rekneskap** – samanlikn tala i **Arkiv** med kassareinskap/bank for det avslutta året og lagr utskrifts‑ eller skjermbilete om styret ynskjer det utanfor appen.

---

*Fila `medlemsregister/README.md` skildrar òg `MEDLEMSBETALING_AR` og kva lukking av medlemsår gjer i detalj.*
