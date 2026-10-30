"""Isolert Nidarosbygda på loopback. Køyr som eigen prosess, aldri via produksjons-WSGI."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys


def prepare(root):
    root=Path(root).expanduser().absolute()
    repo=Path(__file__).resolve().parent.parent
    if root==repo or repo in root.parents or root.is_symlink():
        raise ValueError('Testdata må liggje i eiga mappe utanfor repoet.')
    root=root.resolve();marker=root/'NIDAROSBYGDA-TEST'
    if root.exists() and any(root.iterdir()) and not marker.is_file():
        raise ValueError('Mappa er ikkje eit Nidarosbygda-testmiljø. Vel ei ny, tom mappe.')
    root.mkdir(parents=True,exist_ok=True,mode=0o700);root.chmod(0o700)
    marker.write_text('Berre fiktive data. Nidarosbygda kulturlag.\n');marker.chmod(0o600)
    for key in list(os.environ):
        if key.startswith(('MEDLEMSREGISTER_','VIPPS_','GITHUB_','BREVO_','SMTP_','PUBLIC_DOCUMENTS_','BYGDELISTA_','FLASK_')):
            os.environ.pop(key,None)
    os.environ.update(BYGDELISTA_LOCAL_TEST='1',VIPPS_SIGNUP_MODE='disabled',
                      MEDLEMSREGISTER_DB_KEY='',BYGDELISTA_BILAG_DIR=str(root/'bilag'))
    os.environ['BYGDELISTA_STYRE_FILE']=str(root/'styre.yml')
    settings=root/'testkonto.json'
    if settings.exists():
        if settings.is_symlink():raise ValueError('Testinnstillingar kan ikkje vere symbolsk lenkje.')
        account=json.loads(settings.read_text())
    else:
        import pyotp
        account=dict(username='teststyret',password=secrets.token_urlsafe(18),totp=pyotp.random_base32(),session_key=secrets.token_urlsafe(48))
        settings.write_text(json.dumps(account,indent=2));settings.chmod(0o600)
    os.environ['MEDLEMSREGISTER_SECRET_KEY']=account['session_key']
    return root,account


def install_guards(root):
    def inside(value):
        if isinstance(value,int):return True
        path=Path(value).resolve()
        return path==root or root in path.parents
    def guard(event,args):
        if event in ('socket.getaddrinfo','socket.gethostbyname','socket.gethostbyaddr') and args[0] not in ('127.0.0.1','localhost','::1'):
            raise PermissionError('Nidarosbygda: ekstern namneoppslag er sperra.')
        if event=='open':
            mode=args[1] or '';flags=args[2] or 0
            writing=any(c in mode for c in 'wax+') or flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC)
            if writing and not inside(args[0]):raise PermissionError('Skriving utanfor testmappa er sperra.')
        if event in ('os.remove','os.rmdir','os.mkdir','os.chmod') and not inside(args[0]):
            raise PermissionError('Filendring utanfor testmappa er sperra.')
        if event in ('os.rename','os.link','os.symlink') and not all(inside(x) for x in args[:2]):
            raise PermissionError('Filflytting utanfor testmappa er sperra.')
        if event in ('socket.connect','socket.connect_ex','socket.sendto','subprocess.Popen','os.system'):
            raise PermissionError('Nidarosbygda: utgåande nettverk og eksterne prosessar er sperra.')
        if event=='socket.bind' and args[1][0] not in ('127.0.0.1','::1'):
            raise PermissionError('Nidarosbygda kan berre lytte på loopback.')
        if event=='sqlite3.connect':
            raw=str(args[0])
            if raw.startswith('file:'):
                from urllib.parse import urlsplit,unquote
                uri=urlsplit(raw)
                if uri.netloc:raise PermissionError('Ekstern databaseadresse er sperra.')
                raw=unquote(uri.path)
            path=Path(raw).resolve()
            if root not in path.parents:raise PermissionError('Database utanfor testmappa er sperra.')
    sys.addaudithook(guard)


def build(root,account):
    import app as module
    from database import managed_db
    from werkzeug.security import generate_password_hash
    from jinja2 import BaseLoader
    from flask import request,abort,render_template_string
    import pyotp
    # Prøveåret 2026 må kunne visast komplett, også før det verkelege årsskiftet.
    from datetime import date
    import arsdokument,offentleg_rekneskap
    arsdokument.today=lambda:date(2027,2,24)
    offentleg_rekneskap.today=lambda:date(2027,2,24)
    module.DB_PATH=root/'nidarosbygda.db'
    module.DB_KEY='';module._use_sqlcipher=False
    app=module.app
    app.config.update(SESSION_COOKIE_NAME='nidarosbygda_test',SESSION_COOKIE_SECURE=False,DEBUG=False,
                      BILAG_DIR=str(root/'bilag'))
    module.init_db()
    with managed_db(module.get_db) as db:
        if not db.execute('SELECT 1 FROM board_users WHERE username=?',(account['username'],)).fetchone():
            db.execute('INSERT INTO board_users(username,password_hash,totp_secret,session_version) VALUES (?,?,?,?)',
                       (account['username'],generate_password_hash(account['password']),account['totp'],secrets.token_hex(16)))
        if not db.execute('SELECT 1 FROM members').fetchone():
            for name in ('Prøveperson Ein','Prøveperson To','Prøveperson Tre'):
                db.execute('INSERT INTO members(full_name,email,membership_type,payment_status,consent_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
                           (name,name.split()[-1].lower()+'@example.invalid','kul','ubetalt',module.now() if hasattr(module,'now') else '2026-01-01','2026-01-01','2026-01-01'))
    original=app.jinja_loader
    class TestNames(BaseLoader):
        def get_source(self,environment,template):
            source,path,fresh=original.get_source(environment,template)
            return source.replace('Oslobygda kulturlag','Nidarosbygda kulturlag'),path,fresh
    app.jinja_loader=TestNames()
    # Kalenderen brukar same validering/redigeringsflyt, men berre ei lokal YAML-fil.
    import tilskipingar
    calendar=root/'kalender.yaml'
    if not calendar.exists():calendar.write_text('[]\n');calendar.chmod(0o600)
    def init_calendar(self,token=None): self.branch='lokal-test'
    def local_api(self,method,body=None):
        raw=calendar.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        if method=='GET':return dict(content=base64.b64encode(raw).decode(),sha=sha)
        if method=='PUT':
            if body.get('sha')!=sha:raise tilskipingar.Conflict('Kalenderen er endra. Last sida på nytt.')
            data=base64.b64decode(body['content']);temporary=root/'kalender.tmp'
            temporary.write_bytes(data);temporary.chmod(0o600);temporary.replace(calendar)
            return {}
        raise ValueError('Berre lokal kalenderlesing og -lagring er støtta.')
    tilskipingar.GithubCalendar.__init__=init_calendar
    tilskipingar.GithubCalendar.api=local_api
    @app.before_request
    def loopback_only():
        if request.host.split(':')[0] not in ('127.0.0.1','localhost') or request.remote_addr not in ('127.0.0.1','::1'):
            abort(403)
    @app.after_request
    def test_banner(response):
        if response.mimetype=='text/html' and not response.direct_passthrough:
            text=response.get_data(as_text=True)
            banner='<aside style="padding:12px;background:#fbefcf;color:#12110e;text-align:center;font:15px system-ui"><strong>TESTMILJØ · Nidarosbygda kulturlag</strong> · Prøvedato: 24. februar 2027 · Berre fiktive data. Ekte betaling, e-post og publisering er sperra. <a href="/testkonto">Testinnlogging</a></aside>'
            import re
            text=re.sub(r'(<body\b[^>]*>)',lambda m:m[0]+banner,text,count=1)
            response.set_data(text)
        response.headers['Cache-Control']='no-store'
        return response
    @app.get('/testkonto')
    def test_account():
        return render_template_string('''<!doctype html><html lang="nn"><head><meta charset="utf-8"><title>Lokal testkonto</title></head><body><main style="max-width:650px;margin:40px auto;font:18px/1.6 system-ui"><h1>Nidarosbygda – testinnlogging</h1><p>Denne kontoen gjeld berre lokale, fiktive data.</p><dl><dt>Brukarnamn</dt><dd>{{ user }}</dd><dt>Passord</dt><dd>{{ password }}</dd><dt>Autentiseringskode (skiftar kvart 30. sekund)</dt><dd>{{ code }}</dd></dl><p><a href="/login">Opne vanleg innlogging</a> · <a href="/testkonto">Hent ny kode</a></p><p>Du kan også bruke autentiseringsapp med nøkkelen i den private lokale fila testkonto.json.</p></main></body></html>''',user=account['username'],password=account['password'],code=pyotp.TOTP(account['totp']).now())
    return app,module


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=Path.home()/'Documents/Codex/nidarosbygda-test')
    parser.add_argument('--port',type=int,default=8877)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    root,account=prepare(args.data_dir)
    import tempfile
    (root/'tmp').mkdir(exist_ok=True,mode=0o700)
    tempfile.tempdir=str(root/'tmp')
    install_guards(root)
    app,module=build(root,account)
    if args.check:
        import socket
        try:socket.create_connection(('example.com',443),timeout=1)
        except PermissionError:pass
        else:raise RuntimeError('Nettverkssperra feila.')
        client=app.test_client()
        assert client.get('/').status_code==302
        assert client.get('/testkonto').status_code==200
        assert module.DB_PATH.parent==root
        import sqlite3
        try:sqlite3.connect(root.parent/'skal-ikkje-opnast.db')
        except PermissionError:pass
        else:raise RuntimeError('Databasesperra feila.')
        try:(root.parent/'skal-ikkje-skrivast.txt').write_text('test')
        except PermissionError:pass
        else:raise RuntimeError('Filsperra feila.')
        import pyotp
        client.get('/login')
        with client.session_transaction() as session:token=session['csrf_token']
        response=client.post('/login',data=dict(username=account['username'],password=account['password'],code=pyotp.TOTP(account['totp']).now(),csrf_token=token))
        assert response.status_code==302
        for path in ('/','/okonomi','/arsmote','/budsjett','/arsmote/hjelp','/tilskipingar'):
            response=client.get(path)
            assert response.status_code==200,(path,response.status_code)
            assert b'Nidarosbygda' in response.data
        assert not any(os.environ.get(key) for key in ('SMTP_HOST','BREVO_API_KEY','GITHUB_DOCUMENTS_TOKEN','GITHUB_EVENTS_TOKEN'))
        print('Lokal isolasjon, separat database og sperra nettverk: OK.')
        return
    print(f'Nidarosbygda: http://127.0.0.1:{args.port}/testkonto\nPrivate testdata: {root}',flush=True)
    app.run(host='127.0.0.1',port=args.port,debug=False,use_reloader=False)

if __name__=='__main__':main()
