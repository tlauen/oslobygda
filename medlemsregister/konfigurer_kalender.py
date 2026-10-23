#!/usr/bin/env python3
"""Legg GitHub-tilgangen til kalenderpublisering direkte i serveroppsettet."""
from getpass import getpass
from pathlib import Path
from dotenv import load_dotenv, set_key
from tilskipingar import GithubCalendar, CalendarError


def main():
    env=Path(__file__).resolve().parent/'.env'
    load_dotenv(env)
    print('Bruk ein fine-grained GitHub-token for berre tlauen/oslobygda, med Contents: Read and write.')
    token=getpass('GitHub-token (skjult): ').strip()
    if not token:
        raise SystemExit('Ingen token oppgitt. Ingenting lagra.')
    try:
        _,_,events=GithubCalendar(token).read()
    except CalendarError as error:
        raise SystemExit(str(error)) from None
    env.touch(mode=0o600,exist_ok=True)
    env.chmod(0o600)
    set_key(env,'GITHUB_EVENTS_TOKEN',token)
    env.chmod(0o600)
    print(f'Lesetilgang kontrollert ({len(events)} tilskipingar). Token lagra; skrivetilgang krev Contents: Read and write.')
    print('Last webappen på nytt i Web-fana. Ingen tilskiping er publisert av dette oppsettet.')


if __name__=='__main__':
    main()
