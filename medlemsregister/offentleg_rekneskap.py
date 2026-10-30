"""Avgrensa offentleg rekneskapseksport. Ingen medlems- eller bilagsdata."""
from datetime import date, timedelta
import json
import re
import uuid

from arsdokument import canonical, digest, stamp, today
from database import managed_db
from rekneskap import ACCOUNTS, balances

BALANCE_ACCOUNTS = [code for code,(_,kind) in ACCOUNTS.items() if kind in ('asset','liability')]


def init_public_ledger(get_db):
    with managed_db(get_db) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS public_ledger_settings (
          year INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0,
          actor TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS public_ledger_refs (journal_id INTEGER PRIMARY KEY, public_ref TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS public_ledger_versions (
          id INTEGER PRIMARY KEY, year INTEGER NOT NULL, status TEXT NOT NULL,
          payload TEXT NOT NULL DEFAULT '', content_hash TEXT NOT NULL DEFAULT '',
          actor TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS public_ledger_queue (
          version_id INTEGER PRIMARY KEY REFERENCES public_ledger_versions(id),
          status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
          last_error TEXT NOT NULL DEFAULT '', stored_commit TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS publication_worker (
          id INTEGER PRIMARY KEY CHECK(id=1), owner TEXT, expires REAL NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO publication_worker(id) VALUES (1);
        CREATE TABLE IF NOT EXISTS public_ledger_clock (id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL);
        INSERT OR IGNORE INTO public_ledger_clock(id,revision) VALUES (1,0);
        CREATE TRIGGER IF NOT EXISTS public_ledger_version_immutable_update
        BEFORE UPDATE ON public_ledger_versions WHEN OLD.payload!=''
        BEGIN SELECT RAISE(ABORT,'Offentleg versjon er fast'); END;
        CREATE TRIGGER IF NOT EXISTS public_ledger_version_immutable_delete BEFORE DELETE ON public_ledger_versions
        BEGIN SELECT RAISE(ABORT,'Offentleg versjon er fast'); END;
        ''')
        for table in ('ledger_journals','ledger_reconciliations','ledger_year_events'):
            # A durable revision also tracks reconciliation and year-status changes.
            db.execute(f'''CREATE TRIGGER IF NOT EXISTS public_clock_{table} AFTER INSERT ON {table}
              BEGIN UPDATE public_ledger_clock SET revision=revision+1 WHERE id=1; END''')


def balance_section(amounts):
    result=[]
    for account in BALANCE_ACCOUNTS:
        amount=amounts.get(account,0)
        result.append(dict(category=account,label=ACCOUNTS[account][0],kind=ACCOUNTS[account][1],
                           amount_ore=-amount if ACCOUNTS[account][1]=='liability' else amount))
    assets=sum(row['amount_ore'] for row in result if row['kind']=='asset')
    liabilities=sum(row['amount_ore'] for row in result if row['kind']=='liability')
    return dict(items=result,assets_ore=assets,liabilities_ore=liabilities,equity_ore=assets-liabilities)


def snapshot(db,year,version_id,status='provisional',meeting_year=None,decision_date=None):
    if type(year) is not int or not 1900<=year<=today().year: raise ValueError('Vel eit påbyrja rekneskapsår.')
    cutoff=min(today(),date(year,12,31))
    first=date(year,1,1)
    journals=db.execute("SELECT * FROM ledger_journals WHERE state='posted' AND day BETWEEN ? AND ? ORDER BY day,id",(first.isoformat(),cutoff.isoformat())).fetchall()
    totals={};transactions=[];membership=0
    for journal in journals:
        rows=db.execute('SELECT account,amount_ore FROM ledger_lines WHERE journal_id=?',(journal['id'],)).fetchall()
        # Membership stays aggregated, including corrections and refunds.
        has_membership=any(r['account']=='membership' for r in rows)
        meaningful=[]
        for row in rows:
            account=row['account'];kind=ACCOUNTS[account][1];amount=row['amount_ore']
            if kind not in ('income','expense'): continue
            amount=-amount if kind=='income' else amount
            totals[account]=totals.get(account,0)+amount
            if account=='membership': membership+=amount
            else: meaningful.append((account,kind,amount))
        if not meaningful and has_membership: continue
        ref=db.execute('SELECT public_ref FROM public_ledger_refs WHERE journal_id=?',(journal['id'],)).fetchone()
        if not ref:
            value='B-'+uuid.uuid4().hex[:16]
            db.execute('INSERT INTO public_ledger_refs(journal_id,public_ref) VALUES (?,?)',(journal['id'],value))
            ref=(value,)
        description='Retting av tidlegare post' if journal['reversal_of'] else journal['public_text']
        if meaningful:
            for account,kind,amount in meaningful:
                transactions.append(dict(date=journal['day'],public_ref=ref[0],kind=kind,category=account,
                                         label=ACCOUNTS[account][0],description=description,amount_ore=amount))
        else:
            # Non-result transactions are shown separately and never counted as new income.
            money=sum(row['amount_ore'] for row in rows if row['account']=='bank')
            if journal['source_kind'] in ('opening','opening_adjustment'): money=0
            transactions.append(dict(date=journal['day'],public_ref=ref[0],kind='settlement',category='settlement',
                                     label='Overføring, oppgjer eller balanseføring',description=description,amount_ore=money))
    categories=[dict(category=account,label=ACCOUNTS[account][0],kind=ACCOUNTS[account][1],amount_ore=totals.get(account,0))
                for account in ACCOUNTS if ACCOUNTS[account][1] in ('income','expense')]
    income=sum(r['amount_ore'] for r in categories if r['kind']=='income')
    expense=sum(r['amount_ore'] for r in categories if r['kind']=='expense')
    opening=balances(db,(first-timedelta(days=1)).isoformat())
    # Documented initial balances are dated Jan 1 but belong to the opening position.
    for row in db.execute('''SELECT l.account,SUM(l.amount_ore) amount FROM ledger_lines l
        JOIN ledger_journals j ON j.id=l.journal_id WHERE j.state='posted' AND j.day=?
        AND j.source_kind IN ('opening','opening_adjustment') GROUP BY l.account''',(first.isoformat(),)):
        opening[row['account']]=opening.get(row['account'],0)+row['amount']
    ending=balances(db,cutoff.isoformat())
    year_row=db.execute('SELECT closed FROM ledger_years WHERE year=?',(year,)).fetchone()
    reconciled=bool(year_row and year_row[0] and cutoff==date(year,12,31))
    revision=db.execute('SELECT revision FROM public_ledger_clock WHERE id=1').fetchone()[0]
    value=dict(schema_version=1,kind='rekneskap',version_id=version_id,snapshot_number=0 if version_id=='preview' else int(version_id.split('-')[-1]),report_year=year,meeting_year=meeting_year,
               status=status,decision_date=decision_date,generated_at=stamp(),as_of=cutoff.isoformat(),
               source_revision=revision,reconciled=reconciled,membership_ore=membership,categories=categories,
               transactions=transactions,income_ore=income,expense_ore=expense,result_ore=income-expense,
               opening=balance_section(opening),ending=balance_section(ending),
               principle='Medlemskontingent er inntekt på betalingsdato. Private utlegg gir gjeld fram til refusjon. Abonnement blir fordelte på tenesteåra.')
    validate_ledger(value,allow_preview=version_id=='preview')
    return value


def validate_ledger(value,allow_preview=False):
    expected={'schema_version','kind','version_id','snapshot_number','report_year','meeting_year','status','decision_date','generated_at','as_of',
              'source_revision','reconciled','membership_ore','categories','transactions','income_ore','expense_ore',
              'result_ore','opening','ending','principle'}
    def exact(obj,keys):
        if not isinstance(obj,dict) or set(obj)!=keys: raise ValueError('Ugyldige offentlege rekneskapsfelt.')
    def number(n):
        if type(n) is not int or abs(n)>10**16: raise ValueError('Ugyldig offentleg tal.')
    def text(s,limit=2000):
        if not isinstance(s,str) or len(s)>limit: raise ValueError('Ugyldig offentleg tekst.')
    exact(value,expected)
    if value['schema_version']!=1 or value['kind']!='rekneskap': raise ValueError('Ugyldig eksporttype.')
    if not isinstance(value['version_id'],str) or not (re.fullmatch(r'rekneskap-[1-9][0-9]*',value['version_id']) or (allow_preview and value['version_id']=='preview')):
        raise ValueError('Ugyldig versjons-ID.')
    number(value['snapshot_number'])
    if value['snapshot_number'] != (0 if value['version_id']=='preview' else int(value['version_id'].split('-')[-1])): raise ValueError('Versjonsnummeret stemmer ikkje.')
    year=value['report_year']
    if type(year) is not int or not 1900<=year<=2200: raise ValueError('Ugyldig år.')
    if value['status'] not in ('provisional','meeting','approved'): raise ValueError('Ugyldig status.')
    if type(value['reconciled']) is not bool: raise ValueError('Ugyldig avstemmingsstatus.')
    day=date.fromisoformat(value['as_of'])
    if day.year!=year: raise ValueError('Rapportdato er i feil år.')
    from datetime import datetime
    datetime.fromisoformat(value['generated_at'])
    if value['status']=='provisional':
        if value['decision_date'] is not None or value['meeting_year'] is not None: raise ValueError('Førebels rapport har ikkje vedtak.')
    else:
        if type(value['meeting_year']) is not int or not 1900<=value['meeting_year']<=2200 or not value['reconciled'] or value['as_of']!=f'{year}-12-31':
            raise ValueError('Fast årsrekneskap må vere avstemt ved årsslutt.')
        if value['status']=='approved': date.fromisoformat(value['decision_date'])
        elif value['decision_date'] is not None: raise ValueError('Framlegg skal ikkje ha vedtaksdato.')
    for key in ('source_revision','membership_ore','income_ore','expense_ore','result_ore'): number(value[key])
    text(value['principle'])
    if not isinstance(value['categories'],list) or not isinstance(value['transactions'],list): raise ValueError('Ugyldige lister.')
    seen=set();totals={}
    for row in value['categories']:
        exact(row,{'category','label','kind','amount_ore'})
        code=row['category']
        if code not in ACCOUNTS or ACCOUNTS[code][1] not in ('income','expense') or code in seen: raise ValueError('Ugyldig kategori.')
        if (row['label'],row['kind'])!=ACCOUNTS[code]: raise ValueError('Ugyldig kategorinamn.')
        seen.add(code);number(row['amount_ore']);totals[code]=row['amount_ore']
    if seen!={k for k,v in ACCOUNTS.items() if v[1] in ('income','expense')}: raise ValueError('Manglande kategoriar.')
    detail_totals={}
    for row in value['transactions']:
        exact(row,{'date','public_ref','kind','category','label','description','amount_ore'})
        date.fromisoformat(row['date']);text(row['description'],500);text(row['label'],200);number(row['amount_ore'])
        if not f'{year}-01-01'<=row['date']<=value['as_of']: raise ValueError('Transaksjon utanfor rapportperioden.')
        if not isinstance(row['public_ref'],str) or not re.fullmatch(r'B-[a-f0-9]{16}',row['public_ref']): raise ValueError('Ugyldig offentleg bilagsnummer.')
        if row['kind']=='settlement':
            if row['category']!='settlement': raise ValueError('Ugyldig oppgjer.')
        else:
            if row['category']=='membership' or row['category'] not in totals or row['kind']!=ACCOUNTS[row['category']][1]:
                raise ValueError('Medlemsbetalingar kan ikkje visast enkeltvis.')
            if row['label']!=ACCOUNTS[row['category']][0]: raise ValueError('Ugyldig etikett.')
            detail_totals[row['category']]=detail_totals.get(row['category'],0)+row['amount_ore']
    for code,amount in totals.items():
        if code!='membership' and amount!=detail_totals.get(code,0): raise ValueError('Detaljane summerer ikkje til kategorien.')
    if totals['membership']!=value['membership_ore']: raise ValueError('Kontingentsummen stemmer ikkje.')
    income=sum(n for code,n in totals.items() if ACCOUNTS[code][1]=='income')
    expense=sum(n for code,n in totals.items() if ACCOUNTS[code][1]=='expense')
    if (income,expense,income-expense)!=(value['income_ore'],value['expense_ore'],value['result_ore']): raise ValueError('Resultatsummane stemmer ikkje.')
    for name in ('opening','ending'):
        section=value[name];exact(section,{'items','assets_ore','liabilities_ore','equity_ore'})
        if not isinstance(section['items'],list): raise ValueError('Ugyldig balanse.')
        codes=set();a=0;l=0
        for row in section['items']:
            exact(row,{'category','label','kind','amount_ore'});code=row['category']
            if code not in BALANCE_ACCOUNTS or code in codes or (row['label'],row['kind'])!=ACCOUNTS[code]: raise ValueError('Ugyldig balansekategori.')
            codes.add(code);number(row['amount_ore'])
            if row['kind']=='asset': a+=row['amount_ore']
            else: l+=row['amount_ore']
        if codes!=set(BALANCE_ACCOUNTS): raise ValueError('Manglande balansekontoar.')
        for key in ('assets_ore','liabilities_ore','equity_ore'): number(section[key])
        if (a,l,a-l)!=(section['assets_ore'],section['liabilities_ore'],section['equity_ore']): raise ValueError('Balansen stemmer ikkje.')
    if value['ending']['equity_ore']-value['opening']['equity_ore']!=value['result_ore']:
        raise ValueError('Endring i eigenkapital stemmer ikkje med resultatet.')


class PublicLedger:
    def __init__(self,get_db): self.get_db=get_db

    def preview(self,year):
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            return snapshot(db,year,'preview')

    def _capture(self,db,year,actor,status='provisional',meeting_year=None,decision_date=None):
        vid=db.execute('INSERT INTO public_ledger_versions(year,status,actor,created_at) VALUES (?,?,?,?)',(year,status,actor,stamp())).lastrowid
        payload=snapshot(db,year,'rekneskap-'+str(vid),status,meeting_year,decision_date)
        raw=canonical(payload)
        db.execute('UPDATE public_ledger_versions SET payload=?,content_hash=? WHERE id=?',(raw,digest(raw),vid))
        if status=='provisional':
            db.execute("UPDATE public_ledger_queue SET status='superseded' WHERE status!='superseded' AND version_id IN (SELECT id FROM public_ledger_versions WHERE year=? AND status='provisional')",(year,))
        db.execute('INSERT INTO public_ledger_queue(version_id) VALUES (?)',(vid,))
        return vid

    def activate(self,year,actor,expected_revision):
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            revision=db.execute('SELECT revision FROM public_ledger_clock WHERE id=1').fetchone()[0]
            if revision!=int(expected_revision): raise ValueError('Rekneskapen er endra. Sjå førehandsvisinga på nytt før aktivering.')
            db.execute('INSERT INTO public_ledger_settings(year,enabled,actor,updated_at) VALUES (?,1,?,?) ON CONFLICT(year) DO UPDATE SET enabled=1,actor=excluded.actor,updated_at=excluded.updated_at',(year,actor,stamp()))
            return self._capture(db,year,actor)

    def refresh_enabled(self,actor='vedlikehald'):
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            revision=db.execute('SELECT revision FROM public_ledger_clock WHERE id=1').fetchone()[0]
            settings=db.execute('SELECT year FROM public_ledger_settings WHERE enabled=1').fetchall()
            count=0
            for setting in settings:
                year=setting[0]
                old=db.execute("SELECT payload FROM public_ledger_versions WHERE year=? AND status='provisional' ORDER BY id DESC LIMIT 1",(year,)).fetchone()
                if old:
                    value=json.loads(old[0]);cutoff=min(today(),date(year,12,31)).isoformat()
                    if value['source_revision']==revision and value['as_of']==cutoff: continue
                self._capture(db,year,actor);count+=1
            return count

    def freeze(self,year,status,meeting_year,decision_date,actor,expected_revision):
        if status not in ('meeting','approved'): raise ValueError('Vel framlegg eller godkjend versjon.')
        if status=='approved':
            decision_date=date.fromisoformat(decision_date).isoformat()
            if decision_date>today().isoformat() or decision_date<f'{year+1}-01-01': raise ValueError('Vedtaksdato må vere etter rapportåret og ikkje i framtida.')
        else: decision_date=None
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            revision=db.execute('SELECT revision FROM public_ledger_clock WHERE id=1').fetchone()[0]
            if revision!=int(expected_revision): raise ValueError('Rekneskapen er endra. Kontroller ny førehandsvising.')
            if not db.execute('SELECT 1 FROM ledger_years WHERE year=? AND closed=1',(year,)).fetchone(): raise ValueError('Avstem og avslutt rekneskapsåret før ein fast versjon blir lagra.')
            from arsavslutning import closing_checklist
            if not closing_checklist(db,year)['ready']: raise ValueError('Saldokontrollane er ikkje ferdige. Opne Avstemming og årsslutt og rett punkta som står att.')
            for row in db.execute('SELECT id,payload FROM public_ledger_versions WHERE year=? AND status=?',(year,status)):
                old=json.loads(row['payload'])
                if old['source_revision']==revision and old['decision_date']==decision_date and old['meeting_year']==int(meeting_year): return row['id']
            return self._capture(db,year,actor,status,int(meeting_year),decision_date)
