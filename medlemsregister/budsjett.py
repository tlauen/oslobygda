"""Budsjett med same kategoriar som rekneskapen og faste vedtaksversjonar."""
from datetime import date
import json
import re

from arsdokument import canonical,digest,stamp,today,year,DocumentConflict
from database import managed_db
from rekneskap import ACCOUNTS,ore

CATEGORIES = [code for code,details in ACCOUNTS.items() if details[1] in ('income','expense')]


def init_budgets(get_db):
    with managed_db(get_db) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS budgets (
          year INTEGER PRIMARY KEY, revision INTEGER NOT NULL DEFAULT 1,
          content TEXT NOT NULL, actor TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS budget_edits (
          year INTEGER NOT NULL, revision INTEGER NOT NULL, content TEXT NOT NULL,
          actor TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(year,revision)
        );
        CREATE TABLE IF NOT EXISTS budget_versions (
          id INTEGER PRIMARY KEY, year INTEGER NOT NULL REFERENCES budgets(year),
          source_revision INTEGER NOT NULL, status TEXT NOT NULL, decision_date TEXT,
          payload TEXT NOT NULL DEFAULT '', content_hash TEXT NOT NULL DEFAULT '',
          actor TEXT NOT NULL, created_at TEXT NOT NULL,
          UNIQUE(year,source_revision,status)
        );
        CREATE TABLE IF NOT EXISTS budget_publication_queue (
          id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL UNIQUE REFERENCES budget_versions(id),
          payload TEXT NOT NULL, content_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
          attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT NOT NULL DEFAULT '',
          created_by TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TRIGGER IF NOT EXISTS budget_version_no_update BEFORE UPDATE ON budget_versions WHEN OLD.payload!=''
        BEGIN SELECT RAISE(ABORT,'Budsjettversjonen er fast'); END;
        CREATE TRIGGER IF NOT EXISTS budget_version_no_delete BEFORE DELETE ON budget_versions
        BEGIN SELECT RAISE(ABORT,'Budsjettversjonen er fast'); END;
        CREATE TRIGGER IF NOT EXISTS budget_queue_payload_fixed BEFORE UPDATE OF version_id,payload,content_hash ON budget_publication_queue
        BEGIN SELECT RAISE(ABORT,'Publiseringsinnhaldet er fast'); END;
        ''')
        for operation in ('UPDATE','DELETE'):
            db.execute(f'''CREATE TRIGGER IF NOT EXISTS budget_edits_no_{operation.lower()} BEFORE {operation} ON budget_edits
              BEGIN SELECT RAISE(ABORT,'Budsjetthistorikken er fast'); END''')


def actuals(db,report_year,cutoff):
    totals=dict(db.execute('''SELECT l.account,SUM(l.amount_ore) FROM ledger_lines l
        JOIN ledger_journals j ON j.id=l.journal_id WHERE j.state='posted' AND j.day BETWEEN ? AND ?
        GROUP BY l.account''',(f'{report_year}-01-01',cutoff)).fetchall())
    return {code:-totals.get(code,0) if ACCOUNTS[code][1]=='income' else totals.get(code,0) for code in CATEGORIES}


def previous(db,budget_year):
    prior=budget_year-1
    cutoff=min(today().isoformat(),f'{prior}-12-31')
    values=actuals(db,prior,cutoff)
    started=db.execute('SELECT 1 FROM ledger_years WHERE opening_confirmed=1 AND year<=?',(prior,)).fetchone()
    closed=db.execute('SELECT closed FROM ledger_years WHERE year=?',(prior,)).fetchone()
    return dict(year=prior,as_of=cutoff,state='not_started' if not started or today().year<prior else ('closed' if closed and closed[0] and cutoff==f'{prior}-12-31' else 'provisional'),
                captured_at=stamp(),amounts=values)


def totals(lines):
    income=sum(line['amount_ore'] for line in lines if line['kind']=='income')
    expense=sum(line['amount_ore'] for line in lines if line['kind']=='expense')
    return income,expense,income-expense


def public_budget(content,year_value,revision,version_id,status,decision_date):
    lines=[dict(category=code,label=ACCOUNTS[code][0],kind=ACCOUNTS[code][1],amount_ore=content['amounts'].get(code,0),
                previous_ore=content['previous']['amounts'].get(code,0)) for code in CATEGORIES]
    income,expense,result=totals(lines)
    prior=content['previous']
    prior_income=sum(line['previous_ore'] for line in lines if line['kind']=='income')
    prior_expense=sum(line['previous_ore'] for line in lines if line['kind']=='expense')
    value=dict(schema_version=1,kind='budsjett',version_id=version_id,snapshot_number=int(version_id.split('-')[-1]),
               report_year=year_value,meeting_year=content['meeting_year'],source_revision=revision,status=status,
               decision_date=decision_date,title=content['title'],note=content['note'],lines=lines,
               income_ore=income,expense_ore=expense,result_ore=result,previous_income_ore=prior_income,previous_expense_ore=prior_expense,previous_result_ore=prior_income-prior_expense,
               previous_year=prior['year'],previous_as_of=prior['as_of'],previous_state=prior['state'],
               previous_captured_at=prior['captured_at'])
    validate_budget(value)
    return value


def validate_budget(value):
    fields={'schema_version','kind','version_id','snapshot_number','report_year','meeting_year','source_revision','status',
            'decision_date','title','note','lines','income_ore','expense_ore','result_ore','previous_income_ore','previous_expense_ore','previous_result_ore','previous_year','previous_as_of',
            'previous_state','previous_captured_at'}
    if not isinstance(value,dict) or set(value)!=fields or type(value['schema_version']) is not int or value['schema_version']!=1 or value['kind']!='budsjett':
        raise ValueError('Ugyldige offentlege budsjettfelt.')
    if not isinstance(value['version_id'],str) or not re.fullmatch(r'budsjett-[1-9][0-9]*',value['version_id']): raise ValueError('Ugyldig budsjettversjon.')
    for key in ('snapshot_number','report_year','meeting_year','source_revision','previous_year'):
        if type(value[key]) is not int: raise ValueError('Ugyldig heiltal.')
    if value['snapshot_number']!=int(value['version_id'].split('-')[-1]) or value['source_revision']<1: raise ValueError('Ugyldig revisjon.')
    if not 1901<=value['report_year']<=2200 or not 1900<=value['meeting_year']<=2200 or value['previous_year']!=value['report_year']-1:
        raise ValueError('Ugyldige årstal.')
    if value['status'] not in ('meeting','approved'): raise ValueError('Ugyldig budsjettstatus.')
    if value['status']=='approved': date.fromisoformat(value['decision_date'])
    elif value['decision_date'] is not None: raise ValueError('Framlegg skal ikkje ha vedtaksdato.')
    if not isinstance(value['title'],str) or not value['title'].strip() or len(value['title'])>200 or not isinstance(value['note'],str) or len(value['note'])>5000:
        raise ValueError('Ugyldig offentleg budsjetttekst.')
    if value['previous_state'] not in ('not_started','provisional','closed'): raise ValueError('Ugyldig samanlikningsstatus.')
    cutoff=date.fromisoformat(value['previous_as_of'])
    if cutoff.year>value['previous_year'] or (cutoff.year<value['previous_year'] and value['previous_state']!='not_started'):
        raise ValueError('Ugyldig samanlikningsdato.')
    from datetime import datetime
    datetime.fromisoformat(value['previous_captured_at'])
    if not isinstance(value['lines'],list): raise ValueError('Ugyldige budsjettlinjer.')
    seen=set()
    for line in value['lines']:
        if not isinstance(line,dict) or set(line)!={'category','label','kind','amount_ore','previous_ore'}: raise ValueError('Ugyldige budsjettlinjefelt.')
        code=line['category']
        if code not in CATEGORIES or code in seen or (line['label'],line['kind'])!=ACCOUNTS[code]: raise ValueError('Ugyldig kategori.')
        seen.add(code)
        if type(line['amount_ore']) is not int or not 0<=line['amount_ore']<=10**12 or type(line['previous_ore']) is not int or abs(line['previous_ore'])>10**16:
            raise ValueError('Ugyldig beløp.')
    if seen not in (set(CATEGORIES),set(CATEGORIES)-{'beer'}): raise ValueError('Manglande budsjettkategoriar.')
    for key in ('income_ore','expense_ore','result_ore','previous_income_ore','previous_expense_ore','previous_result_ore'):
        if type(value[key]) is not int: raise ValueError('Ugyldig sum.')
    prior_income=sum(line['previous_ore'] for line in value['lines'] if line['kind']=='income')
    prior_expense=sum(line['previous_ore'] for line in value['lines'] if line['kind']=='expense')
    if (prior_income,prior_expense,prior_income-prior_expense)!=(value['previous_income_ore'],value['previous_expense_ore'],value['previous_result_ore']): raise ValueError('Samanlikningssummane stemmer ikkje.')
    if totals(value['lines'])!=(value['income_ore'],value['expense_ore'],value['result_ore']): raise ValueError('Budsjettsummane stemmer ikkje.')


class Budgets:
    def __init__(self,get_db): self.get_db=get_db

    def create(self,budget_year,actor):
        budget_year=year(budget_year)
        if budget_year<1901: raise ValueError('Vel år frå 1901.')
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM budgets WHERE year=?',(budget_year,)).fetchone(): raise DocumentConflict('Budsjettet finst allereie.')
            content=dict(title=f'Budsjett {budget_year}',meeting_year=budget_year,note='',amounts={code:0 for code in CATEGORIES},
                         previous=previous(db,budget_year))
            raw=canonical(content)
            db.execute('INSERT INTO budgets(year,content,actor,updated_at) VALUES (?,?,?,?)',(budget_year,raw,actor,stamp()))
            db.execute('INSERT INTO budget_edits(year,revision,content,actor,created_at) VALUES (?,1,?,?,?)',(budget_year,raw,actor,stamp()))
        return budget_year

    def update(self,budget_year,revision,actor,action,form):
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM budgets WHERE year=?',(budget_year,)).fetchone()
            if not row or row['revision']!=int(revision): raise DocumentConflict('Budsjettet er endra. Kopier eigne endringar og opne siste revisjon.')
            content=json.loads(row['content'])
            if action=='save':
                title=str(form.get('title','')).strip();note=str(form.get('note','')).strip()
                if not title or len(title)>200 or len(note)>5000: raise ValueError('Fyll inn tittel og offentleg omtale innanfor lengdegrensene.')
                content.update(title=title,note=note,meeting_year=year(form.get('meeting_year')),
                               amounts={code:ore(form.get('amount_'+code,''),True) for code in CATEGORIES})
            elif action=='refresh_previous': content['previous']=previous(db,budget_year)
            elif action=='copy_previous':
                if form.get('confirmed')!='yes': raise ValueError('Stadfest at budsjettbeløpa skal bytast ut med forslag frå førre år.')
                content['previous']=previous(db,budget_year)
                if content['previous']['state']=='not_started': raise ValueError('Førre års rekneskap er ikkje registrert. Fyll inn budsjettet sjølv.')
                content['amounts']={code:max(0,n) for code,n in content['previous']['amounts'].items()}
            else: raise ValueError('Ugyldig handling.')
            raw=canonical(content);new_revision=row['revision']+1
            db.execute('UPDATE budgets SET revision=?,content=?,actor=?,updated_at=? WHERE year=?',(new_revision,raw,actor,stamp(),budget_year))
            db.execute('INSERT INTO budget_edits(year,revision,content,actor,created_at) VALUES (?,?,?,?,?)',(budget_year,new_revision,raw,actor,stamp()))

    def freeze(self,budget_year,revision,status,decision_date,actor):
        if status not in ('meeting','approved'): raise ValueError('Ugyldig status.')
        decision_date=date.fromisoformat(decision_date).isoformat() if status=='approved' else None
        if decision_date and decision_date>today().isoformat(): raise ValueError('Vedtaket kan ikkje vere i framtida.')
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM budgets WHERE year=?',(budget_year,)).fetchone()
            if not row or row['revision']!=int(revision): raise DocumentConflict('Budsjettet er endra. Kontroller nyaste revisjon.')
            old=db.execute('SELECT id,decision_date FROM budget_versions WHERE year=? AND source_revision=? AND status=?',(budget_year,row['revision'],status)).fetchone()
            if old:
                if old['decision_date']!=decision_date: raise DocumentConflict('Versjonen har annan vedtaksdato. Lag ny revisjon for retting.')
                return old['id']
            content=json.loads(row['content'])
            vid=db.execute('INSERT INTO budget_versions(year,source_revision,status,decision_date,actor,created_at) VALUES (?,?,?,?,?,?)',
                           (budget_year,row['revision'],status,decision_date,actor,stamp())).lastrowid
            payload=canonical(public_budget(content,budget_year,row['revision'],'budsjett-'+str(vid),status,decision_date))
            db.execute('UPDATE budget_versions SET payload=?,content_hash=? WHERE id=?',(payload,digest(payload),vid))
            return vid

    def enqueue(self,vid,actor):
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM budget_versions WHERE id=?',(vid,)).fetchone()
            if not row: raise ValueError('Versjonen finst ikkje.')
            validate_budget(json.loads(row['payload']))
            db.execute('INSERT OR IGNORE INTO budget_publication_queue(version_id,payload,content_hash,created_by,created_at) VALUES (?,?,?,?,?)',
                       (vid,row['payload'],row['content_hash'],actor,stamp()))

    def followup(self,budget_year):
        with managed_db(self.get_db) as db:
            row=db.execute('SELECT * FROM budgets WHERE year=?',(budget_year,)).fetchone()
            if not row: raise ValueError('Budsjettet finst ikkje.')
            approved=db.execute("SELECT payload FROM budget_versions WHERE year=? AND status='approved' ORDER BY id DESC LIMIT 1",(budget_year,)).fetchone()
            if approved:
                payload=json.loads(approved[0]);amounts={line['category']:line['amount_ore'] for line in payload['lines']};basis=payload['version_id'];basis_status='approved'
            else:
                amounts=json.loads(row['content'])['amounts'];basis='Arbeidsutkast, revisjon '+str(row['revision']);basis_status='draft'
            cutoff=min(today().isoformat(),f'{budget_year}-12-31')
            actual=actuals(db,budget_year,cutoff)
            started=today().year>=budget_year and bool(db.execute('SELECT 1 FROM ledger_years WHERE opening_confirmed=1 AND year<=?',(budget_year,)).fetchone())
            rows=[]
            for code in CATEGORIES:
                kind=ACCOUNTS[code][1];budget=amounts.get(code,0);used=actual[code]
                rows.append(dict(category=code,label=ACCOUNTS[code][0],kind=kind,budget_ore=budget,actual_ore=used,
                                 remaining_ore=budget-used if kind=='expense' else None,
                                 variance_ore=budget-used if kind=='expense' else used-budget))
            return dict(rows=rows,basis=basis,basis_status=basis_status,as_of=cutoff,started=started,
                        budget_result_ore=sum(r['budget_ore']*(1 if r['kind']=='income' else -1) for r in rows),
                        actual_result_ore=sum(r['actual_ore']*(1 if r['kind']=='income' else -1) for r in rows))
