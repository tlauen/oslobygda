"""Ekstra kryptert offsite-kopi; suksess krev faktisk nedlasting og gjenoppretting."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from kryptert_backup import encrypt_bundle, verified_archive
from okonomi_backup import verify_bundle, verify_bundle_restore


class ProtonBackupError(ValueError):
    pass


def private_file(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ProtonBackupError('Innstillingar og nøkkelfil må vere vanlege, private filer (chmod 600).')
    return path


def checksum(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while chunk:=f.read(1024*1024): h.update(chunk)
    return h.hexdigest()


def write_state(path,value):
    fd,name=tempfile.mkstemp(dir=path.parent,prefix='.status-')
    temporary=Path(name)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(value,f,ensure_ascii=False,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(temporary,path)
    finally: temporary.unlink(missing_ok=True)


class Rclone:
    def __init__(self,binary,config,password):
        self.binary=str(binary);self.config=str(private_file(config))
        # Keep unrelated app/API secrets out of the child's environment and process arguments.
        self.env={key:os.environ[key] for key in ('HOME','PATH','SSL_CERT_FILE','SSL_CERT_DIR') if key in os.environ}
        self.env['RCLONE_CONFIG_PASS']=password

    def run(self,*args):
        command=[self.binary,'--config',self.config,'--ask-password=false','--retries','3','--low-level-retries','5','--contimeout','20s','--timeout','2m',*map(str,args)]
        try: result=subprocess.run(command,capture_output=True,text=True,env=self.env,timeout=900,check=True)
        except (subprocess.SubprocessError,OSError):
            # CLI diagnostics can include account/session details. Do not print them into task logs.
            raise ProtonBackupError('Proton-overføringa feila. Kontroller kontotilgang og prøv igjen; ingen backup er merkt som vellukka.') from None
        return result.stdout

    def check_account(self,remote,account):
        try: config=json.loads(self.run('config','dump'))
        except (ValueError,TypeError): raise ProtonBackupError('Kunne ikkje kontrollere rclone-kontoen.') from None
        selected=config.get(remote,{})
        actual=selected.get('username') or selected.get('user','')
        if selected.get('type')!='protondrive' or actual.strip().casefold()!=account.strip().casefold():
            raise ProtonBackupError('Rclone-oppsettet peikar ikkje på den avtalte Proton-kontoen; inga opplasting utført.')

    def upload(self,source,destination):
        self.run('copyto',source,destination,'--protondrive-replace-existing-draft=true','--protondrive-enable-caching=false')

    def download(self,source,destination):
        self.run('copyto',source,destination,'--protondrive-enable-caching=false')


def perform(settings,client=None):
    required={'account','remote','rclone_binary','rclone_config','key_file','backup_directory','export_directory'}
    if not isinstance(settings,dict) or set(settings)!=required: raise ProtonBackupError('Ugyldig Proton-backupoppsett.')
    remote=settings['remote']
    if not isinstance(remote,str) or not re.fullmatch(r'[A-Za-z0-9_-]+:[^\r\n]+',remote) or any(part in ('..','.') for part in remote.split(':',1)[1].split('/')):
        raise ProtonBackupError('Vel ein fast rclone-remote og ei eiga backupmappe.')
    password=private_file(settings['key_file']).read_text().rstrip('\r\n')
    if not 16<=len(password)<=1024: raise ProtonBackupError('Backupnøkkelen må vere mellom 16 og 1024 teikn.')
    exports=Path(settings['export_directory'])
    if exports.is_symlink(): raise ProtonBackupError('Eksportmappa kan ikkje vere ei symbolsk lenkje.')
    exports.mkdir(mode=0o700,parents=True,exist_ok=True);exports.chmod(0o700)
    lock=exports/'.lock'
    if lock.is_symlink(): raise ProtonBackupError('Ugyldig låsefil.')
    with lock.open('a') as handle:
        lock.chmod(0o600)
        try: fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ProtonBackupError('Ei anna Proton-backupkøyring pågår.') from None
        return _perform(settings,remote,password,exports,client)


def _perform(settings,remote,password,exports,client):
    sets=sorted(p for p in Path(settings['backup_directory']).glob('okonomi-*') if p.is_dir() and not p.is_symlink())
    if not sets: raise ProtonBackupError('Ingen samla lokal backup er tilgjengeleg. Den nattlege backupen må køyre først.')
    bundle=sets[-1]
    if time.time()-bundle.stat().st_mtime>36*3600: raise ProtonBackupError('Siste lokale backup er eldre enn 36 timar; kontroller den nattlege jobben.')
    verify_bundle(bundle)
    state_path=exports/'status.json'
    state=json.loads(private_file(state_path).read_text()) if state_path.exists() else {}
    destination=remote.rstrip('/')+'/'+bundle.name+'.bygdebackup'
    manifest_hash=checksum(bundle/'manifest.json')
    identity=dict(bundle=bundle.name,manifest_sha256=manifest_hash,remote_file=destination,account=settings['account'])
    # Verify local integrity before skipping a transfer that was previously restored successfully.
    if state.get('identity')==identity and state.get('verified_at'):
        return dict(status='already_verified',bundle=bundle.name,verified_at=state['verified_at'])
    client=client or Rclone(settings['rclone_binary'],settings['rclone_config'],password)
    client.check_account(remote.split(':',1)[0],settings['account'])
    artifact=exports/(bundle.name+'.bygdebackup')
    if artifact.exists():
        with verified_archive(artifact,password) as restored:
            if checksum(restored/'manifest.json')!=manifest_hash: raise ProtonBackupError('Eksisterande eksport har anna innhald; inga overskriving utført.')
    else: encrypt_bundle(bundle,artifact,password)
    artifact_hash=checksum(artifact)
    pending=dict(identity=identity,artifact_sha256=artifact_hash)
    # A successful upload followed by a failed verification resumes at download next time.
    if state.get('identity')!=identity or state.get('uploaded_sha256')!=artifact_hash:
        client.upload(artifact,destination)
        write_state(state_path,dict(pending,uploaded_sha256=artifact_hash))
    with tempfile.TemporaryDirectory(prefix='.proton-prove-',dir=exports) as folder:
        downloaded=Path(folder)/'downloaded.bygdebackup'
        client.download(destination,downloaded)
        if downloaded.is_symlink() or not downloaded.is_file(): raise ProtonBackupError('Proton returnerte ikkje ei vanleg backupfil.')
        downloaded.chmod(0o600)
        if checksum(downloaded)!=artifact_hash: raise ProtonBackupError('Den nedlasta kopien har feil kontrollsum; ingen suksess registrert.')
        with verified_archive(downloaded,password) as restored: verify_bundle_restore(restored)
    verified_at=datetime.now(timezone.utc).isoformat()
    write_state(state_path,dict(pending,uploaded_sha256=artifact_hash,verified_at=verified_at))
    return dict(status='verified',bundle=bundle.name,verified_at=verified_at)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings',required=True,type=Path,help='Privat JSON-oppsett; skal ikkje liggje i Git.')
    args=parser.parse_args()
    try:
        settings=json.loads(private_file(args.settings).read_text())
        result=perform(settings)
    except (ProtonBackupError,ValueError,OSError) as exc:
        print('Proton-backup FEILA:',str(exc));raise SystemExit(1)
    print('Proton-backup og nedlastings-/gjenopprettingsprøve: OK.' if result['status']=='verified' else 'Proton-backup er allereie overført og gjenopprettingsprøvd.')
    print('Backupsett:',result['bundle'])
    print('Sist verifisert:',result['verified_at'])


if __name__=='__main__': main()
