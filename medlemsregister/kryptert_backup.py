"""Passfraseverna, autentisert backup. Ingen nøkkel eller passfrase blir lagra."""
from contextlib import contextmanager
import io
import os
from pathlib import Path
import re
import tarfile
import tempfile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from okonomi_backup import verify_bundle

MAGIC=b'BYGDELISTA-BACKUP-1\n'
HEADER_SIZE=len(MAGIC)+16+12
MAX_BYTES=8*1024**3
CHUNK=1024*1024


def key_for(password,salt):
    if not isinstance(password,str) or not 16<=len(password)<=1024:
        raise ValueError('Bruk ei eiga passfrase med minst 16 og høgst 1024 teikn.')
    return Scrypt(salt=salt,length=32,n=2**15,r=8,p=1).derive(password.encode('utf-8'))


class EncryptedWriter(io.RawIOBase):
    def __init__(self,out,encryptor): self.out=out;self.encryptor=encryptor;self.count=0
    def writable(self): return True
    def write(self,data):
        self.count+=len(data)
        if self.count>MAX_BYTES: raise ValueError('Backupsettet er større enn 8 GiB.')
        self.out.write(self.encryptor.update(data))
        return len(data)


@contextmanager
def verified_archive(path,password):
    """Ingen data blir tolka eller ekstraherte før heile GCM-taggen er kontrollert."""
    path=Path(path)
    if path.is_symlink() or not path.is_file(): raise ValueError('Vel ei vanleg kryptert backupfil.')
    size=path.stat().st_size
    if not HEADER_SIZE+16<size<=MAX_BYTES+HEADER_SIZE+16: raise ValueError('Ugyldig storleik på backupfila.')
    with tempfile.TemporaryDirectory(prefix='bygdelista-kryptert-') as folder:
        archive_path=Path(folder)/'backup.tar'
        try:
            with path.open('rb') as source,archive_path.open('xb') as out:
                archive_path.chmod(0o600)
                header=source.read(HEADER_SIZE)
                if not header.startswith(MAGIC): raise ValueError('Ukjent backupformat.')
                salt=header[len(MAGIC):len(MAGIC)+16];nonce=header[-12:]
                source.seek(-16,os.SEEK_END);tag=source.read(16);source.seek(HEADER_SIZE)
                decryptor=Cipher(algorithms.AES(key_for(password,salt)),modes.GCM(nonce,tag)).decryptor()
                decryptor.authenticate_additional_data(header)
                remaining=size-HEADER_SIZE-16
                while remaining:
                    data=source.read(min(CHUNK,remaining))
                    if not data: raise ValueError('Backupfila er avkorta.')
                    remaining-=len(data);out.write(decryptor.update(data))
                out.write(decryptor.finalize())
        except InvalidTag: raise ValueError('Feil passfrase eller endra/øydelagd backup. Ingen data er godtekne.') from None
        restored=Path(folder)/'restored';restored.mkdir(mode=0o700)
        seen=set();total=0
        with tarfile.open(archive_path,mode='r:') as archive:
            for item in archive:
                name=item.name
                if not item.isfile() or name in seen or not (name in ('database.db','manifest.json','styre-og-kalender.zip') or re.fullmatch(r'bilag/[a-f0-9]{32}',name)):
                    raise ValueError('Utrygt eller ukjent innhald i backupen.')
                seen.add(name);total+=item.size
                if item.size<0 or total>MAX_BYTES or len(seen)>100000: raise ValueError('Backupgrensa er overskriden.')
                destination=restored/name;destination.parent.mkdir(mode=0o700,exist_ok=True)
                source=archive.extractfile(item)
                with destination.open('xb') as out:
                    destination.chmod(0o600)
                    while data:=source.read(CHUNK): out.write(data)
        verify_bundle(restored)
        yield restored


def encrypt_bundle(directory,output,password):
    directory=Path(directory);output=Path(output)
    if output.exists() or output.is_symlink(): raise ValueError('Målfila finst allereie. Vel eit nytt filnamn.')
    manifest=verify_bundle(directory)
    names=['manifest.json',*sorted(manifest['files'])]
    if sum((directory/name).stat().st_size for name in names)>MAX_BYTES-1024*1024:
        raise ValueError('Backupsettet er større enn grensa for kryptert eksport.')
    output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    salt=os.urandom(16);nonce=os.urandom(12);header=MAGIC+salt+nonce
    key=key_for(password,salt)
    fd,temp=tempfile.mkstemp(prefix='.kryptert-',dir=output.parent)
    temporary=Path(temp)
    try:
        encryptor=Cipher(algorithms.AES(key),modes.GCM(nonce)).encryptor()
        encryptor.authenticate_additional_data(header)
        with os.fdopen(fd,'wb') as out:
            out.write(header);writer=EncryptedWriter(out,encryptor)
            with tarfile.open(mode='w|',fileobj=writer) as archive:
                for name in names:
                    path=directory/name
                    if path.is_symlink(): raise ValueError('Symbolsk lenkje i backupsettet.')
                    info=tarfile.TarInfo(name);info.size=path.stat().st_size;info.mode=0o600
                    with path.open('rb') as source: archive.addfile(info,source)
            out.write(encryptor.finalize());out.write(encryptor.tag);out.flush();os.fsync(out.fileno())
        # Require a successful actual decrypt/restore before finalizing the export.
        with verified_archive(temporary,password): pass
        # Exclusive creation avoids replacing an output created by another job.
        os.link(temporary,output);temporary.unlink()
        return output
    finally:
        temporary.unlink(missing_ok=True)
