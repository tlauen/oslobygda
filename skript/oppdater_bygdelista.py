#!/usr/bin/env python3
"""Oppdater PythonAnywhere-koden frå main; aldri kopier runtime-data frå Git."""
import argparse
import hashlib
import io
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile
import os
from datetime import datetime, timezone

REPOSITORY = 'https://github.com/tlauen/oslobygda.git'
SHARED = {'_data/arsmotesider.json','_data/motereglar.json','_data/styre.yml','_data/rekneskapskategoriar.json', '_data/balanseforklaringar.json', '_tillegg/kolofon.html', '_data/nav.yml', 'lutar/kolofon.css', 'lutar/topp.css'}
CODE_SUFFIXES = {'.py', '.html', '.css', '.js', '.txt', '.md', '.sh', '.json', '.yml', '.yaml'}


def allowed(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:
        return False
    if name.startswith('lutar/bilete/styret/') and path.suffix.lower() in {'.jpg','.jpeg','.png','.webp'}:
        return True
    if name in SHARED:
        return True
    if not name.startswith('medlemsregister/'):
        return False
    if any(part.startswith('.') or part in {'_site', 'venv', '__pycache__', 'node_modules', 'backups'} for part in path.parts[1:]):
        return False
    return path.suffix.lower() in CODE_SUFFIXES and not any('.db' in part.lower() for part in path.parts)


def git(source, *args):
    return subprocess.check_output(['git', '-C', str(source), *args], stderr=subprocess.PIPE)


def tracked_code(source):
    files = {}
    with tarfile.open(fileobj=io.BytesIO(git(source, 'archive', '--format=tar', 'HEAD'))) as archive:
        for entry in archive:
            if allowed(entry.name):
                if not entry.isfile():
                    raise RuntimeError('Uventa filtype i Git: ' + entry.name)
                data = archive.extractfile(entry).read()
                if entry.name.endswith('.py'):
                    compile(data, entry.name, 'exec')
                files[entry.name] = (data, entry.mode)
    required = {'medlemsregister/app.py', 'medlemsregister/wsgi.py', 'medlemsregister/requirements-pythonanywhere.txt'} | SHARED
    if not required.issubset(files):
        raise RuntimeError('Kjeldekopien manglar nødvendige kodefiler.')
    return files


def install(source, target, backups, dry_run=False):
    source, target, backups = map(lambda p: Path(p).resolve(), (source, target, backups))
    if source == target or target in source.parents or source in target.parents:
        raise RuntimeError('Kjelde og aktiv app må liggje i separate mapper.')
    files = tracked_code(source)
    changed = {}
    for name, content in files.items():
        destination = target / name
        if destination.resolve() != destination.absolute():
            raise RuntimeError('Stogga ved symbolsk lenkje: ' + name)
        if not destination.exists() or destination.read_bytes() != content[0]:
            changed[name] = content
    revision = git(source, 'rev-parse', '--short', 'HEAD').decode().strip()
    print(f'Git-versjon {revision}: {len(changed)} kodefiler må oppdaterast.')
    if dry_run or not changed:
        return
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = backups / f'kode-for-oppdatering-{stamp}.tar.gz'
    with tarfile.open(backup, 'w:gz') as archive:
        for name in changed:
            destination = target / name
            if destination.exists():
                archive.add(destination, arcname=name, recursive=False)
    backup.chmod(0o600)
    print('Kodebackup:', backup)
    for name, (data, mode) in changed.items():
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as tmp:
            temporary = Path(tmp.name)
            tmp.write(data)
        try:
            temporary.chmod(mode & 0o777)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    for name, (data, _) in changed.items():
        if hashlib.sha256((target / name).read_bytes()).digest() != hashlib.sha256(data).digest():
            raise RuntimeError('Filkontroll feila: ' + name)
    print('Kodefilene er oppdaterte og kontrollerte. Innstillingar og database er ikkje kopierte eller endra.')
    print('Ved endringar i Python-pakkene: installer requirements-pythonanywhere.txt i bygdelista-miljøet før omlasting.')
    print('Til slutt: PythonAnywhere → Web → Reload bygdelista.oslobygda.no')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Vis om kode må oppdaterast, utan å endre nettappen.')
    args = parser.parse_args()
    home = Path.home()
    source = home / 'oslobygda-kjelde'
    if not source.exists():
        subprocess.run(['git', 'clone', '--branch', 'main', '--single-branch', REPOSITORY, str(source)], check=True)
    if git(source, 'remote', 'get-url', 'origin').decode().strip() != REPOSITORY:
        raise RuntimeError('Git-kopien peikar på feil kjelde.')
    if git(source, 'branch', '--show-current').decode().strip() != 'main':
        raise RuntimeError('Git-kopien må stå på main.')
    if git(source, 'status', '--porcelain'):
        raise RuntimeError('Kjeldekopien har lokale endringar. Avklar dei før oppdatering.')
    subprocess.run(['git', '-C', str(source), 'pull', '--ff-only', 'origin', 'main'], check=True)
    install(source, home / 'oslobygda', home / 'Bygdelista-backup', args.dry_run)


if __name__ == '__main__':
    main()
