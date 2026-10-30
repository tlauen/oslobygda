"""Balansert intern rekneskap. Beløp er heiltalsøre; ingen bank-/Vipps-kall."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import uuid

from database import managed_db

ACCOUNTS = {
    'bank': ('Bank', 'asset'), 'vipps': ('Vipps til gode', 'asset'),
    'cash': ('Kontantar', 'asset'), 'prepaid': ('Forskotsbetalte kostnader', 'asset'),
    'receivable': ('Andre krav', 'asset'), 'private': ('Skuldige private utlegg', 'liability'),
    'payable': ('Leverandørgjeld', 'liability'), 'equity': ('Eigenkapital', 'equity'),
    'membership': ('Medlemspengar', 'income'),
    'grants': ('Tilskot', 'income'), 'donations': ('Gåver', 'income'),
    'event_income': ('Tilskipingar', 'income'), 'interest': ('Renteinnkome', 'income'),
    'other_income': ('Anna innkome', 'income'), 'domain': ('Digitale tenester', 'expense'),
    'events': ('Tilskipingar', 'expense'), 'fees': ('Betalings- og bankgebyr', 'expense'),
    'other_expense': ('Andre utgifter', 'expense'),
}
MONEY_ACCOUNTS = ('bank', 'vipps', 'cash')


def now(): return datetime.now(timezone.utc).isoformat()


def ore(value, allow_zero=False):
    try:
        raw=str(value).strip().replace(',', '.')
        if len(raw)>40: raise ValueError('Beløpet er for langt.')
        amount = Decimal(raw)
        if not amount.is_finite() or abs(amount)>Decimal('10000000000'): raise ValueError('Beløpet er for stort.')
        if not amount.is_finite() or amount * 100 != (amount * 100).to_integral_value():
            raise ValueError('Beløpet må ha høgst to desimalar.')
        value = int(amount * 100)
    except (InvalidOperation, TypeError):
        raise ValueError('Ugyldig beløp.') from None
    if value < (0 if allow_zero else 1) or value > 10**12:
        raise ValueError('Beløpet må vere positivt og høgst 10 milliardar kr.')
    return value


def label(value, limit=1000, required=False):
    value = str(value or '').strip()
    if len(value) > limit or (required and not value):
        raise ValueError('Fyll inn tekst innanfor tillaten lengd.')
    return value


def iso_day(value):
    try: return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError): raise ValueError('Ugyldig dato.') from None


def init_ledger(get_db):
    with managed_db(get_db) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS ledger_accounts (
          code TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ledger_years (
          year INTEGER PRIMARY KEY CHECK(year BETWEEN 1900 AND 2200),
          closed INTEGER NOT NULL DEFAULT 0, opening_confirmed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS ledger_journals (
          id INTEGER PRIMARY KEY, day TEXT NOT NULL, public_text TEXT NOT NULL, internal_note TEXT NOT NULL,
          actor TEXT NOT NULL, created_at TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','posted')),
          request_key TEXT NOT NULL UNIQUE, request_hash TEXT NOT NULL,
          source_kind TEXT, source_id TEXT, event_uid TEXT,
          receipt_id INTEGER REFERENCES ledger_receipts(id), evidence_note TEXT NOT NULL,
          reversal_of INTEGER UNIQUE REFERENCES ledger_journals(id),
          related_to INTEGER REFERENCES ledger_journals(id),
          UNIQUE(source_kind,source_id)
        );
        CREATE TABLE IF NOT EXISTS ledger_lines (
          id INTEGER PRIMARY KEY, journal_id INTEGER NOT NULL REFERENCES ledger_journals(id),
          account TEXT NOT NULL REFERENCES ledger_accounts(code),
          amount_ore INTEGER NOT NULL CHECK(typeof(amount_ore)='integer' AND amount_ore!=0),
          party TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS ledger_receipts (
          id INTEGER PRIMARY KEY, file_key TEXT NOT NULL UNIQUE, original_name TEXT NOT NULL,
          media_type TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL,
          actor TEXT NOT NULL, created_at TEXT NOT NULL,
          replaces_id INTEGER REFERENCES ledger_receipts(id), reason TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS ledger_attachments (
          journal_id INTEGER NOT NULL REFERENCES ledger_journals(id), receipt_id INTEGER NOT NULL REFERENCES ledger_receipts(id),
          actor TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(journal_id,receipt_id)
        );
        CREATE TABLE IF NOT EXISTS ledger_reconciliations (
          id INTEGER PRIMARY KEY, year INTEGER NOT NULL, day TEXT NOT NULL, account TEXT NOT NULL,
          party TEXT NOT NULL, actual_ore INTEGER NOT NULL, book_ore INTEGER NOT NULL,
          ledger_revision INTEGER NOT NULL, note TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ledger_year_events (
          id INTEGER PRIMARY KEY, year INTEGER NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL,
          actor TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ledger_day ON ledger_journals(day);
        CREATE TRIGGER IF NOT EXISTS ledger_post_balanced BEFORE UPDATE OF state ON ledger_journals
        WHEN NEW.state='posted' BEGIN
          SELECT CASE WHEN (SELECT COUNT(*) FROM ledger_lines WHERE journal_id=NEW.id)<2
            OR COALESCE((SELECT SUM(amount_ore) FROM ledger_lines WHERE journal_id=NEW.id),1)!=0
            THEN RAISE(ABORT,'Posteringa balanserer ikkje') END;
          SELECT CASE WHEN COALESCE((SELECT closed FROM ledger_years WHERE year=CAST(substr(NEW.day,1,4) AS INTEGER)),0)=1
            THEN RAISE(ABORT,'Rekneskapsaaret er avslutta') END;
        END;
        CREATE TRIGGER IF NOT EXISTS ledger_no_posted_insert BEFORE INSERT ON ledger_journals
        WHEN NEW.state='posted' BEGIN SELECT RAISE(ABORT,'Opprett som utkast fyrst'); END;
        CREATE TRIGGER IF NOT EXISTS ledger_no_posted_update BEFORE UPDATE ON ledger_journals
        WHEN OLD.state='posted' BEGIN SELECT RAISE(ABORT,'Bokfoert post er fast'); END;
        CREATE TRIGGER IF NOT EXISTS ledger_no_posted_delete BEFORE DELETE ON ledger_journals
        WHEN OLD.state='posted' BEGIN SELECT RAISE(ABORT,'Bokfoert post er fast'); END;
        CREATE TRIGGER IF NOT EXISTS ledger_no_line_insert BEFORE INSERT ON ledger_lines
        WHEN (SELECT state FROM ledger_journals WHERE id=NEW.journal_id)='posted'
        BEGIN SELECT RAISE(ABORT,'Bokfoerte linjer er faste'); END;
        CREATE TRIGGER IF NOT EXISTS ledger_no_line_update BEFORE UPDATE ON ledger_lines
        WHEN (SELECT state FROM ledger_journals WHERE id=OLD.journal_id)='posted'
          OR (SELECT state FROM ledger_journals WHERE id=NEW.journal_id)='posted'
        BEGIN SELECT RAISE(ABORT,'Bokfoerte linjer er faste'); END;
        CREATE TRIGGER IF NOT EXISTS ledger_no_line_delete BEFORE DELETE ON ledger_lines
        WHEN (SELECT state FROM ledger_journals WHERE id=OLD.journal_id)='posted'
        BEGIN SELECT RAISE(ABORT,'Bokfoerte linjer er faste'); END;
        ''')
        columns={row[1] for row in db.execute('PRAGMA table_info(ledger_journals)')}
        if 'related_to' not in columns: db.execute('ALTER TABLE ledger_journals ADD COLUMN related_to INTEGER REFERENCES ledger_journals(id)')
        for table in ('ledger_receipts','ledger_reconciliations','ledger_year_events','ledger_attachments'):
            for operation in ('UPDATE','DELETE'):
                db.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()}
                    BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'Historikken er fast'); END''')
        db.executemany('INSERT OR IGNORE INTO ledger_accounts(code,name,kind) VALUES (?,?,?)',
                       [(code,*data) for code,data in ACCOUNTS.items()])


def balances(db, day, party=None):
    params = [day]
    party_filter = ''
    if party is not None:
        party_filter = ' AND l.party=?'; params.append(party)
    return dict(db.execute('''SELECT l.account, SUM(l.amount_ore) FROM ledger_lines l
        JOIN ledger_journals j ON j.id=l.journal_id WHERE j.state='posted' AND j.day<=?'''
        + party_filter + ' GROUP BY l.account', params).fetchall())


def year_balances(db, year):
    return dict(db.execute('''SELECT l.account,SUM(l.amount_ore) FROM ledger_lines l
        JOIN ledger_journals j ON j.id=l.journal_id WHERE j.state='posted' AND j.day BETWEEN ? AND ?
        GROUP BY l.account''', (f'{year}-01-01',f'{year}-12-31')).fetchall())


def make_lines(values):
    """Convert simple user actions to signed debits/credits."""
    kind = values.get('kind')
    amount = ore(values.get('amount'))
    account = values.get('account','bank')
    category = values.get('category')
    party = label(values.get('party'),200)
    if kind in ('income','expense','refund_income') and account not in MONEY_ACCOUNTS:
        raise ValueError('Vel bank, Vipps eller kontantar.')
    if kind in ('expense','private_expense','invoice'):
        if category not in ACCOUNTS or ACCOUNTS[category][1]!='expense': raise ValueError('Vel utgiftskategori.')
        credit = 'private' if kind=='private_expense' else ('payable' if kind=='invoice' else account)
        if credit in ('private','payable') and not party: raise ValueError('Oppgi intern utleggshavar eller leverandør.')
        return [(category,amount,''),(credit,-amount,party if credit in ('private','payable') else '')]
    if kind in ('income','refund_income'):
        if category not in ACCOUNTS or ACCOUNTS[category][1]!='income': raise ValueError('Vel inntektskategori.')
        sign = -1 if kind=='refund_income' else 1
        return [(account,amount*sign,''),(category,-amount*sign,'')]
    if kind=='private_forgiveness':
        if not party: raise ValueError('Oppgi kven som ettergir gjelda.')
        return [('private',amount,party),('donations',-amount,'')]
    if kind in ('private_refund','pay_invoice'):
        if not party: raise ValueError('Oppgi kven oppgjeret gjeld.')
        return [('private' if kind=='private_refund' else 'payable',amount,party),('bank',-amount,'')]
    if kind=='vipps_settlement':
        fee = ore(values.get('fee','0'),allow_zero=True)
        if fee>=amount: raise ValueError('Gebyret må vere mindre enn brutto oppgjer.')
        return [('bank',amount-fee,''),('vipps',-amount,'')] + ([('fees',fee,'')] if fee else [])
    if kind=='transfer':
        target=values.get('target')
        if account not in MONEY_ACCOUNTS or target not in MONEY_ACCOUNTS or target==account:
            raise ValueError('Vel to ulike betalingskontoar.')
        return [(target,amount,''),(account,-amount,'')]
    raise ValueError('Ugyldig føringstype.')


class Ledger:
    def __init__(self,get_db): self.get_db=get_db

    def _post(self,db,day,lines,public_text,internal_note,actor,request_key,evidence_note='',receipt_id=None,
              source_kind=None,source_id=None,event_uid=None,reversal_of=None,related_to=None):
        day=iso_day(day)
        if not 1900<=int(day[:4])<=2200: raise ValueError('Ugyldig rekneskapsår.')
        public_text=label(public_text,500,True); internal_note=label(internal_note,3000)
        evidence_note=label(evidence_note,1000)
        if not receipt_id and not evidence_note: raise ValueError('Legg ved bilag eller forklar dokumentasjonsgrunnlaget.')
        if receipt_id and not db.execute('SELECT 1 FROM ledger_receipts WHERE id=?',(receipt_id,)).fetchone():
            raise ValueError('Bilaget finst ikkje.')
        if not request_key or len(request_key)>100: raise ValueError('Ugyldig innsending.')
        if len(lines)<2 or sum(line[1] for line in lines)!=0: raise ValueError('Posteringa balanserer ikkje.')
        for account,amount,party in lines:
            if account not in ACCOUNTS or type(amount) is not int or not amount or abs(amount)>10**12:
                raise ValueError('Ugyldig kontolinje.')
            if account in ('private','payable') and not label(party,200): raise ValueError('Gjeld må ha intern motpart.')
            if account not in ('private','payable') and party: raise ValueError('Ugyldig motpart på konto.')
        payload=json.dumps([day,lines,public_text,internal_note,evidence_note,receipt_id,source_kind,source_id,event_uid,reversal_of,related_to],sort_keys=True)
        fingerprint=hashlib.sha256(payload.encode()).hexdigest()
        old=db.execute('SELECT id,request_hash FROM ledger_journals WHERE request_key=?',(request_key,)).fetchone()
        if old:
            if old['request_hash']!=fingerprint: raise ValueError('Innsendinga er allereie brukt med anna innhald. Opne nytt skjema.')
            return old['id']
        if source_kind and db.execute('SELECT 1 FROM ledger_journals WHERE source_kind=? AND source_id=?',(source_kind,source_id)).fetchone():
            raise ValueError('Kjelda er allereie bokført. Kontroller eksisterande post.')
        opening=db.execute('SELECT MIN(year) FROM ledger_years WHERE opening_confirmed=1').fetchone()[0]
        if source_kind!='opening' and (opening is None or int(day[:4])<opening):
            raise ValueError('Dokumenter inngåande balanse før bokføring i dette året.')
        db.execute('INSERT OR IGNORE INTO ledger_years(year) VALUES (?)',(int(day[:4]),))
        if db.execute('SELECT 1 FROM ledger_years WHERE year>=? AND closed=1',(int(day[:4]),)).fetchone():
            raise ValueError('Rekneskapsåret er avslutta. Opne året med grunngiving før ny føring.')
        journal=db.execute('''INSERT INTO ledger_journals
            (day,public_text,internal_note,actor,created_at,request_key,request_hash,source_kind,source_id,event_uid,receipt_id,evidence_note,reversal_of,related_to)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (day,public_text,internal_note,actor,now(),request_key,fingerprint,source_kind,source_id,event_uid,receipt_id,evidence_note,reversal_of,related_to)).lastrowid
        db.executemany('INSERT INTO ledger_lines(journal_id,account,amount_ore,party) VALUES (?,?,?,?)',[(journal,*line) for line in lines])
        db.execute("UPDATE ledger_journals SET state='posted' WHERE id=?",(journal,))
        return journal

    def post(self,values,actor,request_key):
        if values.get('kind')=='vipps_income_settled': return self.vipps_income_settled(values,actor,request_key)
        lines=make_lines(values)
        receipt_id=int(values['receipt_id']) if values.get('receipt_id') else None
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            # Private repayments and invoice payments cannot silently overpay a party.
            if values.get('kind') in ('private_refund','private_forgiveness','pay_invoice') and not db.execute('SELECT 1 FROM ledger_journals WHERE request_key=?',(request_key,)).fetchone():
                account=lines[0][0];party=lines[0][2]
                owed=-balances(db,iso_day(values.get('day')),party).get(account,0)
                if lines[0][1]>owed: raise ValueError('Oppgjeret er større enn registrert gjeld til denne motparten på datoen.')
            if values.get('payment_id'):
                payment=db.execute('SELECT amount_ore FROM payments WHERE id=?',(int(values['payment_id']),)).fetchone()
                if not payment or values.get('kind')!='income' or values.get('category')!='membership' or payment['amount_ore']!=ore(values.get('amount')):
                    raise ValueError('Kopla medlemsbetaling må finnast og ha same beløp som medlemsinntekta.')
            related_to=None
            refund=values.get('kind')=='refund_income'
            if refund:
                try: related_to=int(values.get('original_id',''))
                except ValueError: raise ValueError('Oppgi originalpost for inntektsrefusjonen.') from None
                original=db.execute("SELECT * FROM ledger_journals WHERE id=? AND state='posted'",(related_to,)).fetchone()
                category=values.get('category')
                income=db.execute('SELECT SUM(amount_ore) FROM ledger_lines WHERE journal_id=? AND account=?',(related_to,category)).fetchone()[0]
                if not original or not income or income>=0 or db.execute('SELECT 1 FROM ledger_journals WHERE reversal_of=?',(related_to,)).fetchone():
                    raise ValueError('Vel ei aktiv inntekt i same kategori som refusjonen.')
                if iso_day(values.get('day'))<original['day']: raise ValueError('Refusjonsdato kan ikkje vere før inntekta.')
                if not db.execute('SELECT 1 FROM ledger_journals WHERE request_key=?',(request_key,)).fetchone():
                    refunded=db.execute('''SELECT COALESCE(SUM(l.amount_ore),0) FROM ledger_lines l
                        JOIN ledger_journals j ON j.id=l.journal_id WHERE j.state='posted'
                        AND j.related_to=? AND l.account=?''',(related_to,category)).fetchone()[0]
                    if ore(values.get('amount'))>-income-refunded: raise ValueError('Refusjonen er større enn inntekta som står att.')
            return self._post(db,values.get('day'),lines,values.get('public_text'),values.get('internal_note'),actor,
                              request_key,values.get('evidence_note'),receipt_id,
                              'membership_payment' if values.get('payment_id') else ('income_refund' if refund else None),
                              str(int(values['payment_id'])) if values.get('payment_id') else (request_key if refund else None),
                              label(values.get('event_uid'),200) or None, related_to=related_to)

    def vipps_income_settled(self,values,actor,request_key):
        category=values.get('category')
        if category not in ('membership','donations'):
            raise ValueError('Vel Medlemspengar eller Gåver for samla Vipps-føring.')
        if values.get('payment_id'): raise ValueError('Bruk medlemsbetalingskoplinga for ei betaling som alt finst i medlemsregisteret.')
        if values.get('vipps_not_booked')!='yes': raise ValueError('Stadfest at verken innkoma eller oppgjeret er bokført frå før.')
        day=iso_day(values.get('day'));settled=iso_day(values.get('settlement_day'))
        if settled<day: raise ValueError('Oppgjersdato kan ikkje vere før betalingsdato.')
        amount=ore(values.get('amount'));fee=ore(values.get('fee','0'),True)
        if fee>=amount: raise ValueError('Gebyr må vere mindre enn bruttoinnkoma.')
        receipt=int(values['receipt_id']) if values.get('receipt_id') else None
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            first=self._post(db,day,[('vipps',amount,''),(category,-amount,'')],values.get('public_text'),values.get('internal_note'),actor,
                             request_key,values.get('evidence_note'),receipt,source_kind='vipps_income')
            lines=[('bank',amount-fee,''),('vipps',-amount,'')]
            if fee: lines.append(('fees',fee,''))
            self._post(db,settled,lines,'Vipps-oppgjer til bank',values.get('internal_note'),actor,request_key+'-oppgjer',
                       values.get('evidence_note'),receipt,source_kind='vipps_income_settlement',related_to=first)
            return first

    def reverse(self,journal_id,day,reason,actor,request_key):
        reason=label(reason,1000,True);day=iso_day(day)
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            original=db.execute("SELECT * FROM ledger_journals WHERE id=? AND state='posted'",(journal_id,)).fetchone()
            if not original: raise ValueError('Posten finst ikkje.')
            if original['source_kind'] in ('opening','opening_adjustment'): raise ValueError('Opningsbalanse må korrigerast gjennom opningsrutinen.')
            if original['source_kind'] in ('periodize','periodize_release','vipps_income_settlement'):
                raise ValueError('Reverser originalposten for å rette heile den samankopla føringa samla.')
            if original['reversal_of']: raise ValueError('Ei reversering kan ikkje reverserast. Før ny korrekt post.')
            linked=db.execute("SELECT * FROM ledger_journals WHERE related_to=? AND source_kind IN ('periodize','periodize_release','vipps_income_settlement') ORDER BY id",(journal_id,)).fetchall()
            if db.execute("SELECT 1 FROM ledger_journals WHERE related_to=? AND source_kind='income_refund'",(journal_id,)).fetchone():
                raise ValueError('Originalinntekta har refusjonar. Rett refusjonane og før ei særskild dokumentert korrigering.')
            result=None
            for index,record in enumerate([original,*linked]):
                reverse_day=day if index==0 else max(day,record['day'])
                if reverse_day<record['day']: raise ValueError('Rettingsdato kan ikkje vere før originalposten.')
                key=request_key if index==0 else request_key+'-'+str(record['id'])
                existing=db.execute('SELECT request_key FROM ledger_journals WHERE reversal_of=?',(record['id'],)).fetchone()
                if existing and existing[0]!=key: raise ValueError('Posten er allereie reversert.')
                lines=[(r['account'],-r['amount_ore'],r['party']) for r in db.execute('SELECT * FROM ledger_lines WHERE journal_id=?',(record['id'],))]
                created=self._post(db,reverse_day,lines,'Retting av post '+str(record['id']),reason,actor,key,
                                   'Reversering: '+reason,record['receipt_id'],reversal_of=record['id'],related_to=record['related_to'])
                if result is None: result=created
            return result

    def attach(self,journal_id,receipt_id,actor):
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT day FROM ledger_journals WHERE id=? AND state='posted'",(journal_id,)).fetchone()
            if not row or not db.execute('SELECT 1 FROM ledger_receipts WHERE id=?',(receipt_id,)).fetchone():
                raise ValueError('Posten eller bilaget finst ikkje.')
            if db.execute('SELECT closed FROM ledger_years WHERE year=?',(int(row['day'][:4]),)).fetchone()[0]:
                raise ValueError('Opne rekneskapsåret før du legg til dokumentasjon.')
            db.execute('INSERT OR IGNORE INTO ledger_attachments(journal_id,receipt_id,actor,created_at) VALUES (?,?,?,?)',
                       (journal_id,receipt_id,actor,now()))

    def opening(self,year,values,party,note,actor,request_key,correction=False):
        year=int(year)
        if not 1900<=year<=2200: raise ValueError('Ugyldig år.')
        desired={}
        for account in ('bank','vipps','cash','prepaid','receivable','private','payable'):
            amount=ore(values.get(account,'0'),True)
            if amount:
                name=label(party,200,True) if account in ('private','payable') else ''
                desired[(account,name)]=-amount if ACCOUNTS[account][1]=='liability' else amount
        total=sum(desired.values())
        if total: desired[('equity','')]=-total
        note=label(note,1000,True)
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            first=db.execute('SELECT MIN(year) FROM ledger_years WHERE opening_confirmed=1').fetchone()[0]
            if correction:
                if first!=year: raise ValueError('Korriger inngåande balanse i første rekneskapsår.')
                previous=db.execute('''SELECT l.account,l.party,SUM(l.amount_ore) amount FROM ledger_lines l
                    JOIN ledger_journals j ON j.id=l.journal_id WHERE j.state='posted'
                    AND j.source_kind IN ('opening','opening_adjustment') GROUP BY l.account,l.party''').fetchall()
                for row in previous:
                    k=(row['account'],row['party']);desired[k]=desired.get(k,0)-row['amount']
            elif first is not None or db.execute("SELECT 1 FROM ledger_journals WHERE state='posted'").fetchone():
                raise ValueError('Opningsbalanse finst eller bokføring er starta. Bruk korrigering i første rekneskapsår.')
            lines=[(account,amount,name) for (account,name),amount in desired.items() if amount]
            db.execute('INSERT OR IGNORE INTO ledger_years(year) VALUES (?)',(year,))
            if db.execute('SELECT closed FROM ledger_years WHERE year=?',(year,)).fetchone()[0]:
                raise ValueError('Opne rekneskapsåret før korrigering.')
            if lines:
                self._post(db,f'{year}-01-01',lines,'Korrigert inngåande balanse' if correction else 'Inngåande balanse',
                           note,actor,request_key,note,source_kind='opening_adjustment' if correction else 'opening',
                           source_id=request_key if correction else str(year))
            db.execute('UPDATE ledger_years SET opening_confirmed=1 WHERE year=?',(year,))
            db.execute('INSERT INTO ledger_year_events(year,action,reason,actor,created_at) VALUES (?,?,?,?,?)',
                       (year,'opening_adjustment' if correction else 'opening',note,actor,now()))

    def reconcile(self,year,day,account,actual,party,note,actor):
        day=iso_day(day);year=int(year)
        if int(day[:4])!=year or account not in ('bank','vipps','cash','private','payable','prepaid','receivable'):
            raise ValueError('Ugyldig avstemmingskonto eller dato.')
        party=label(party,200)
        if account not in ('private','payable') and party: raise ValueError('Bruk motpart berre for gjeld.')
        actual=ore(actual,True);note=label(note,1000,True)
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            book=balances(db,day,party if party else None).get(account,0)
            if ACCOUNTS[account][1]=='liability': book=-book
            revision=db.execute("SELECT COALESCE(MAX(id),0) FROM ledger_journals WHERE state='posted'").fetchone()[0]
            db.execute('''INSERT INTO ledger_reconciliations(year,day,account,party,actual_ore,book_ore,ledger_revision,note,actor,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)''',(year,day,account,party,actual,book,revision,note,actor,now()))

    def year_state(self,year,close,reason,actor):
        year=int(year);reason=label(reason,1000,True)
        if not 1900<=year<=2200: raise ValueError('Ugyldig år.')
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO ledger_years(year) VALUES (?)',(year,))
            if close:
                if db.execute('SELECT 1 FROM ledger_years WHERE year<? AND closed=0',(year,)).fetchone():
                    raise ValueError('Avslutt tidlegare rekneskapsår først.')
                if not db.execute('SELECT 1 FROM ledger_years WHERE year<=? AND opening_confirmed=1',(year,)).fetchone():
                    raise ValueError('Inngåande balanse må vere dokumentert først.')
                revision=db.execute("SELECT COALESCE(MAX(id),0) FROM ledger_journals WHERE state='posted'").fetchone()[0]
                end=f'{year}-12-31'; amounts=balances(db,end)
                for account in ('bank','vipps','cash','private','payable','prepaid','receivable'):
                    if account not in ('bank','vipps','private') and amounts.get(account,0)==0: continue
                    row=db.execute('''SELECT * FROM ledger_reconciliations WHERE year=? AND account=? AND party='' AND day=?
                        ORDER BY id DESC LIMIT 1''',(year,account,end)).fetchone()
                    if not row or row['actual_ore']!=row['book_ore'] or row['ledger_revision']!=revision:
                        raise ValueError('Avstem alle relevante saldoar ved årsslutt etter siste bokføring, utan differansar.')
            if not close and db.execute('SELECT 1 FROM ledger_years WHERE year>? AND closed=1',(year,)).fetchone():
                raise ValueError('Opne seinare avslutta rekneskapsår først; saldoane deira kan bli påverka.')
            db.execute('UPDATE ledger_years SET closed=? WHERE year=?',(int(close),year))
            db.execute('INSERT INTO ledger_year_events(year,action,reason,actor,created_at) VALUES (?,?,?,?,?)',
                       (year,'close' if close else 'reopen',reason,actor,now()))

    def periodize(self,journal_id,start,end,actor,request_key):
        start=date.fromisoformat(iso_day(start));end=date.fromisoformat(iso_day(end))
        if end<start: raise ValueError('Tenesteperioden sluttar før han byrjar.')
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            original=db.execute("SELECT * FROM ledger_journals WHERE id=? AND state='posted'",(journal_id,)).fetchone()
            if not original: raise ValueError('Posten finst ikkje.')
            if original['reversal_of'] or db.execute('SELECT 1 FROM ledger_journals WHERE reversal_of=?',(journal_id,)).fetchone():
                raise ValueError('Reversert post kan ikkje periodiserast.')
            expenses=db.execute('SELECT account,amount_ore FROM ledger_lines WHERE journal_id=? AND amount_ore>0',(journal_id,)).fetchall()
            if len(expenses)!=1 or ACCOUNTS[expenses[0]['account']][1]!='expense': raise ValueError('Vel ei enkel utgiftsføring.')
            if start.year!=int(original['day'][:4]): raise ValueError('Tenesteperioden må byrje i utgiftsåret; andre tilfelle må førast særskilt.')
            if end.year==start.year: raise ValueError('Perioden kryssar ikkje årsskiftet.')
            if db.execute('SELECT 1 FROM ledger_journals WHERE source_kind=? AND source_id=?',('periodize',str(journal_id))).fetchone():
                raise ValueError('Utgifta er allereie periodisert.')
            amount=expenses[0]['amount_ore'];category=expenses[0]['account'];days=(end-start).days+1
            allocations=[];remaining=amount
            for y in range(start.year,end.year+1):
                n=(min(end,date(y,12,31))-max(start,date(y,1,1))).days+1
                share=remaining if y==end.year else amount*n//days
                remaining-=share;allocations.append((y,share))
            deferred=amount-allocations[0][1]
            if not deferred: raise ValueError('Ingen øre å periodisere.')
            self._post(db,f'{start.year}-12-31',[('prepaid',deferred,''),(category,-deferred,'')],
                       'Periodisering av abonnement',f'Post {journal_id}: {start} til {end}',actor,request_key,
                       'Tenesteperiode dokumentert på originalpost',original['receipt_id'],'periodize',str(journal_id),related_to=journal_id)
            for y,share in allocations[1:]:
                if share:
                    self._post(db,f'{y}-01-01',[(category,share,''),('prepaid',-share,'')],
                               'Kostnad for forskotsbetalt abonnement',f'Post {journal_id}: {start} til {end}',actor,
                               request_key+f'-{y}','Tenesteperiode dokumentert på originalpost',original['receipt_id'],
                               'periodize_release',str(journal_id)+'-'+str(y),related_to=journal_id)
