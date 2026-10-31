"""Protokollføring, to personlege godkjenningar og automatisk publisering."""
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlsplit

from flask import abort, flash, redirect, render_template, request, session, send_from_directory
from arsdokument import canonical, digest, stamp, today, year, integer, DocumentConflict
from database import managed_db
from epost import send_message, DeliveryUncertain

LINK_DAYS = 14
APPROVED_WITHOUT_REMARKS = 'Godkjent utan merknader.'


def init_minutes(get_db):
    with managed_db(get_db) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS minutes_writers (
          report_year INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL,
          token_hash TEXT NOT NULL UNIQUE, expires REAL NOT NULL, mail_status TEXT NOT NULL DEFAULT 'pending');
        CREATE TABLE IF NOT EXISTS minutes_drafts (
          report_year INTEGER PRIMARY KEY, revision INTEGER NOT NULL DEFAULT 1,
          content TEXT NOT NULL, updated_by TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS minutes_reviews (
          id INTEGER PRIMARY KEY, report_year INTEGER NOT NULL, source_revision INTEGER NOT NULL,
          snapshot TEXT NOT NULL, content_hash TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','approved','rejected','cancelled')),
          UNIQUE(report_year,source_revision));
        CREATE TABLE IF NOT EXISTS minutes_signers (
          id INTEGER PRIMARY KEY, review_id INTEGER NOT NULL REFERENCES minutes_reviews(id),
          slot INTEGER NOT NULL CHECK(slot IN (1,2)), name TEXT NOT NULL, email TEXT NOT NULL,
          token_hash TEXT UNIQUE, expires REAL, approved_at TEXT, rejection TEXT NOT NULL DEFAULT '',
          mail_status TEXT NOT NULL DEFAULT 'pending', UNIQUE(review_id,slot), UNIQUE(review_id,email));
        CREATE TRIGGER IF NOT EXISTS minutes_review_immutable
        BEFORE UPDATE OF report_year,source_revision,snapshot,content_hash,created_by,created_at ON minutes_reviews
        BEGIN SELECT RAISE(ABORT,'Godkjenningskopien er fast'); END;
        CREATE TRIGGER IF NOT EXISTS minutes_review_no_delete
        BEFORE DELETE ON minutes_reviews
        BEGIN SELECT RAISE(ABORT,'Godkjenningskopien skal bevarast'); END;
        CREATE TRIGGER IF NOT EXISTS minutes_approval_immutable
        BEFORE UPDATE OF approved_at ON minutes_signers WHEN OLD.approved_at IS NOT NULL
        BEGIN SELECT RAISE(ABORT,'Ei godkjenning kan ikkje skrivast om'); END;
        CREATE TRIGGER IF NOT EXISTS minutes_signer_no_delete
        BEFORE DELETE ON minutes_signers
        BEGIN SELECT RAISE(ABORT,'Underskrivaren skal bevarast'); END;
        CREATE TRIGGER IF NOT EXISTS minutes_signer_identity_immutable
        BEFORE UPDATE OF review_id,slot,name,email ON minutes_signers
        BEGIN SELECT RAISE(ABORT,'Underskrivaren høyrer til ein fast kopi'); END;
        ''')


def validate_minutes_content(content):
    if not isinstance(content,dict) or set(content)!={'title','meeting_date','details','secretary','items'}:
        raise ValueError('Ugyldig protokoll.')
    for key,limit in (('title',200),('details',6000),('secretary',200)):
        if not isinstance(content[key],str) or len(content[key])>limit or (key!='details' and not content[key].strip()):
            raise ValueError('Fyll inn tittel og protokollskrivar innanfor lengdegrensene.')
    if not isinstance(content['meeting_date'],str): raise ValueError('Fyll inn møtedato.')
    try: date.fromisoformat(content['meeting_date'])
    except ValueError: raise ValueError('Fyll inn ein gyldig møtedato.') from None
    if not isinstance(content['items'],list) or not 1<=len(content['items'])<=100:
        raise ValueError('Protokollen må ha mellom 1 og 100 saker.')
    for item in content['items']:
        if not isinstance(item,dict) or set(item) not in ({'title','subitems','proposals','speakers','votes','decision'},{'title','subitems','subdecisions','proposals','speakers','votes','decision'}):
            raise ValueError('Ugyldig protokollsak.')
        for key,limit in (('title',200),('proposals',12000),('speakers',6000),('votes',6000),('decision',12000)):
            if not isinstance(item[key],str) or len(item[key])>limit or (key=='title' and not item[key].strip()):
                raise ValueError('Ugyldig eller for lang tekst i protokollsaka.')
        if not isinstance(item['subitems'],list) or len(item['subitems'])>30 or any(not isinstance(s,str) or not s.strip() or len(s)>200 for s in item['subitems']):
            raise ValueError('Ugyldige undersaker.')
        if 'subdecisions' in item:
            decisions=item['subdecisions']
            if not isinstance(decisions,list) or len(decisions)!=len(item['subitems']) or any(not isinstance(d,str) or len(d)>12000 for d in decisions):
                raise ValueError('Kvar undersak må ha sitt eige vedtaksfelt.')


def validate_minutes(payload):
    expected={'schema_version','kind','report_year','status','version_id','source_revision','generated_at','content','approved_by'}
    if not isinstance(payload,dict) or set(payload)!=expected or payload['kind']!='protokoll' or payload['status']!='approved' or payload['schema_version']!=1:
        raise ValueError('Berre godkjend protokoll kan publiserast.')
    if type(payload['report_year']) is not int: raise ValueError('Ugyldig møteår.')
    year(payload['report_year'])
    if type(payload['source_revision']) is not int or payload['source_revision']<1 or not isinstance(payload['version_id'],str) or not re.fullmatch(r'protokoll-\d+',payload['version_id']):
        raise ValueError('Ugyldig protokollversjon.')
    validate_minutes_content(payload['content'])
    if not isinstance(payload['approved_by'],list) or len(payload['approved_by'])!=2:
        raise ValueError('To godkjenningar er påkravde.')
    for signer in payload['approved_by']:
        if not isinstance(signer,dict) or set(signer)!={'name','approved_at'} or not isinstance(signer['name'],str) or not signer['name'].strip() or len(signer['name'])>200:
            raise ValueError('Ugyldig underskrivar.')
        try: datetime.fromisoformat(signer['approved_at'])
        except (ValueError,TypeError): raise ValueError('Ugyldig godkjenningstidspunkt.') from None
    try: datetime.fromisoformat(payload['generated_at'])
    except (ValueError,TypeError): raise ValueError('Ugyldig publiseringstidspunkt.') from None


def parse_minutes_form(form, previous):
    fields={key:form.getlist(key) for key in ('case_title','case_subitems','proposals','speakers','votes','decision')}
    if len({len(v) for v in fields.values()})!=1: raise ValueError('Ufullstendig protokollskjema.')
    count=len(fields['case_title'])
    approved=set(form.getlist('case_approved'))
    if not approved.issubset({str(i) for i in range(count)}): raise ValueError('Ugyldig saksnummer.')
    content=dict(title=form.get('title','').strip(),meeting_date=form.get('meeting_date',''),secretary=form.get('secretary','').strip(),details=form.get('details','').strip(),items=[])
    for i in range(count):
        if form.get(f'subitems_present_{i}')=='yes':
            subs=[s.strip() for s in form.getlist(f'sub_title_{i}')]
            decisions=[s.strip() for s in form.getlist(f'sub_decision_{i}')]
            subapproved=set(form.getlist(f'sub_approved_{i}'))
            if len(subs)!=len(decisions) or not subapproved.issubset({str(j) for j in range(len(subs))}):
                raise ValueError('Ufullstendige vedtaksfelt for undersakene.')
            decisions=[APPROVED_WITHOUT_REMARKS if str(j) in subapproved else d for j,d in enumerate(decisions)]
        else:
            # Older open forms must preserve saved subcase decisions when titles still match.
            subs=[s.strip() for s in fields['case_subitems'][i].splitlines() if s.strip()]
            old=previous['items'][i] if i<len(previous['items']) else {}
            old_subs=old.get('subitems',[]);old_decisions=old.get('subdecisions',[])
            decisions=[old_decisions[j] if j<len(old_decisions) and j<len(old_subs) and old_subs[j]==title else '' for j,title in enumerate(subs)]
        item=dict(title=fields['case_title'][i].strip(),subitems=subs,subdecisions=decisions,**{key:fields[key][i].strip() for key in ('proposals','speakers','votes','decision')})
        if str(i) in approved: item['decision']=APPROVED_WITHOUT_REMARKS
        content['items'].append(item)
    return content


def approval_origin():
    origin=os.environ.get('BYGDELISTA_PUBLIC_ORIGIN','https://bygdelista.oslobygda.no').rstrip('/')
    parts=urlsplit(origin)
    if parts.scheme!='https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('BYGDELISTA_PUBLIC_ORIGIN må vere ei fast HTTPS-adresse.')
    return origin


def mail_ready():
    return all(os.environ.get(key,'').strip() for key in ('SMTP_HOST','SMTP_USER','SMTP_PASSWORD','STYRE_EPOST_FRA'))


class Minutes:
    def __init__(self,get_db): self.get_db=get_db

    def load(self,meeting_year):
        meeting_year=year(meeting_year)
        with managed_db(self.get_db) as db:
            row=db.execute('SELECT * FROM minutes_drafts WHERE report_year=?',(meeting_year,)).fetchone()
            if row: return row['revision'],json.loads(row['content'])
            agenda=db.execute("SELECT content FROM meeting_drafts WHERE kind='sakliste' AND report_year=?",(meeting_year,)).fetchone()
        if not agenda: raise ValueError('Lagre saklista før du opprettar protokoll.')
        agenda=json.loads(agenda['content'])
        content=dict(title=f'Protokoll frå årsmøtet {meeting_year}',meeting_date='',details=agenda['details'],secretary='',items=[])
        for item in agenda['items']:
            content['items'].append(dict(title=item['title'],subitems=item.get('subitems',[]),subdecisions=['']*len(item.get('subitems',[])),proposals=item.get('proposal',''),speakers='',votes='',decision=''))
        return 0,content

    def save(self,meeting_year,revision,content,actor):
        meeting_year=year(meeting_year);validate_minutes_content(content)
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT revision FROM minutes_drafts WHERE report_year=?',(meeting_year,)).fetchone()
            if (row['revision'] if row else 0)!=integer(revision): raise DocumentConflict('Protokollen er endra av nokon andre. Teksten din er bevart. Opne siste versjon før du lagrar.')
            db.execute('''INSERT INTO minutes_drafts(report_year,content,updated_by,updated_at) VALUES (?,?,?,?)
                ON CONFLICT(report_year) DO UPDATE SET revision=revision+1,content=excluded.content,updated_by=excluded.updated_by,updated_at=excluded.updated_at''',(meeting_year,canonical(content),actor,stamp()))
            # A changed draft cannot reuse either approval from an unfinished review.
            db.execute("UPDATE minutes_reviews SET state='cancelled' WHERE report_year=? AND state='pending'",(meeting_year,))

    def start_review(self,meeting_year,revision,signers,actor):
        meeting_year=year(meeting_year)
        if len(signers)!=2: raise ValueError('Vel to protokollunderskrivarar.')
        cleaned=[]
        for name,email in signers:
            name=name.strip();email=email.strip().casefold()
            if not name or len(name)>200 or len(email)>254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',email):
                raise ValueError('Fyll inn namn og gyldig e-post for begge underskrivarane.')
            cleaned.append((name,email))
        if cleaned[0][1]==cleaned[1][1]: raise ValueError('Underskrivarane må ha kvar si e-postadresse.')
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            draft=db.execute('SELECT * FROM minutes_drafts WHERE report_year=?',(meeting_year,)).fetchone()
            if not draft or draft['revision']!=integer(revision): raise DocumentConflict('Lagre og kontroller siste versjon før du sender til godkjenning.')
            content=json.loads(draft['content']);validate_minutes_content(content)
            if date.fromisoformat(content['meeting_date'])>today(): raise ValueError('Møtet må vere halde før protokollen blir send til godkjenning.')
            for item in content['items']:
                if item['subitems']:
                    decisions=item.get('subdecisions',[])
                    if len(decisions)!=len(item['subitems']) or any(not d.strip() for d in decisions):
                        raise ValueError('Fyll inn vedtak eller kryss av for godkjenning i kvar undersak før du sender protokollen.')
                elif not item['decision'].strip():
                    raise ValueError('Fyll inn vedtak, kryss av for godkjenning eller skriv «Ingen vedtak» i kvar sak før godkjenning.')
            old=db.execute('SELECT * FROM minutes_reviews WHERE report_year=? AND source_revision=?',(meeting_year,draft['revision'])).fetchone()
            if old: raise ValueError('Denne revisjonen er allereie send til godkjenning. Bruk ny lenkje ved sendefeil, eller lagre ei ny revisjon ved endringar.')
            rid=db.execute('INSERT INTO minutes_reviews(report_year,source_revision,snapshot,content_hash,created_by,created_at) VALUES (?,?,?,?,?,?)',(meeting_year,draft['revision'],draft['content'],digest(draft['content']),actor,stamp())).lastrowid
            for slot,(name,email) in enumerate(cleaned,1):
                db.execute('INSERT INTO minutes_signers(review_id,slot,name,email) VALUES (?,?,?,?)',(rid,slot,name,email))
            return rid

    def send_link(self,review_id,slot,path_prefix=''):
        if not mail_ready(): raise ValueError('E-postsending er ikkje konfigurert.')
        origin=approval_origin()
        token=secrets.token_urlsafe(32);token_hash=digest(token)
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('''SELECT s.*,r.state,r.report_year,r.source_revision FROM minutes_signers s
                JOIN minutes_reviews r ON r.id=s.review_id JOIN minutes_drafts d ON d.report_year=r.report_year AND d.revision=r.source_revision
                WHERE s.review_id=? AND s.slot=?''',(review_id,slot)).fetchone()
            if not row or row['state']!='pending' or row['approved_at']: raise ValueError('Godkjenninga er avslutta eller protokollen er endra.')
            db.execute("UPDATE minutes_signers SET token_hash=?,expires=?,mail_status='sending' WHERE id=?",(token_hash,time.time()+LINK_DAYS*86400,row['id']))
        message=EmailMessage()
        message['From']=os.environ['STYRE_EPOST_FRA'];message['To']=row['email']
        message['Subject']=f'Godkjenn protokoll frå årsmøtet {row["report_year"]}'
        # Fragment avoids putting the secret in ordinary HTTP access logs/referrers.
        url=origin+path_prefix+'/protokoll/godkjenn#'+token
        message.set_content(f'Hei {row["name"]}!\n\nDu er vald til protokollunderskrivar. Les den faste kopien av protokollen (revisjon {row["source_revision"]}) og godkjenn eller be om retting:\n\n{url}\n\nLenkja er personleg. Ikkje del henne vidare. Ho gjeld i {LINK_DAYS} dagar. Å opne lenkja godkjenner ikkje protokollen. Namnet ditt og tidspunktet for godkjenning blir publiserte saman med protokollen etter at begge har godkjent.\n')
        state='sent'
        try: send_message(message)
        except DeliveryUncertain: state='uncertain'
        except Exception: state='failed'
        with managed_db(self.get_db) as db:
            db.execute('UPDATE minutes_signers SET mail_status=? WHERE id=? AND token_hash=?',(state,row['id'],token_hash))
        return state

    def resolve(self,token_hash):
        with managed_db(self.get_db) as db:
            return self._resolve(db,token_hash)

    @staticmethod
    def _resolve(db,token_hash):
        row=db.execute('''SELECT s.*,r.report_year,r.source_revision,r.snapshot,r.content_hash,r.state,d.revision AS current_revision
            FROM minutes_signers s JOIN minutes_reviews r ON r.id=s.review_id
            JOIN minutes_drafts d ON d.report_year=r.report_year WHERE s.token_hash=?''',(token_hash,)).fetchone()
        if not row or row['expires']<time.time() or row['state'] not in ('pending','approved') or row['current_revision']!=row['source_revision'] or digest(row['snapshot'])!=row['content_hash']:
            raise ValueError('Lenkja er ugyldig, utgått eller erstatta. Be protokollskrivaren om ei ny lenkje.')
        return dict(row)

    def decide(self,token_hash,decision,note=''):
        if decision not in ('approve','reject'): raise ValueError('Vel godkjenning eller retting.')
        note=note.strip()
        if len(note)>4000 or (decision=='reject' and not note): raise ValueError('Forklar kva som må rettast (maks 4000 teikn).')
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._resolve(db,token_hash)
            if row['approved_at']:
                # Browser retries must never add another signature or publication.
                if decision=='approve': return None
                raise ValueError('Du har allereie godkjent denne kopien.')
            if row['state']!='pending': raise ValueError('Godkjenninga er avslutta.')
            if decision=='reject':
                db.execute('UPDATE minutes_signers SET rejection=? WHERE id=?',(note,row['id']))
                db.execute("UPDATE minutes_reviews SET state='rejected' WHERE id=?",(row['review_id'],))
                return None
            db.execute('UPDATE minutes_signers SET approved_at=? WHERE id=?',(stamp(),row['id']))
            signers=db.execute('SELECT name,approved_at FROM minutes_signers WHERE review_id=? ORDER BY slot',(row['review_id'],)).fetchall()
            if len(signers)!=2 or not all(s['approved_at'] for s in signers): return None
            next_id=db.execute('SELECT COALESCE(MAX(id),0)+1 FROM meeting_publication_queue').fetchone()[0]
            payload=dict(schema_version=1,kind='protokoll',report_year=row['report_year'],status='approved',version_id=f'protokoll-{next_id}',source_revision=row['source_revision'],generated_at=stamp(),content=json.loads(row['snapshot']),approved_by=[dict(s) for s in signers])
            validate_minutes(payload);raw=canonical(payload)
            db.execute('INSERT INTO meeting_publication_queue(payload,content_hash) VALUES (?,?)',(raw,digest(raw)))
            db.execute("UPDATE minutes_reviews SET state='approved' WHERE id=?",(row['review_id'],))
            return payload

    def send_writer(self,meeting_year,name,email,path_prefix=''):
        meeting_year=year(meeting_year)
        name=name.strip();email=email.strip().casefold()
        if not name or len(name)>200 or len(email)>254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',email):
            raise ValueError('Fyll inn namn og gyldig e-post for protokollskrivaren.')
        if not mail_ready(): raise ValueError('E-postsending er ikkje konfigurert.')
        origin=approval_origin()
        self.load(meeting_year)  # Requires an existing agenda or minutes draft.
        token=secrets.token_urlsafe(32);token_hash=digest(token)
        with managed_db(self.get_db) as db:
            db.execute("INSERT INTO minutes_writers(report_year,name,email,token_hash,expires,mail_status) VALUES (?,?,?,?,?,'sending') ON CONFLICT(report_year) DO UPDATE SET name=excluded.name,email=excluded.email,token_hash=excluded.token_hash,expires=excluded.expires,mail_status='sending'",(meeting_year,name,email,token_hash,time.time()+30*86400))
        message=EmailMessage();message['From']=os.environ['STYRE_EPOST_FRA'];message['To']=email
        message['Subject']=f'Før protokoll frå årsmøtet {meeting_year}'
        message.set_content(f'Hei {name}!\n\nDu får tilgang til å føre protokoll for årsmøtet {meeting_year} og sende den til dei to valde protokollunderskrivarane:\n\n{origin}{path_prefix}/protokoll/skriv#{token}\n\nLenkja er personleg og gjeld i 30 dagar. Ikkje del henne vidare. Ho gir berre tilgang til denne protokollen.\n')
        state='sent'
        try: send_message(message)
        except DeliveryUncertain: state='uncertain'
        except Exception: state='failed'
        with managed_db(self.get_db) as db:
            db.execute('UPDATE minutes_writers SET mail_status=? WHERE report_year=? AND token_hash=?',(state,meeting_year,token_hash))
        return state

    def resolve_writer(self,token_hash):
        with managed_db(self.get_db) as db:
            row=db.execute('SELECT * FROM minutes_writers WHERE token_hash=? AND expires>?',(token_hash,time.time())).fetchone()
        if not row: raise ValueError('Skrivetilgangen er utgått eller trekt tilbake. Be styret om ei ny lenkje.')
        return dict(row)

    def publish_pending(self,app,limit=3):
        from publisering import PublicationError
        with managed_db(self.get_db) as db:
            payloads=[json.loads(r['payload']) for r in db.execute("SELECT payload FROM meeting_publication_queue WHERE status IN ('pending','failed','sending','stored') ORDER BY attempts,id")]
        counts=dict(visible=0,stored=0,failed=0,busy=False)
        for payload in [p for p in payloads if p['kind']=='protokoll'][:limit]:
            try: result=app.extensions['document_publisher'].run(target=('meeting',payload['version_id']),limit=1)
            except PublicationError:
                counts['failed']+=1
                continue
            for key in ('visible','stored','failed'): counts[key]+=result[key]
            if result['busy']: counts['busy']=True;break
        return counts


def install_minutes(app,get_db,require_admin):
    service=Minutes(get_db);app.extensions['minutes']=service

    @app.get('/felles/protokoll.css')
    def minutes_styles():
        return send_from_directory(Path(__file__).resolve().parents[1]/'lutar','protokoll.css')

    def location(endpoint,**values): return app.jinja_env.globals['prefix_url'](endpoint,**values)

    @app.route('/sakliste/<int:meeting_year>/protokoll',methods=['GET','POST'])
    def minutes_editor(meeting_year):
        is_admin=app.extensions['styre_auth_valid']()
        if is_admin: actor=session['board_username']
        else:
            try: writer=service.resolve_writer(session.get('minutes_writer',''))
            except ValueError: return require_admin(lambda: None)()
            if writer['report_year']!=meeting_year: abort(403)
            actor='protokollskrivar:'+str(meeting_year)
        if not 1900<=meeting_year<=2200: abort(404)
        try: revision,content=service.load(meeting_year)
        except ValueError as exc: return render_template('protokoll.html',error=str(exc),content=None,meeting_year=meeting_year),400
        error=None;status=200;submitted=None
        writer_status=None
        if is_admin:
            with managed_db(get_db) as db:
                writer_status=db.execute('SELECT name,email,expires,mail_status FROM minutes_writers WHERE report_year=?',(meeting_year,)).fetchone()
        if request.method=='POST':
            try:
                action=request.form.get('action')
                if action=='invite_writer':
                    if not is_admin: abort(403)
                    state=service.send_writer(meeting_year,request.form.get('writer_name',''),request.form.get('writer_email',''),app.jinja_env.globals['url_prefix'])
                    flash('Skrivetilgang: '+{'sent':'personleg lenkje er send.','uncertain':'uvisst om e-posten kom fram. Kontroller med mottakaren før nytt forsøk.','failed':'sendinga feila.'}[state],'protokoll')
                elif action=='revoke_writer':
                    if not is_admin: abort(403)
                    with managed_db(get_db) as db:
                        db.execute('DELETE FROM minutes_writers WHERE report_year=?',(meeting_year,))
                    flash('Skrivetilgangen er trekt tilbake.','protokoll')
                elif action=='review':
                    if request.form.get('confirmed')!='yes': raise ValueError('Kontroller førehandsvisinga og stadfest at protokollen kan publiserast etter godkjenning.')
                    if not mail_ready(): raise ValueError('E-postsending er ikkje konfigurert.')
                    approval_origin()
                    signers=[(request.form.get(f'name_{slot}',''),request.form.get(f'email_{slot}','')) for slot in (1,2)]
                    rid=service.start_review(meeting_year,request.form.get('revision'),signers,actor)
                    states=[service.send_link(rid,slot,app.jinja_env.globals['url_prefix']) for slot in (1,2)]
                    flash('Godkjenningslenkjene er sende.' if states==['sent','sent'] else 'Godkjenningsrunda er oppretta. Sjå e-poststatus nedanfor; ei eller fleire sendingar må kontrollerast.','protokoll')
                elif action=='resend':
                    rid=integer(request.form.get('review_id'));slot=integer(request.form.get('slot'))
                    with managed_db(get_db) as db:
                        if not db.execute('SELECT 1 FROM minutes_reviews WHERE id=? AND report_year=?',(rid,meeting_year)).fetchone(): abort(404)
                    state=service.send_link(rid,slot,app.jinja_env.globals['url_prefix'])
                    flash({'sent':'Ny personleg lenkje er send. Den førre lenkja er ugyldig.','uncertain':'Uvisst om e-posten kom fram. Kontroller med mottakaren før du sender igjen.','failed':'E-postsendinga feila. Prøv igjen når e-postoppsettet er kontrollert.'}[state],'protokoll')
                else:
                    submitted=parse_minutes_form(request.form,content)
                    service.save(meeting_year,request.form.get('revision'),submitted,actor)
                    flash('Protokollen er lagra. Ei eventuell pågåande godkjenningsrunde er avslutta.','protokoll')
                return redirect(location('minutes_editor',meeting_year=meeting_year))
            except ValueError as exc:
                error=str(exc);status=409 if isinstance(exc,DocumentConflict) else 400
                if submitted is not None: content=submitted
                revision=request.form.get('revision',revision)
        with managed_db(get_db) as db:
            reviews=[dict(row) for row in db.execute('SELECT * FROM minutes_reviews WHERE report_year=? ORDER BY id DESC',(meeting_year,))]
            for review in reviews:
                review['signers']=db.execute('SELECT * FROM minutes_signers WHERE review_id=? ORDER BY slot',(review['id'],)).fetchall()
            jobs=[]
            for row in db.execute('SELECT * FROM meeting_publication_queue ORDER BY id DESC'):
                payload=json.loads(row['payload'])
                if payload['kind']=='protokoll' and payload['report_year']==meeting_year: jobs.append(row)
        return render_template('protokoll.html',content=content,revision=revision,meeting_year=meeting_year,error=error,reviews=reviews,jobs=jobs,is_admin=is_admin,writer_status=writer_status,automatic_retry_ready=len(os.environ.get('BYGDELISTA_PUBLICATION_TOKEN',''))>=32),status

    @app.route('/protokoll/skriv',methods=['GET','POST'])
    def minutes_writer_entry():
        error=None
        if request.method=='POST':
            token=request.form.get('token','')
            if not re.fullmatch(r'[A-Za-z0-9_-]{43}',token): abort(404)
            token_hash=digest(token)
            try: writer=service.resolve_writer(token_hash)
            except ValueError as exc: error=str(exc)
            else:
                session['minutes_writer']=token_hash
                return redirect(location('minutes_editor',meeting_year=writer['report_year']))
        response=app.make_response((render_template('protokoll_lenkje.html',error=error,entry='writer'),410 if error else 200))
        response.headers['Referrer-Policy']='no-referrer'
        return response

    @app.route('/protokoll/godkjenn',methods=['GET','POST'])
    def minutes_approval():
        error=None;done=False;row=None;status=200
        if request.method=='POST' and request.form.get('action')=='open':
            token=request.form.get('token','')
            if not re.fullmatch(r'[A-Za-z0-9_-]{43}',token): abort(404)
            token_hash=digest(token)
            try: service.resolve(token_hash)
            except ValueError as exc: return render_template('protokoll_godkjenn.html',error=str(exc),row=None),410
            session['minutes_approval']=token_hash
            return redirect(location('minutes_approval'))
        token_hash=session.get('minutes_approval')
        if token_hash:
            try:
                row=service.resolve(token_hash)
                if request.method=='POST':
                    if not hmac.compare_digest(request.form.get('approval_context','').encode(),token_hash.encode()): raise ValueError('Du har opna ei anna godkjenningslenkje. Last sida på nytt før du vel godkjenning.')
                    decision=request.form.get('decision')
                    if decision=='approve' and request.form.get('confirmed')!='yes': raise ValueError('Stadfest at du har lese protokollen og godkjenner denne kopien.')
                    payload=service.decide(token_hash,decision,request.form.get('note',''))
                    if payload is not None: service.publish_pending(app)
                    done=True
                    # Keep no capability in the browser session after an explicit decision.
                    session.pop('minutes_approval',None)
            except ValueError as exc: error=str(exc);status=400
        elif request.method=='POST': abort(400)
        content=json.loads(row['snapshot']) if row else None
        response=app.make_response((render_template('protokoll_godkjenn.html',row=row,content=content,error=error,done=done),status))
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store'
        return response

    @app.post('/api/protokoll/publiser')
    def minutes_auto_publish():
        expected=os.environ.get('BYGDELISTA_PUBLICATION_TOKEN','')
        supplied=request.headers.get('Authorization','')
        if len(expected)<32 or not hmac.compare_digest(supplied.encode(),('Bearer '+expected).encode()): abort(403)
        return service.publish_pending(app)
