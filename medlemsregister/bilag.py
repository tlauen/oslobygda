"""Private uforanderlege vedlegg. Ingen statisk eksponering eller offentleg eksport."""
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import re
import tempfile
import uuid

from werkzeug.utils import secure_filename
from database import managed_db
from rekneskap import now, label

MAX_FILE = 10 * 1024 * 1024


def private_root(value):
    root=Path(value).expanduser().absolute()
    if root.is_symlink(): raise ValueError('Bilagsmappa kan ikkje vere ei symbolsk lenkje.')
    root=root.resolve()
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    root.chmod(0o700)
    return root


@contextmanager
def receipt_lock(root,exclusive=False):
    root=private_root(root)
    fd=os.open(root/'.bilag.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'a+b') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try: yield root
        finally: fcntl.flock(handle,fcntl.LOCK_UN)


def file_path(root,key):
    if not re.fullmatch(r'[a-f0-9]{32}',key): raise ValueError('Ugyldig bilagsnøkkel.')
    path=Path(root)/key
    if path.is_symlink(): raise ValueError('Bilag kan ikkje vere ei symbolsk lenkje.')
    return path


def store_receipt(get_db,root,upload,actor,replaces_id=None,reason=''):
    name=secure_filename(upload.filename or '')
    extension=Path(name).suffix.lower()
    data=upload.stream.read(MAX_FILE+1)
    if not data or len(data)>MAX_FILE: raise ValueError('Bilaget må vere mellom 1 byte og 10 MiB.')
    types={'.pdf':('application/pdf',b'%PDF-'),'.png':('image/png',b'\x89PNG\r\n\x1a\n'),
           '.jpg':('image/jpeg',b'\xff\xd8\xff'),'.jpeg':('image/jpeg',b'\xff\xd8\xff')}
    if extension not in types or not data.startswith(types[extension][1]):
        raise ValueError('Bruk PDF, JPEG eller PNG med korrekt filinnhald.')
    reason=label(reason,1000,replaces_id is not None)
    key=uuid.uuid4().hex
    with receipt_lock(root) as directory:
        path=file_path(directory,key)
        fd,temp=tempfile.mkstemp(prefix='.upload-',dir=directory)
        try:
            with os.fdopen(fd,'wb') as target:
                target.write(data);target.flush();os.fsync(target.fileno())
            os.replace(temp,path)
            with managed_db(get_db) as db:
                db.execute('BEGIN IMMEDIATE')
                if replaces_id and not db.execute('SELECT 1 FROM ledger_receipts WHERE id=?',(replaces_id,)).fetchone():
                    raise ValueError('Originalbilaget finst ikkje.')
                return db.execute('''INSERT INTO ledger_receipts
                    (file_key,original_name,media_type,size,sha256,actor,created_at,replaces_id,reason)
                    VALUES (?,?,?,?,?,?,?,?,?)''',(key,name,types[extension][0],len(data),hashlib.sha256(data).hexdigest(),actor,now(),replaces_id,reason)).lastrowid
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        finally: Path(temp).unlink(missing_ok=True)


def verified_receipt(root,row):
    path=file_path(root,row['file_key'])
    data=path.read_bytes()
    if len(data)!=row['size'] or hashlib.sha256(data).hexdigest()!=row['sha256']:
        raise ValueError('Bilaget manglar eller har feil kontrollsum.')
    return data
