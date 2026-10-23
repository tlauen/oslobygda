# Nye tilskipingar frå Bygdelista

Innlogga styremedlemmar finn **Tilskipingar** frå medlemslista. Skjemaet tek imot
type, tittel, dato, start/slutt, stad, omtale, valfri lenkje og eit av dei etablerte
arrangementsbileta. «Publiser tilskipinga» legg data direkte til den eksisterande
`_data/kalender.yml` i GitHub. Komande tilskipingar står i ei liste med «Rediger». Endringane bevarer UID,
registrerings-ID og andre eksisterande felt. Gjennomførte tilskipingar kan ikkje
redigerast her. Ved samtidig endring av same tilskiping må skjemaet opnast på nytt.
Biletopplasting og sletting er ikkje del av skjemaet.

Nettsida og `.ics`-straumen blir oppdaterte av GitHub Pages etter lagring. Det kan
ta nokre minutt. Nyhendebrevskriptet les den same datafila på neste køyring; skjemaet
sender ikkje nyhendebrev med ein gong. Eksisterande kommentarar og data vert bevarte.
Ved samtidige endringar vert fila lesen på nytt før nytt forsøk. Ei innsending
har fast ID, slik at eit avbrot og nytt forsøk ikkje lagar duplikat.

## GitHub-tilgang på PythonAnywhere

1. I GitHub: Settings → Developer settings → Personal access tokens → Fine-grained tokens.
2. Opprett ein eigen token for Bygdelista. Vel berre repoet **tlauen/oslobygda**.
3. Set repository-permission **Contents: Read and write**. Tokenen treng ikkje
   tilgang til Actions, andre repo eller kontoadministrasjon. Merk at GitHub avgrensar
   dette på repo-nivå, ikkje til berre kalenderfila; serverkoden skriv berre kalenderfila.
4. Vel ei utløpstid som laget kan følgje opp og lagre nøkkelen sikkert. GitHub kan
   krevje regelmessig fornying. Ein utgått token stoppar publisering, men ikkje nettsida.
5. I Bash-konsollen på PythonAnywhere:

       /home/oslobygda/.virtualenvs/bygdelista/bin/python /home/oslobygda/oslobygda/medlemsregister/konfigurer_kalender.py

6. Lim tokenen inn i det skjulte feltet, og trykk Enter. Ingen publisering vert
   utført av oppsettet. Programmet testar lesetilgang og lagrar `GITHUB_EVENTS_TOKEN`
   i `.env` med filrettar 600. Skrivetilgang vert først brukt ved reell publisering.
7. Trykk **Web → Reload**. Opne **Tilskipingar** og legg inn den neste reelle tilskipinga.

Standard repo er `tlauen/oslobygda`, branch `main`. Dersom dette skal endrast,
set `GITHUB_EVENTS_REPO` og `GITHUB_EVENTS_BRANCH` i serveroppsettet.

Hugs å hente nye GitHub-endringar til lokale prosjekt før du redigerer kalenderfila
på Mac-en. Ved behov kan ei publisering rullast tilbake som ein vanleg Git-commit.

## Flytting til historikken

Den offentlege kalendersida inkluderer alle arrangements-korta og sluttidene i
HTML. `lutar/kalender.js` samanliknar sluttid med faktisk klokkeslett i Europe/Oslo,
sorterer komande hendingar og grupperer passerte hendingar etter år. Det vert sjekka
ved sideopning, kvart 30. sekund og når fana vert aktiv igjen. Midnatt og sommar-/
vintertid vert tekne omsyn til. Gamle kalenderabonnement vert ikkje sletta.

Utan JavaScript viser sida inndelinga frå siste Jekyll-bygg. Den automatiske
omgrupperinga gjeld kalendersida; framsida si korte oversikt blir framleis bygd
ved publisering. Nye tilskipingar må vere publiserte før nettlesaren kan vise dei.
