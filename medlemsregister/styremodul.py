"""Årsfesta offentlege styreopplysningar, felles med Jekyll-nettsida."""
from pathlib import Path
import hashlib
import re
import yaml

ROOT=Path(__file__).resolve().parent.parent

def load_board(year):
    raw=source_bytes()
    data=yaml.safe_load(raw)
    people=data.get('ar',{}).get(str(year))
    if people is None: raise ValueError(f'Ingen styreopplysningar er registrerte for {year}.')
    result=[]
    for person in people:
        name=str(person.get('namn','')).strip();role=str(person.get('rolle','')).strip()
        picture=str(person.get('bilete',''))
        position=str(person.get('bilete_posisjon','center'))
        if not name or not role:raise ValueError('Styremedlemmar må ha namn og verv.')
        if picture and (not picture.startswith('/lutar/bilete/styret/') or Path(picture).name in ('','.','..') or '..' in picture):raise ValueError('Ugyldig styrebilete.')
        if not re.fullmatch(r'(center|top|bottom|left|right|\d+%)( (center|top|bottom|left|right|\d+%))?',position):raise ValueError('Ugyldig biletplassering.')
        result.append(dict(namn=name,rolle=role,bilete=picture,bilete_posisjon=position))
    return dict(year=int(year),people=result,source_revision=hashlib.sha256(raw).hexdigest())


def board_file():
    import os
    return Path(os.environ.get('BYGDELISTA_STYRE_FILE',str(Path.home()/'bygdelista-data'/'styre.yml')))


def source_bytes():
    path=board_file()
    return (path if path.exists() else ROOT/'_data'/'styre.yml').read_bytes()


def install_board(app,require_admin):
    from flask import request,render_template,redirect,send_file,abort
    from io import BytesIO
    import fcntl,os,uuid

    @app.route('/styret',methods=['GET','POST'])
    @require_admin
    def board_editor():
        error=None;status=200
        try:
            year=int(request.values.get('year',2026))
            if not 1900<=year<=2200:raise ValueError('Vel eit år mellom 1900 og 2200.')
        except ValueError:
            year=2026;error='Ugyldig år.';status=400
        if request.method=='POST' and not error:
            path=board_file();path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            with (path.parent/'.styre.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                raw=source_bytes();data=yaml.safe_load(raw)
                try:
                    if request.form.get('revision')!=hashlib.sha256(raw).hexdigest():raise ValueError('Styret er endra. Last sida på nytt før du prøver igjen.')
                    name=request.form.get('name','').strip();role=request.form.get('role','').strip()
                    if not name or not role or len(name)>200 or len(role)>200:raise ValueError('Fyll inn namn og verv, maks 200 teikn.')
                    people=data.setdefault('ar',{}).setdefault(str(year),[])
                    index=int(request.form.get('index','-1'))
                    if index < -1 or index>=len(people):raise ValueError('Ugyldig styremedlem.')
                    person=dict(people[index]) if index>=0 else {}
                    person.update(namn=name,rolle=role,initialar=name.split()[0])
                    picture=request.files.get('portrait')
                    if picture and picture.filename:
                        content=picture.read(3*1024*1024+1)
                        if len(content)>3*1024*1024:raise ValueError('Portrettet må vere under 3 MiB.')
                        if content.startswith(b'\xff\xd8\xff'):ext='.jpg'
                        elif content.startswith(b'\x89PNG\r\n\x1a\n'):ext='.png'
                        elif content[:4]==b'RIFF' and content[8:12]==b'WEBP':ext='.webp'
                        else:raise ValueError('Bruk eit JPEG-, PNG- eller WebP-bilete.')
                        directory=path.parent/'styreportrett';directory.mkdir(mode=0o700,exist_ok=True)
                        filename=uuid.uuid4().hex+ext
                        with (directory/filename).open('xb') as target:target.write(content)
                        (directory/filename).chmod(0o600)
                        person.update(bilete='/lutar/bilete/styret/'+filename,bilete_posisjon='center')
                    if index>=0:people[index]=person
                    else:people.append(person)
                    if request.form.get('current')=='yes':data['gjeldande_ar']=year
                    temp=path.with_suffix('.tmp');temp.write_text(yaml.safe_dump(data,allow_unicode=True,sort_keys=False));temp.chmod(0o600);temp.replace(path)
                    return redirect(app.jinja_env.globals['prefix_url']('board_editor')+'?year='+str(year)+'&saved=1')
                except (ValueError,TypeError) as exc:error=str(exc);status=400
        raw=source_bytes();data=yaml.safe_load(raw);people=data.get('ar',{}).get(str(year),[])
        try:index=int(request.args.get('edit','-1'));person=people[index] if 0<=index<len(people) else {}
        except ValueError:index=-1;person={}
        response=app.make_response((render_template('styret.html',year=year,people=people,person=person,index=index,current=data['gjeldande_ar'],revision=hashlib.sha256(raw).hexdigest(),error=error,submitted=request.form if error else {}),status))
        response.headers['Cache-Control']='no-store';return response

    @app.get('/styret/nettsidepakke')
    @require_admin
    def board_export():
        import zipfile
        data=yaml.safe_load(source_bytes());output=BytesIO()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr('_data/styre.yml',source_bytes())
            names=set()
            for people in data['ar'].values():
                for person in people:
                    name=Path(person.get('bilete','')).name
                    if not name or name in names:continue
                    names.add(name)
                    photo=board_file().parent/'styreportrett'/name
                    if not photo.exists():photo=ROOT/'lutar'/'bilete'/'styret'/name
                    if photo.is_file():bundle.write(photo,'lutar/bilete/styret/'+name)
        output.seek(0)
        return send_file(output,mimetype='application/zip',as_attachment=True,download_name='styret-nettside.zip',max_age=0)
