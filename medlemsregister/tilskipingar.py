"""Innlogga skjema for nye tilskipingar i den felles kalenderdatafila."""
import base64
from datetime import date, datetime, timedelta
import json
import hashlib
from zoneinfo import ZoneInfo
import os
import re
import secrets
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler

import certifi
from flask import render_template, request, session
import yaml

FILE_PATH = '_data/kalender.yml'
KINDS = {'pobb':'Folkemusikkpøbb', 'kved':'Kvedarkrok', 'kviss':'Kviss', 'anna':'Anna tilskiping'}
IMAGES = {'/lutar/bilete/arr-cover.png', '/lutar/bilete/gamal-cover.png'}


class CalendarError(RuntimeError):
    pass


class Conflict(CalendarError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_event(values, submission):
    if not re.fullmatch(r'[a-f0-9]{32}',submission):
        raise ValueError('Ugyldig innsending. Last sida på nytt.')
    kind=values.get('kind','')
    if kind not in KINDS:
        raise ValueError('Vel type tilskiping.')
    event={}
    for field,maximum in [('tittel',200),('stad',200),('merknad',3000)]:
        value=values.get(field,'').strip()
        if len(value)>maximum or any(ord(c)<32 and c not in '\n\r\t' for c in value):
            raise ValueError('Kontroller lengda og teikna i tekstfelta.')
        event[field]=value
    if not event['tittel'] or not event['stad']:
        raise ValueError('Tittel og stad er påkravde.')
    try:
        day=date.fromisoformat(values.get('dato',''))
        start=datetime.strptime(values.get('start',''),'%H:%M').time()
        end=datetime.strptime(values.get('slutt',''),'%H:%M').time()
        end_day=date.fromisoformat(values['sluttdato']) if values.get('sluttdato') else day+timedelta(days=end<=start)
        if datetime.combine(end_day,end)<=datetime.combine(day,start):
            raise ValueError()
    except (ValueError,TypeError):
        raise ValueError('Kontroller dato og start-/sluttid. Slutt må vere etter start.') from None
    image=values.get('bilete','/lutar/bilete/arr-cover.png')
    if image not in IMAGES:
        raise ValueError('Vel eit av dei tilgjengelege bileta.')
    link=values.get('lenkje','').strip()
    if link:
        parts=urlsplit(link)
        if any(c.isspace() or ord(c)<32 for c in link) or '\\' in link or not (
            (link.startswith('/') and not link.startswith('//')) or
            (parts.scheme=='https' and parts.hostname and not parts.username and not parts.password)):
            raise ValueError('Lenkja må starte med / eller https://.')
    result={'uid':f'{kind}-{day.year}-{submission}', 'registrering_id':submission,
            'dato':day.isoformat(), 'start':start.strftime('%H:%M'), 'slutt':end.strftime('%H:%M'),
            'tittel':event['tittel'],'stad':event['stad'],'merknad':event['merknad'],'bilete':image}
    if end_day!=day:
        result['sluttdato']=end_day.isoformat()
    if link:
        result['lenkje']=link
    return result


def fingerprint(event):
    return hashlib.sha256(json.dumps(event,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


def editable(event):
    try:
        day=date.fromisoformat(str(event['dato']))
        start=datetime.strptime(str(event.get('start','00:00')),'%H:%M').time()
        end=datetime.strptime(str(event.get('slutt','23:59')),'%H:%M').time()
        last=date.fromisoformat(str(event['sluttdato'])) if event.get('sluttdato') else day+timedelta(days=end<=start)
        return datetime.combine(last,end,ZoneInfo('Europe/Oslo'))>datetime.now(ZoneInfo('Europe/Oslo'))
    except (KeyError,ValueError,TypeError):
        return False


class GithubCalendar:
    def __init__(self, token=None):
        self.token=token or os.environ.get('GITHUB_EVENTS_TOKEN','').strip()
        if not self.token:
            raise CalendarError('Publisering av tilskipingar er ikkje sett opp enno. Kontakt administratoren.')
        self.repo=os.environ.get('GITHUB_EVENTS_REPO','tlauen/oslobygda')
        self.branch=os.environ.get('GITHUB_EVENTS_BRANCH','main')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',self.repo):
            raise CalendarError('Ugyldig kalenderoppsett.')
        self.path=f'https://api.github.com/repos/{self.repo}/contents/{FILE_PATH}'
        self.opener=build_opener(NoRedirect(),HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))

    def api(self, method, body=None):
        url=self.path+('?ref='+quote(self.branch,safe='') if method=='GET' else '')
        req=Request(url,method=method, data=json.dumps(body).encode() if body is not None else None,
                    headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json',
                             'Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28',
                             'User-Agent':'Bygdelista-calendar'})
        try:
            with self.opener.open(req,timeout=20) as response:
                return json.loads(response.read())
        except HTTPError as error:
            status=error.code
            error.close()
            if status==409:
                raise Conflict('Kalenderen vart endra samtidig. Prøv igjen.') from None
            if status in (401,403):
                raise CalendarError('Tilgangen for publisering må kontrollerast av administratoren.') from None
            raise CalendarError(f'Publiseringstenesta svarte med HTTP {status}. Prøv igjen.') from None
        except (URLError,OSError,ValueError):
            raise CalendarError('Kunne ikkje stadfeste publiseringa. Prøv same innsending igjen; ho blir ikkje lagd inn to gonger.') from None

    def read(self):
        try:
            data=self.api('GET')
            raw=base64.b64decode(data['content']).decode('utf-8')
            events=yaml.safe_load(raw)
            if not isinstance(events,list) or not all(isinstance(e,dict) and e.get('uid') for e in events):
                raise ValueError()
            return raw,data['sha'],events
        except (KeyError,TypeError,ValueError,yaml.YAMLError):
            raise CalendarError('Kalenderdataa kunne ikkje lesast. Ingen endringar er lagra.') from None

    def create(self,event):
        for attempt in range(3):
            raw,sha,events=self.read()
            old=next((e for e in events if e.get('registrering_id')==event['registrering_id'] or e['uid']==event['uid']),None)
            if old:
                if old!=event:
                    raise Conflict('Innsendinga er allereie publisert med andre opplysningar. Opne eit nytt skjema.')
                return False
            # Berre legg til: eksisterande kommentarar og formatering vert bevarte.
            updated=raw.rstrip()+'\n\n'+yaml.safe_dump([event],allow_unicode=True,sort_keys=False)
            try:
                self.api('PUT',{'message':'Legg til tilskiping frå Bygdelista', 'branch':self.branch,
                                'sha':sha,'content':base64.b64encode(updated.encode()).decode()})
                return True
            except Conflict:
                if attempt==2:
                    raise


    def update(self,uid,event,expected):
        for attempt in range(3):
            raw,sha,events=self.read()
            matches=[i for i,item in enumerate(events) if item['uid']==uid]
            if len(matches)!=1:
                raise Conflict('Tilskipinga finst ikkje eintydig. Last lista på nytt.')
            index=matches[0]
            old=events[index]
            if not editable(old):
                raise Conflict('Tilskipinga er gjennomført og kan ikkje redigerast her.')
            replacement=dict(old)
            for field in ('dato','start','slutt','tittel','stad','merknad','bilete','sluttdato','lenkje'):
                replacement.pop(field,None)
                if field in event:
                    replacement[field]=event[field]
            if replacement==old:
                return False
            if fingerprint(old)!=expected:
                raise Conflict('Tilskipinga vart endra sidan du opna skjemaet. Opne ho på nytt før du lagrar.')
            # YAML-nodeposisjonar gjer at resten av fila blir ståande urørt.
            nodes=yaml.compose(raw).value
            begin=nodes[index].start_mark.index
            end=nodes[index+1].start_mark.index if index+1<len(nodes) else len(raw)
            begin=raw.rfind('\n',0,begin)+1
            if index+1<len(nodes):
                end=raw.rfind('\n',0,end)+1
            updated=raw[:begin]+yaml.safe_dump([replacement],allow_unicode=True,sort_keys=False)+raw[end:]
            try:
                self.api('PUT',{'message':'Endre tilskiping frå Bygdelista','branch':self.branch,
                                'sha':sha,'content':base64.b64encode(updated.encode()).decode()})
                return True
            except Conflict:
                if attempt==2:
                    raise


def install_calendar(app, require_admin):
    @app.route('/tilskipingar',methods=['GET','POST'])
    @require_admin
    def event_editor():
        key=session.setdefault('calendar_submission',secrets.token_hex(16))
        values={'kind':'pobb','start':'21:00','slutt':'23:45','stad':'Kaffistova, kjellaren'}
        message=error=None
        upcoming=[]
        editing=request.form.get('uid','') if request.method=='POST' else request.args.get('uid','')
        revision=request.form.get('revision','')
        ready=bool(os.environ.get('GITHUB_EVENTS_TOKEN','').strip())
        status=200
        if request.method=='POST':
            values=request.form.to_dict()
            try:
                posted=values.get('submission','')
                if posted not in (key,session.get('last_calendar_submission')):
                    raise ValueError('Ugyldig innsending. Last sida på nytt.')
                event=validate_event(values,posted)
                created=GithubCalendar().update(editing,event,revision) if editing else GithubCalendar().create(event)
                message='Tilskipinga er lagra. Nettsida, kalenderabonnementet og nyhendebrevet brukar no dei same kalenderdataa. Nettsida blir oppdatert når publiseringa er ferdig.' if created else 'Denne tilskipinga er allereie lagra.'
                session['last_calendar_submission']=posted
                session['calendar_submission']=secrets.token_hex(16)
                key=session['calendar_submission']
                values={'kind':'pobb','start':'21:00','slutt':'23:45','stad':'Kaffistova, kjellaren'}
                editing=''
            except ValueError as e:
                error=str(e); status=400
            except CalendarError as e:
                error=str(e); status=409 if isinstance(e,Conflict) else 503
        if ready:
            try:
                _,_,events=GithubCalendar().read()
                upcoming=sorted((e for e in events if editable(e)),key=lambda e:(str(e['dato']),str(e.get('start',''))))
                if editing and request.method=='GET':
                    old=next((e for e in upcoming if e['uid']==editing),None)
                    if old is None:
                        raise Conflict('Tilskipinga kan ikkje redigerast. Vel ei komande tilskiping frå lista.')
                    values=dict(old)
                    values['kind']=next((kind for kind in KINDS if editing.startswith(kind+'-')),'anna')
                    revision=fingerprint(old)
            except CalendarError as e:
                error=error or str(e)
                status=status if status!=200 else 503
        return render_template('tilskipingar.html',upcoming=upcoming,editing=editing,revision=revision,values=values,submission=key,kinds=KINDS,ready=ready,message=message,error=error),status
