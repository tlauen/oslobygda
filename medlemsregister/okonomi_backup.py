"""Samla lokal backup av SQLite og bilag. Arkivet er ikkje kryptert."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import uuid
from datetime import datetime,timezone

from backup import connect_readonly,check_database
from bilag import receipt_lock, file_path, verified_receipt


def verify_bundle(directory):
    directory=Path(directory)
    if (directory/'database.db').is_symlink() or (directory/'manifest.json').is_symlink():
        raise ValueError('Backupen kan ikkje ha symbolske lenkjer til database eller manifest.')
    manifest=json.loads((directory/'manifest.json').read_text())
    if manifest.get('schema_version')!=1 or not isinstance(manifest.get('files'),dict):
        raise ValueError('Ugyldig backupmanifest.')
    expected={'database.db'}
    if 'styre-og-kalender.zip' in manifest['files']: expected.add('styre-og-kalender.zip')
    with closing(connect_readonly(directory/'database.db')) as db:
        check_database(db)
        db.row_factory=sqlite3.Row
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        receipts=db.execute('SELECT * FROM ledger_receipts').fetchall() if 'ledger_receipts' in tables else []
        for row in receipts:
            key=row['file_key'];file_path(directory/'bilag',key)
            expected.add('bilag/'+key)
            verified_receipt(directory/'bilag',row)
        if 'ledger_journals' in tables and db.execute('''SELECT j.id FROM ledger_journals j
            LEFT JOIN ledger_lines l ON l.journal_id=j.id WHERE j.state='posted'
            GROUP BY j.id HAVING COUNT(l.id)<2 OR SUM(l.amount_ore)!=0''').fetchone():
            raise ValueError('Backupen inneheld ei ubalansert bokføring.')
    if set(manifest['files'])!=expected: raise ValueError('Manifestet svarar ikkje til databasen sine bilag.')
    for name,metadata in manifest['files'].items():
        path=directory/name
        if path.is_symlink(): raise ValueError('Symbolsk lenkje i backup.')
        data=path.read_bytes()
        if len(data)!=metadata['size'] or hashlib.sha256(data).hexdigest()!=metadata['sha256']:
            raise ValueError('Backupfil har feil kontrollsum.')
    return manifest


def verify_bundle_restore(directory):
    """Prøv gjenoppretting i ny, isolert mappe. Endrar aldri aktiv database."""
    verify_bundle(directory)
    with tempfile.TemporaryDirectory(prefix='bygdelista-bilag-restore-') as temp:
        restored=Path(temp)/'restore'
        shutil.copytree(directory,restored,symlinks=True)
        verify_bundle(restored)


def create_bundle(source,receipts_root,directory,keep=30,include_board=False):
    source=Path(source);directory=Path(directory)
    if not source.is_file(): raise FileNotFoundError('Databasen finst ikkje.')
    if keep<1: raise ValueError('Minst ein backup må bevarast.')
    directory.mkdir(mode=0o700,parents=True,exist_ok=True);directory.chmod(0o700)
    temp=Path(tempfile.mkdtemp(prefix='.okonomi-',dir=directory))
    try:
        with receipt_lock(receipts_root,exclusive=True) as root:
            with closing(connect_readonly(source)) as live, closing(sqlite3.connect(temp/'database.db')) as copy:
                live.backup(copy);copy.execute('PRAGMA journal_mode=DELETE');check_database(copy)
            (temp/'database.db').chmod(0o600)
            (temp/'bilag').mkdir(mode=0o700)
            with closing(connect_readonly(temp/'database.db')) as copy:
                copy.row_factory=sqlite3.Row
                tables={r[0] for r in copy.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                rows=copy.execute('SELECT * FROM ledger_receipts').fetchall() if 'ledger_receipts' in tables else []
                for row in rows:
                    data=verified_receipt(root,row)
                    dest=file_path(temp/'bilag',row['file_key'])
                    dest.write_bytes(data);dest.chmod(0o600)
        extra_files=[]
        if include_board:
            import zipfile,fcntl
            from styremodul import source_bytes,board_file,ROOT
            from contextlib import nullcontext
            board=board_file()
            extra=temp/'styre-og-kalender.zip'
            with ((board.parent/'.styre.lock').open('a') if board.parent.exists() else nullcontext()) as lock:
                if lock is not None: fcntl.flock(lock,fcntl.LOCK_SH)
                with zipfile.ZipFile(extra,'w',zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr('styre.yml',source_bytes())
                    names=set()
                    for folder in (board.parent/'styreportrett',ROOT/'lutar'/'bilete'/'styret'):
                        if folder.exists():
                            for photo in folder.iterdir():
                                if photo.is_file() and not photo.is_symlink() and photo.name not in names and photo.suffix.lower() in ('.jpg','.jpeg','.png','.webp'):
                                    names.add(photo.name);archive.write(photo,'styreportrett/'+photo.name)
            extra.chmod(0o600);extra_files.append(extra)
        manifest={'schema_version':1,'created_at':datetime.now(timezone.utc).isoformat(),'files':{}}
        for path in [temp/'database.db',*sorted((temp/'bilag').iterdir()),*extra_files]:
            data=path.read_bytes()
            manifest['files'][path.relative_to(temp).as_posix()]={'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        (temp/'manifest.json').write_text(json.dumps(manifest,sort_keys=True));(temp/'manifest.json').chmod(0o600)
        verify_bundle_restore(temp)
        name='okonomi-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid.uuid4().hex
        result=directory/name;os.replace(temp,result)
        complete=[]
        for path in sorted(directory.glob('okonomi-*'),reverse=True):
            # Roter berre komplette sett etter at ny backup er kontrollert.
            if path.is_dir() and not path.is_symlink():
                try: verify_bundle(path)
                except (OSError,ValueError,sqlite3.DatabaseError): continue
                complete.append(path)
        for old in complete[keep:]: shutil.rmtree(old)
        return result
    finally:
        if temp.exists(): shutil.rmtree(temp)
