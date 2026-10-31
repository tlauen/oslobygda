"""Saklister og felles møtereglar, med versjonskontroll og offentleg kø."""
import json
import re
from pathlib import Path
from flask import render_template, request, redirect, abort
from arsdokument import canonical, digest, stamp, today, year, integer, DocumentConflict
from database import managed_db

ROOT = Path(__file__).resolve().parents[1]
LINKS = {'arsmelding': 'arsmeldingar', 'rekneskap': 'rekneskap', 'budsjett': 'budsjett'}


def init_agendas(get_db):
    with managed_db(get_db) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS meeting_drafts (
          kind TEXT NOT NULL CHECK(kind IN ('sakliste','motereglar')), report_year INTEGER NOT NULL,
          revision INTEGER NOT NULL DEFAULT 1, content TEXT NOT NULL,
          PRIMARY KEY(kind,report_year));
        CREATE TABLE IF NOT EXISTS meeting_publication_queue (
          id INTEGER PRIMARY KEY, payload TEXT NOT NULL, content_hash TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sending','stored','visible','failed')),
          attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT NOT NULL DEFAULT '',
          UNIQUE(content_hash));
        CREATE TRIGGER IF NOT EXISTS meeting_payload_immutable
        BEFORE UPDATE OF payload,content_hash ON meeting_publication_queue
        BEGIN SELECT RAISE(ABORT,'Publiseringsinnhald kan ikkje endrast'); END;
        ''')
        seed = json.loads((ROOT/'_data/motereglar.json').read_text())
        db.execute("INSERT OR IGNORE INTO meeting_drafts(kind,report_year,content) VALUES ('motereglar',0,?)", (canonical(seed),))


def document_choices():
    choices = json.loads((ROOT/'_data/arsmotesider.json').read_text())
    for kind, folder in LINKS.items():
        for path in (ROOT/'om'/folder).glob('*/index.md'):
            if re.fullmatch(r'\d{4}', path.parent.name):
                choices[f'{kind}:{path.parent.name}'] = f'{dict(arsmelding="Årsmelding",rekneskap="Rekneskap",budsjett="Budsjett")[kind]} {path.parent.name}'
    return dict(sorted(choices.items()))


def default_agenda(meeting_year):
    meeting_year=year(meeting_year)
    def item(title, document='', subitems=None):
        return dict(title=title,body='',document=document,subitems=subitems or [])
    choices=document_choices()
    def link(kind, report_year):
        value=f'{kind}:{report_year}'
        return value if value in choices else ''
    return dict(title=f'Sakliste til årsmøtet {meeting_year}',details='',items=[
        item('Organisering av møtet',subitems=['Val av ordstyrar','Val av protokollskrivar',
             'Godkjenning av innkalling','Godkjenning av møtereglar','Godkjenning av sakliste',
             'Val av protokollunderskrivarar']),
        item(f'Årsmelding for {meeting_year-1}',link('arsmelding',meeting_year-1)),
        item(f'Rekneskap for {meeting_year-1}',link('rekneskap',meeting_year-1)),
        item(f'Medlemspengar for {meeting_year+1}'),
        item(f'Planar for {meeting_year}'),
        item(f'Budsjett for {meeting_year}',link('budsjett',meeting_year)),
        item('Ymse'),
        item('Val',subitems=['Val av leiar','Val av styremedlemmar'])])


def validate_meeting(payload):
    if not isinstance(payload, dict) or set(payload) != {'schema_version','kind','report_year','status','version_id','source_revision','generated_at','content'}:
        raise ValueError('Ugyldig møtepublisering.')
    if payload['schema_version'] != 1 or payload['kind'] not in ('sakliste','motereglar') or payload['status'] != 'meeting':
        raise ValueError('Ugyldig møtepublisering.')
    year(payload['report_year'])
    if type(payload['source_revision']) is not int or payload['source_revision'] < 1 or not re.fullmatch(payload['kind']+r'-\d+', payload['version_id']):
        raise ValueError('Ugyldig versjon.')
    if not isinstance(payload['generated_at'], str) or len(payload['generated_at']) > 50:
        raise ValueError('Ugyldig tidspunkt.')
    validate_content(payload['kind'], payload['content'])


def validate_content(kind, content):
    def text(value, limit, required=False):
        if not isinstance(value, str) or len(value)>limit or (required and not value.strip()):
            raise ValueError('Fyll inn tekst innanfor lengdegrensene.')
    if not isinstance(content, dict): raise ValueError('Ugyldig innhald.')
    if kind == 'motereglar':
        if set(content) != {'body'}: raise ValueError('Ugyldige møtereglar.')
        text(content['body'],30000,True)
        return
    if set(content) != {'title','details','items'}: raise ValueError('Ugyldig sakliste.')
    text(content['title'],200,True); text(content['details'],4000)
    if not isinstance(content['items'],list) or not 1 <= len(content['items']) <= 100:
        raise ValueError('Saklista må ha mellom 1 og 100 saker.')
    for item in content['items']:
        if not isinstance(item,dict) or set(item) not in ({'title','body','document'},{'title','body','document','subitems'}): raise ValueError('Ugyldig sak.')
        text(item['title'],200,True); text(item['body'],6000)
        subs=item.get('subitems',[])
        if not isinstance(subs,list) or len(subs)>30: raise ValueError('Maks 30 undersaker per sak.')
        for sub in subs: text(sub,200,True)
        if not isinstance(item['document'],str) or (item['document'] and not re.fullmatch(r'(arsmelding|rekneskap|budsjett):\d{4}', item['document'])):
            raise ValueError('Ugyldig dokumentkopling.')
        if item['document']: year(item['document'].split(':')[1])


def rule_blocks(body):
    blocks=[]
    paragraph=[]
    def flush():
        if paragraph:
            blocks.append(('text','\n'.join(paragraph)))
            paragraph.clear()
    for line in body.splitlines():
        if line.startswith('## '):
            flush(); blocks.append(('heading',line[3:]))
        elif not line.strip(): flush()
        else: paragraph.append(line)
    flush()
    return blocks


class Meetings:
    def __init__(self, get_db): self.get_db = get_db

    def save(self, kind, report_year, revision, content):
        if kind not in ('sakliste','motereglar'): raise ValueError('Ukjend dokumenttype.')
        report_year = 0 if kind == 'motereglar' else year(report_year)
        validate_content(kind,content)
        for item in content.get('items',[]):
            if item['document'] and item['document'] not in document_choices():
                raise ValueError('Årssida for dokumentet er ikkje klargjord.')
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT revision FROM meeting_drafts WHERE kind=? AND report_year=?',(kind,report_year)).fetchone()
            if (old['revision'] if old else 0) != integer(revision):
                raise DocumentConflict('Dokumentet er endra av nokon andre. Teksten din er bevart nedanfor. Opne siste versjon før du lagrar.')
            db.execute('INSERT INTO meeting_drafts(kind,report_year,revision,content) VALUES (?,?,1,?) ON CONFLICT(kind,report_year) DO UPDATE SET revision=revision+1,content=excluded.content', (kind,report_year,canonical(content)))

    def enqueue(self, kind, report_year, revision):
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM meeting_drafts WHERE kind=? AND report_year=?',(kind,report_year)).fetchone()
            if not row or row['revision'] != integer(revision): raise DocumentConflict('Dokumentet er endra. Last inn og kontroller siste versjon før publisering.')
            # Each revision is frozen once; retries reuse its original payload and timestamp.
            for queued in db.execute('SELECT payload FROM meeting_publication_queue'):
                payload=json.loads(queued['payload'])
                if payload['kind']==kind and payload['source_revision']==row['revision'] and (kind=='motereglar' or payload['report_year']==report_year): return payload
            next_id=db.execute('SELECT COALESCE(MAX(id),0)+1 FROM meeting_publication_queue').fetchone()[0]
            payload=dict(schema_version=1,kind=kind,report_year=report_year or today().year,status='meeting',version_id=f'{kind}-{next_id}',source_revision=row['revision'],generated_at=stamp(),content=json.loads(row['content']))
            validate_meeting(payload)
            raw=canonical(payload)
            db.execute('INSERT INTO meeting_publication_queue(payload,content_hash) VALUES (?,?)',(raw,digest(raw)))
            return payload


def install_meetings(app,get_db,require_admin):
    service=Meetings(get_db); app.extensions['meetings']=service
    app.jinja_env.filters['meeting_blocks']=rule_blocks

    @app.route('/sakliste', methods=['GET','POST'])
    @require_admin
    def agenda_index():
        if request.method=='GET' and request.args.get('meeting_year'):
            try: selected=year(request.args['meeting_year'])
            except ValueError: abort(400)
            return redirect(app.jinja_env.globals['prefix_url']('agenda_editor',meeting_year=selected))
        return editor('motereglar',0)

    @app.route('/sakliste/<int:meeting_year>',methods=['GET','POST'])
    @require_admin
    def agenda_editor(meeting_year):
        if not 1900<=meeting_year<=2200: abort(404)
        return editor('sakliste',meeting_year)

    def editor(kind, report_year):
        error=None; status=200; submitted=None
        with managed_db(get_db) as db:
            row=db.execute('SELECT * FROM meeting_drafts WHERE kind=? AND report_year=?',(kind,report_year)).fetchone()
        content=json.loads(row['content']) if row else default_agenda(report_year)
        revision=row['revision'] if row else 0
        if request.method=='POST':
            try:
                if request.form.get('action')=='publish':
                    if request.form.get('confirmed')!='yes': raise ValueError('Stadfest at innhaldet kan publiserast.')
                    payload=service.enqueue(kind,report_year,request.form.get('revision'))
                    from publisering import publish_from_button
                    publish_from_button(app,('meeting',payload['version_id']))
                else:
                    if kind=='motereglar': submitted=dict(body=request.form.get('body','').strip())
                    else:
                        titles=request.form.getlist('item_title'); bodies=request.form.getlist('item_body'); links=request.form.getlist('item_document')
                        subs=request.form.getlist('item_subitems')
                        if not subs: subs=['']*len(titles)
                        if not len(titles)==len(bodies)==len(links)==len(subs): raise ValueError('Ufullstendig sakliste.')
                        submitted=dict(title=request.form.get('title','').strip(),details=request.form.get('details','').strip(),items=[dict(title=t.strip(),body=b.strip(),document=d,subitems=[line.strip() for line in sub.splitlines() if line.strip()]) for t,b,d,sub in zip(titles,bodies,links,subs)])
                    service.save(kind,report_year,request.form.get('revision'),submitted)
                return redirect(app.jinja_env.globals['prefix_url']('agenda_index' if kind=='motereglar' else 'agenda_editor',**({} if kind=='motereglar' else {'meeting_year':report_year})))
            except ValueError as exc:
                error=str(exc); status=409 if isinstance(exc,DocumentConflict) else 400
                if submitted is not None: content=submitted
                revision=request.form.get('revision',revision)
        with managed_db(get_db) as db:
            drafts=db.execute("SELECT report_year,revision FROM meeting_drafts WHERE kind='sakliste' ORDER BY report_year DESC").fetchall()
            jobs=[]
            for job in db.execute('SELECT * FROM meeting_publication_queue ORDER BY id DESC'):
                payload=json.loads(job['payload'])
                if payload['kind']==kind and (kind=='motereglar' or payload['report_year']==report_year): jobs.append(job)
        return render_template('sakliste.html',kind=kind,meeting_year=report_year,content=content,revision=revision,drafts=drafts,jobs=jobs,error=error,choices=document_choices(),next_meeting_year=today().year+1),status
