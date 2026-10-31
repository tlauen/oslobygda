"""Interaktiv førstegongsinnlogging; passord og OTP skal aldri sendast i chat."""
import getpass
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import tempfile

from proton_backup import Rclone, ProtonBackupError, private_file, write_state

ACCOUNT='oslobygda@proton.me'
REMOTE='proton-oslobygda'


def main():
    root=Path.home()/'bygdelista-data/proton-backup'
    binary=Path.home()/'bin/rclone'
    root.mkdir(mode=0o700,parents=True,exist_ok=True);root.chmod(0o700)
    key=root/'backup-key.txt'
    if not key.exists():
        fd=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(48)+'\n')
    password=private_file(key).read_text().strip()
    print('Proton-konto:',ACCOUNT)
    print('Passordet blir skrive skjult og blir ikkje vist i logg eller prosessargument.')
    login_password=getpass.getpass('Proton-passord: ')
    otp=getpass.getpass('Eingongskode frå autentiseringsappen (Enter dersom ikkje brukt): ').strip()
    if not login_password: raise ProtonBackupError('Tomt passord; oppsett avbrote.')
    if otp and (not otp.isdigit() or len(otp)!=6): raise ProtonBackupError('Eingongskoden må ha seks siffer.')
    obscured=subprocess.run([str(binary),'obscure','-'],input=login_password,text=True,capture_output=True,check=True).stdout.strip()
    del login_password
    config=root/'rclone.conf'
    fd,name=tempfile.mkstemp(prefix='.rclone-',dir=root);temporary=Path(name)
    try:
        with os.fdopen(fd,'w') as f:f.write(f'[{REMOTE}]\ntype = protondrive\nusername = {ACCOUNT}\npassword = {obscured}\nenable_caching = false\n')
        client=Rclone(binary,temporary,password)
        client.run('--password-command','/usr/bin/cat '+shlex.quote(str(key)),'config','encryption','set')
        if b'RCLONE_ENCRYPT_V0:' not in temporary.read_bytes(): raise ProtonBackupError('Rclone-konfigurasjonen blei ikkje kryptert; oppsett stoppa.')
        if otp:client.env['RCLONE_PROTONDRIVE_2FA']=otp
        client.run('lsd',REMOTE+':')
        client.env.pop('RCLONE_PROTONDRIVE_2FA',None)
        client.check_account(REMOTE,ACCOUNT)
        client.run('mkdir',REMOTE+':Tryggleikskopiar')
        os.replace(temporary,config);config.chmod(0o600)
    finally: temporary.unlink(missing_ok=True)
    settings=dict(account=ACCOUNT,remote=REMOTE+':Tryggleikskopiar',rclone_binary=str(binary),rclone_config=str(config),key_file=str(key),backup_directory=str(Path.home()/'Bygdelista-backup'),export_directory=str(root/'exports'))
    write_state(root/'settings.json',settings)
    print('Kontotilgangen er kontrollert og lagra i kryptert, privat konfigurasjon.')
    print('Ta vare på backupnøkkelen separat frå serveren:',key)
    print('Neste steg er prøveoverføring og kontrollert automatisk jobb; ingenting er lasta opp av dette oppsettet.')


if __name__=='__main__':
    try: main()
    except (ProtonBackupError,subprocess.SubprocessError,OSError):
        print('Oppsettet feila. Ingen automatisk jobb er aktivert. Kontroller innlogginga og prøv igjen.')
        raise SystemExit(1)
