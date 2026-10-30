"""Kontrollert publisering av berre validerte offentlege årsdata."""
import base64
import json
import os
import re
import ssl
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPSHandler

import certifi
from arsdokument import canonical,digest,validate_public
from database import managed_db
from offentleg_rekneskap import validate_ledger
from budsjett import validate_budget
from tilskipingar import NoRedirect


class PublicationError(ValueError): pass
class PublicationConflict(PublicationError): pass


def validate_document(value):
    if not isinstance(value,dict): raise PublicationError('Ugyldig offentleg dokument.')
    try:
        if value.get('kind')=='rekneskap': validate_ledger(value)
        elif value.get('kind')=='budsjett': validate_budget(value)
        else: validate_public(value)
    except (ValueError,TypeError,KeyError,OverflowError): raise PublicationError('Offentleg dokument har ugyldige felt eller summer.') from None


def validate_envelope(value,year):
    if not isinstance(value,dict) or set(value)!={'schema_version','year','versions','ledger_latest'} or value['schema_version']!=1 or type(value['year']) is not int or value['year']!=year or not isinstance(value['versions'],list):
        raise PublicationError('Årsfila har ukjent format; ingen endringar blir skrivne.')
    identities=set()
    for doc in value['versions']:
        validate_document(doc)
        identity=(doc['kind'],doc['version_id'])
        if doc['report_year']!=year or doc['status'] not in ('meeting','approved') or identity in identities:
            raise PublicationError('Ugyldig eller duplisert dokumentversjon.')
        identities.add(identity)
    if value['ledger_latest'] is not None:
        validate_document(value['ledger_latest'])
        if value['ledger_latest']['kind']!='rekneskap' or value['ledger_latest']['report_year']!=year or value['ledger_latest']['status']!='provisional':
            raise PublicationError('Ugyldige løpande tal.')


class GithubDocuments:
    def __init__(self):
        self.token=os.environ.get('GITHUB_DOCUMENTS_TOKEN','').strip()
        self.repo=os.environ.get('GITHUB_DOCUMENTS_REPO','tlauen/oslobygda')
        self.branch=os.environ.get('GITHUB_DOCUMENTS_BRANCH','main')
        self.public_base=os.environ.get('PUBLIC_DOCUMENTS_BASE_URL','https://oslobygda.no').rstrip('/')
        if not self.token: raise PublicationError('Dokumentpublisering er ikkje konfigurert. Ingen nettverkskall er utførte.')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',self.repo) or not re.fullmatch(r'[A-Za-z0-9_./-]+',self.branch):
            raise PublicationError('Ugyldig GitHub-oppsett.')
        if not re.fullmatch(r'https://[A-Za-z0-9.-]+(?::[0-9]+)?(?:/[A-Za-z0-9_./-]*)?',self.public_base):
            raise PublicationError('Offentleg adresse må vere ei fast HTTPS-adresse.')
        self.opener=build_opener(NoRedirect(),HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))

    def api(self,method,path,body=None):
        url=f'https://api.github.com/repos/{self.repo}/contents/{path}'
        if method=='GET': url+='?ref='+quote(self.branch,safe='')
        request=Request(url,method=method,data=canonical(body).encode() if body is not None else None,
                        headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json',
                                 'Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'Bygdelista-documents'})
        try:
            with self.opener.open(request,timeout=20) as response:
                raw=response.read(4*1024*1024+1)
                if len(raw)>4*1024*1024: raise PublicationError('Publiseringsfila er for stor.')
                return json.loads(raw)
        except HTTPError as exc:
            status=exc.code;exc.close()
            if status==404 and method=='GET': return None
            if status in (409,422): raise PublicationConflict('Samtidig endring i GitHub. Nytt forsøk trengst.') from None
            raise PublicationError(f'GitHub svarte med HTTP {status}. Kontroller tilgang og køstatus.') from None
        except (URLError,OSError,ValueError) as exc:
            if isinstance(exc,PublicationError): raise
            raise PublicationError('Kunne ikkje stadfeste GitHub-svaret. Same jobb kan prøvast igjen.') from None

    def read(self,year):
        result=self.api('GET',f'_data/arsdokument/{year}.json')
        if result is None: return dict(schema_version=1,year=year,versions=[],ledger_latest=None),None
        try: data=json.loads(base64.b64decode(result['content'],validate=False).decode())
        except (ValueError,KeyError,TypeError): raise PublicationError('Årsfila kunne ikkje lesast.') from None
        validate_envelope(data,year)
        return data,result['sha']

    @staticmethod
    def contains(envelope,payload):
        if payload['status']=='provisional':
            old=envelope['ledger_latest']
            if old and old['source_revision']>payload['source_revision']: return True
            if old and old['source_revision']==payload['source_revision']:
                # Daily snapshots can advance cutoff without a ledger write.
                if old['as_of']>payload['as_of']: return True
                if old['as_of']==payload['as_of']:
                    if old['version_id']==payload['version_id'] and canonical(old)!=canonical(payload):
                        raise PublicationError('Versjonsidentiteten har ulikt innhald.')
                    if int(old['version_id'].split('-')[-1])>int(payload['version_id'].split('-')[-1]): return True
            return old==payload
        for old in envelope['versions']:
            if (old['kind'],old['version_id'])==(payload['kind'],payload['version_id']):
                if canonical(old)!=canonical(payload): raise PublicationError('Ein fast versjon har ulikt innhald i GitHub.')
                return True
        if payload['kind']=='arsmelding':
            reports=[v for v in envelope['versions'] if v['kind']=='arsmelding']
            if reports:
                current=max(reports,key=lambda v:(v['status']=='approved',v['version_id']))
                if (current['status']=='approved',current['version_id'])>(payload['status']=='approved',payload['version_id']): return True
        return False

    def store(self,payload,guard=lambda:None):
        validate_document(payload);year=payload['report_year']
        # Publishing is restricted to years with deployed page stubs.
        stub={'rekneskap':'rekneskap','arsmelding':'arsmeldingar','budsjett':'budsjett'}[payload['kind']]
        if self.api('GET',f'om/{stub}/{year}/index.md') is None or self.api('GET',f'api/arsdokument/{year}.json') is None:
            raise PublicationError('Årssida er ikkje klargjord i GitHub. Publiser sidestubben før data.')
        for attempt in range(3):
            guard()
            envelope,sha=self.read(year)
            before=canonical(envelope)
            present=self.contains(envelope,payload)
            if not present:
                if payload['status']=='provisional': envelope['ledger_latest']=payload
                else: envelope['versions'].append(payload)
            if payload['kind']=='arsmelding':
                reports=[v for v in envelope['versions'] if v['kind']=='arsmelding']
                if reports:
                    current=max(reports,key=lambda v:(v['status']=='approved',v['version_id']))
                    envelope['versions']=[v for v in envelope['versions'] if v['kind']!='arsmelding']+[current]
            if canonical(envelope)==before: return sha or ''
            validate_envelope(envelope,year)
            body={'branch':self.branch,'message':f'Oppdater offentlege årsdokument {year}',
                  'content':base64.b64encode(canonical(envelope).encode()).decode()}
            if sha: body['sha']=sha
            guard()
            try: self.api('PUT',f'_data/arsdokument/{year}.json',body)
            except PublicationConflict:
                if attempt==2: raise
                continue
            # Also read after successful/uncertain write; never infer completion solely from a PUT.
            guard();stored,sha=self.read(year)
            if self.contains(stored,payload): return sha or ''
        raise PublicationError('Publiseringa kunne ikkje stadfestast.')

    def visible(self,payload):
        """Public JSON is built alongside HTML; do not send credentials to the public host."""
        url=f'{self.public_base}/api/arsdokument/{payload["report_year"]}.json'
        try:
            request=Request(url,headers={'Cache-Control':'no-cache','User-Agent':'Bygdelista-documents'})
            with self.opener.open(request,timeout=20) as response:
                raw=response.read(4*1024*1024+1)
                if len(raw)>4*1024*1024: return False
                envelope=json.loads(raw)
            validate_envelope(envelope,payload['report_year'])
            return self.contains(envelope,payload)
        except (HTTPError,URLError,OSError,ValueError,TypeError): return False


class Publisher:
    def __init__(self,get_db,public_ledger): self.get_db=get_db;self.public_ledger=public_ledger

    def run(self,client=None,limit=20,target=None):
        # Missing credentials are detected before snapshots or queue states change.
        client=client or GithubDocuments()
        owner=uuid.uuid4().hex
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('UPDATE publication_worker SET owner=?,expires=? WHERE id=1 AND expires<?',
                              (owner,time.time()+120,time.time())).rowcount:
                return {'busy':True,'stored':0,'visible':0,'failed':0}
        def guard():
            with managed_db(self.get_db) as db:
                if not db.execute('UPDATE publication_worker SET expires=? WHERE id=1 AND owner=? AND expires>?',
                                  (time.time()+120,owner,time.time())).rowcount:
                    raise PublicationError('Publiseringslåsen er utgått. Avbryt og prøv same jobb igjen.')
        counts=dict(busy=False,stored=0,visible=0,failed=0)
        try:
            if target is None: self.public_ledger.refresh_enabled()
            with managed_db(self.get_db) as db:
                jobs=[('ledger',r['id'],r['payload'],r['content_hash'],r['status']) for r in db.execute('''SELECT v.id,v.payload,v.content_hash,q.status FROM public_ledger_versions v
                    JOIN public_ledger_queue q ON q.version_id=v.id WHERE q.status IN ('pending','failed','sending','stored') ORDER BY v.id''')]
                jobs += [('annual',r['id'],r['payload'],r['content_hash'],r['status']) for r in db.execute("SELECT * FROM annual_publication_queue WHERE status IN ('pending','failed','sending','stored') ORDER BY id")]
                jobs += [('budget',r['id'],r['payload'],r['content_hash'],r['status']) for r in db.execute("SELECT * FROM budget_publication_queue WHERE status IN ('pending','failed','sending','stored') ORDER BY id")]
            if target is not None:
                jobs=[job for job in jobs if job[0]==target[0] and json.loads(job[2])['version_id']==target[1]]
            jobs.sort(key=lambda job: (job[4]=='stored',job[1],job[0]))
            for kind,job_id,raw,hash_value,state in jobs[:limit]:
                guard()
                table={'ledger':'public_ledger_queue','annual':'annual_publication_queue','budget':'budget_publication_queue'}[kind]
                key='version_id' if kind=='ledger' else 'id'
                try:
                    if digest(raw)!=hash_value: raise PublicationError('Køinnhaldet har feil kontrollsum.')
                    payload=json.loads(raw);validate_document(payload)
                    # A newer coalesced provisional job may have superseded the fetched row.
                    with managed_db(self.get_db) as db:
                        current=db.execute(f'SELECT status FROM {table} WHERE {key}=?',(job_id,)).fetchone()[0]
                        if current=='superseded': continue
                        db.execute(f"UPDATE {table} SET status='sending',attempts=attempts+1 WHERE {key}=?",(job_id,))
                    def job_guard():
                        guard()
                        with managed_db(self.get_db) as db:
                            if db.execute(f'SELECT status FROM {table} WHERE {key}=?',(job_id,)).fetchone()[0]=='superseded':
                                raise PublicationError('Jobben er erstatta eller stansa.')
                    commit=client.store(payload,job_guard)
                    is_visible=client.visible(payload)
                    guard()
                    with managed_db(self.get_db) as db:
                        # Do not overwrite superseding status written by a newer capture.
                        db.execute(f"UPDATE {table} SET status=?,last_error='' WHERE {key}=? AND status!='superseded'",('visible' if is_visible else 'stored',job_id))
                        if kind=='ledger': db.execute('UPDATE public_ledger_queue SET stored_commit=? WHERE version_id=?',(commit,job_id))
                    counts['visible' if is_visible else 'stored']+=1
                except (PublicationError,ValueError,TypeError,KeyError) as exc:
                    guard()
                    with managed_db(self.get_db) as db:
                        db.execute(f"UPDATE {table} SET status='failed',last_error=? WHERE {key}=? AND status!='superseded'",(str(exc)[:500],job_id))
                    counts['failed']+=1
            return counts
        finally:
            with managed_db(self.get_db) as db:
                db.execute('UPDATE publication_worker SET owner=NULL,expires=0 WHERE id=1 AND owner=?',(owner,))


def publish_from_button(app,target):
    """Overfør berre dokumentet brukaren valde; bevar køa ved feil."""
    from flask import flash
    try:
        result=app.extensions['document_publisher'].run(target=target,limit=1)
        if result['busy']: message='Ei anna publisering pågår. Prøv igjen om litt.'
        elif result['failed']: message='Sendinga feila. Sjå køstatus og prøv igjen.'
        elif result['visible']: message='Dokumentet er stadfesta synleg på nettsida.'
        elif result['stored']: message='Dokumentet er sendt til GitHub. Nettsida blir oppdatert når bygginga er ferdig.'
        else: message='Ingen ny overføring var nødvendig. Sjå publiseringsstatusen.'
    except PublicationError as exc: message=str(exc)
    flash(message,'publisering')
