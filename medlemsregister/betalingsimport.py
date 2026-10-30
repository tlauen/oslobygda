"""Kontrollerte kjelder for medlemsinntekter. Ingen betaling/trekk/refusjon blir starta."""
from datetime import datetime,date,timezone,timedelta
from zoneinfo import ZoneInfo
import json
import uuid

from arsdokument import stamp,today,canonical,digest
from database import managed_db
from rekneskap import Ledger,label,iso_day
from vipps_client import VippsError


def init_payment_import(get_db):
    with managed_db(get_db) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS payment_evidence (
          id INTEGER PRIMARY KEY,payment_id INTEGER NOT NULL,revision INTEGER NOT NULL,
          amount_ore INTEGER NOT NULL,day TEXT NOT NULL,account TEXT NOT NULL,
          captured_ore INTEGER NOT NULL,refunded_ore INTEGER NOT NULL,source TEXT NOT NULL,
          source_reference TEXT NOT NULL,checked_at TEXT NOT NULL,actor TEXT NOT NULL,note TEXT NOT NULL,
          UNIQUE(payment_id,revision)
        );
        CREATE TABLE IF NOT EXISTS payment_ledger_links (
          payment_id INTEGER PRIMARY KEY,journal_id INTEGER NOT NULL UNIQUE REFERENCES ledger_journals(id),
          evidence_id INTEGER NOT NULL REFERENCES payment_evidence(id),actor TEXT NOT NULL,created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS payment_import_settings (
          id INTEGER PRIMARY KEY CHECK(id=1),enabled INTEGER NOT NULL DEFAULT 0,
          from_day TEXT NOT NULL,actor TEXT NOT NULL,updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS payment_import_errors (
          payment_id INTEGER PRIMARY KEY,message TEXT NOT NULL,checked_at TEXT NOT NULL
        );
        ''')
        db.execute("""CREATE TABLE IF NOT EXISTS payment_ledger_corrections (
          id INTEGER PRIMARY KEY,payment_id INTEGER NOT NULL,old_journal_id INTEGER NOT NULL UNIQUE REFERENCES ledger_journals(id),
          journal_id INTEGER NOT NULL UNIQUE REFERENCES ledger_journals(id),evidence_id INTEGER NOT NULL REFERENCES payment_evidence(id),
          actor TEXT NOT NULL,created_at TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS payment_group_links (
          payment_id INTEGER PRIMARY KEY REFERENCES payments(id),journal_id INTEGER NOT NULL REFERENCES ledger_journals(id),
          amount_ore INTEGER NOT NULL,note TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL)""")
        for table in ('payment_evidence','payment_ledger_links','payment_ledger_corrections','payment_group_links'):
            for operation in ('UPDATE','DELETE'):
                db.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table}
                  BEGIN SELECT RAISE(ABORT,'Importhistorikken er fast'); END''')


def event_time(value):
    if not isinstance(value,str): raise ValueError('Manglande kjeldetidspunkt.')
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None: raise ValueError('Kjeldetidspunktet manglar tidssone.')
    if parsed>datetime.now(timezone.utc)+timedelta(minutes=5): raise ValueError('Vipps-tidspunktet er i framtida.')
    return parsed


def inspect_vipps(order,payment,result,events):
    from ny_innmelding import SignupService
    if order['environment']!='production' or order['status'] not in ('complete','review','redacted') or order['payment_id']!=payment['id']:
        raise ValueError('Berre bokført produksjonsbetaling kan kontrollerast.')
    SignupService.check_result(order,result)
    if result.get('state')!='AUTHORIZED' or result['aggregate']['cancelledAmount']['value']:
        raise ValueError('Betalingsstatus eller kansellering krev manuell kontroll.')
    captured=result['aggregate']['capturedAmount']['value'];refunded=result['aggregate']['refundedAmount']['value']
    if captured!=payment['amount_ore'] or captured!=order['amount_ore'] or refunded>captured:
        raise ValueError('Trekt beløp stemmer ikkje med registrert medlemsbetaling.')
    if not isinstance(events,list) or len(events)>1000: raise ValueError('Ugyldig hendingslogg.')
    captures=[];refunds=[];seen={}
    for event in events:
        if not isinstance(event,dict): raise ValueError('Ugyldig betalingshending.')
        if event.get('name') not in ('CAPTURED','REFUNDED') or event.get('success') is not True: continue
        if event.get('reference')!=order['reference']: raise ValueError('Hendinga har feil betalingsreferanse.')
        amount=event.get('amount',{})
        if amount.get('currency')!='NOK' or type(amount.get('value')) is not int or amount['value']<=0:
            raise ValueError('Ugyldig beløp i hendingsloggen.')
        timestamp=event_time(event.get('timestamp'))
        key=event.get('idempotencyKey') or event.get('pspReference')
        if not isinstance(key,str) or not key: raise ValueError('Hendinga manglar stabil identitet.')
        identity=(event['name'],key)
        fingerprint=(timestamp.isoformat(),amount['value'])
        if identity in seen:
            if seen[identity]!=fingerprint: raise ValueError('Same hending har motstridande innhald.')
            continue
        seen[identity]=fingerprint
        (captures if event['name']=='CAPTURED' else refunds).append((timestamp,amount['value']))
    if len(captures)!=1 or captures[0][1]!=captured or sum(n for _,n in refunds)!=refunded:
        raise ValueError('Trekk eller refusjonar i hendingsloggen må kontrollerast manuelt.')
    return dict(amount_ore=payment['amount_ore'],day=captures[0][0].astimezone(ZoneInfo('Europe/Oslo')).date().isoformat(),
                account='vipps',captured_ore=captured,refunded_ore=refunded,source='vipps-events',source_reference=order['reference'])


class PaymentImport:
    def __init__(self,get_db): self.get_db=get_db;self.ledger=Ledger(get_db)

    def _source(self,db,pid):
        payment=db.execute('SELECT * FROM payments WHERE id=?',(pid,)).fetchone()
        if not payment or payment['amount_ore']<=0: raise ValueError('Positiv medlemsbetaling finst ikkje.')
        orders=db.execute('SELECT * FROM signup_orders WHERE payment_id=?',(pid,)).fetchall()
        if len(orders)>1: raise ValueError('Fleire Vipps-ordrar viser til same betaling.')
        order=dict(orders[0]) if orders else None
        if order and order['environment']!='production': raise ValueError('Testbetalingar skal ikkje førast i rekneskapen.')
        return dict(payment),order

    def _record(self,db,pid,values,actor,note):
        old=db.execute('SELECT * FROM payment_evidence WHERE payment_id=? ORDER BY revision DESC LIMIT 1',(pid,)).fetchone()
        fields=('amount_ore','day','account','captured_ore','refunded_ore','source','source_reference')
        note=label(note,1000,True)
        if old and all(old[k]==values[k] for k in fields) and old['note']==note and datetime.now(timezone.utc)-datetime.fromisoformat(old['checked_at'])<timedelta(minutes=5):
            db.execute('DELETE FROM payment_import_errors WHERE payment_id=?',(pid,))
            return old['id']
        revision=old['revision']+1 if old else 1
        eid=db.execute('''INSERT INTO payment_evidence
            (payment_id,revision,amount_ore,day,account,captured_ore,refunded_ore,source,source_reference,checked_at,actor,note)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',(pid,revision,*(values[k] for k in fields),stamp(),actor,note)).lastrowid
        db.execute('DELETE FROM payment_import_errors WHERE payment_id=?',(pid,))
        return eid

    def attest(self,pid,day,account,note,actor):
        day=iso_day(day)
        if day>today().isoformat() or account not in ('bank','vipps','cash'): raise ValueError('Vel faktisk betalingsdato og rett konto.')
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE');payment,order=self._source(db,pid)
            if order: raise ValueError('ePayment-ordrar må kontrollerast mot Vipps, ikkje overstyrast med manuell dato.')
            values=dict(amount_ore=payment['amount_ore'],day=day,account=account,captured_ore=payment['amount_ore'],
                        refunded_ore=0,source='manual-attestation',source_reference='')
            return self._record(db,pid,values,actor,note)

    def fetch(self,pid,actor,client_factory=None):
        with managed_db(self.get_db) as db: payment,order=self._source(db,pid)
        if not order: raise ValueError('Historisk/manuell betaling har ingen ePayment-ordre.')
        if order['status'] not in ('complete','review','redacted'): raise ValueError('Betalinga er ikkje klar til rekneskapskontroll.')
        if client_factory is None:
            from ny_innmelding import client_for
            client_factory=client_for
        # GET status and GET events only; never call SignupService.reconcile (which may capture).
        client=client_factory('production',order['msn'])
        result=client.get(order['reference']);events=client.events(order['reference'])
        try: values=inspect_vipps(order,payment,result,events)
        except (ValueError,VippsError,KeyError,TypeError,OverflowError):
            raise VippsError('Vipps-kjelda gav ikkje eintydig trekkdato og beløp. Kontroller betalinga manuelt.') from None
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE');fresh,fresh_order=self._source(db,pid)
            if fresh['amount_ore']!=payment['amount_ore'] or not fresh_order or any(fresh_order[k]!=order[k] for k in ('reference','msn','environment','payment_id')):
                raise ValueError('Betalingskjelda er endra under kontroll. Prøv igjen.')
            return self._record(db,pid,values,actor,'Kontrollert status og hendingslogg direkte frå Vipps.')

    def _evidence(self,db,pid):
        payment,order=self._source(db,pid)
        evidence=db.execute('SELECT * FROM payment_evidence WHERE payment_id=? ORDER BY revision DESC LIMIT 1',(pid,)).fetchone()
        if not evidence: raise ValueError('Betalingsdato og dokumentasjonsgrunnlag må kontrollerast først.')
        if evidence['amount_ore']!=payment['amount_ore']: raise ValueError('Beløpet er endra etter kjeldekontroll.')
        if order and (evidence['source']!='vipps-events' or evidence['source_reference']!=order['reference']):
            raise ValueError('Vipps-kjelda stemmer ikkje med dokumentasjonen.')
        if order and order['status'] not in ('complete','review','redacted'): raise ValueError('Ordren må kontrollerast på nytt.')
        if order and datetime.now(timezone.utc)-datetime.fromisoformat(evidence['checked_at'])>timedelta(hours=1):
            raise ValueError('Hent ny Vipps-kontroll før bokføring. Kjeldekontrollen er eldre enn ein time.')
        if order and order['status']=='review': raise ValueError('Vipps-ordren er sett til kontroll. Avklar ordren før ny bokføring.')
        if evidence['refunded_ore']: raise ValueError('Refusjon er observert. Avstem og før refusjonen manuelt; inga automatisk nettoføring.')
        return payment,order,evidence

    def _linked(self,db,pid):
        group=db.execute('SELECT journal_id FROM payment_group_links WHERE payment_id=?',(pid,)).fetchone()
        if group:return group[0]
        correction=db.execute('SELECT journal_id FROM payment_ledger_corrections WHERE payment_id=? ORDER BY id DESC LIMIT 1',(pid,)).fetchone()
        if correction: return correction[0]
        row=db.execute('SELECT journal_id FROM payment_ledger_links WHERE payment_id=?',(pid,)).fetchone()
        if row: return row[0]
        row=db.execute("SELECT id FROM ledger_journals WHERE state='posted' AND source_kind='membership_payment' AND source_id=?",(str(pid),)).fetchone()
        return row[0] if row else None

    def _check_group(self,db,jid):
        rows=db.execute('SELECT g.amount_ore,p.amount_ore current_amount FROM payment_group_links g LEFT JOIN payments p ON p.id=g.payment_id WHERE g.journal_id=?',(jid,)).fetchall()
        if not rows or any(r['current_amount']!=r['amount_ore'] for r in rows):raise ValueError('Medlemsbetalingane i samleposten er endra. Manuell kontroll er nødvendig.')
        amount=sum(r['amount_ore'] for r in rows)
        journal=db.execute('SELECT * FROM ledger_journals WHERE id=?',(jid,)).fetchone()
        lines=sorted(tuple(r) for r in db.execute('SELECT account,amount_ore FROM ledger_lines WHERE journal_id=?',(jid,)))
        if not journal or journal['state']!='posted' or lines!=sorted([('bank',amount),('membership',-amount)]) or db.execute('SELECT 1 FROM ledger_journals WHERE reversal_of=?',(jid,)).fetchone():
            raise ValueError('Samleposten avvik eller er reversert. Manuell kontroll er nødvendig.')

    def link_group(self,pids,jid,note,actor):
        ids=[int(pid) for pid in pids]
        if not ids or len(ids)>200 or len(set(ids))!=len(ids):raise ValueError('Vel éin eller fleire ulike betalingar, maks 200.')
        note=str(note or '').strip()
        if not note or len(note)>1000:raise ValueError('Forklar dokumentasjonen for den samla bankoverføringa, maks 1000 teikn.')
        jid=int(jid)
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT payment_id FROM payment_group_links WHERE journal_id=?',(jid,)).fetchall()
            if existing:
                if {r[0] for r in existing}==set(ids):self._check_group(db,jid);return jid
                raise ValueError('Samleposten er allereie kopla til andre betalingar.')
            payments=[]
            for pid in ids:
                payment,order=self._source(db,pid)
                if order:raise ValueError('Betalingar gjennom innmeldingsskjemaet må kontrollerast mot Vipps kvar for seg.')
                if self._linked(db,pid):raise ValueError('Ei vald betaling er allereie kopla til rekneskapen.')
                payments.append(payment)
            amount=sum(p['amount_ore'] for p in payments)
            journal=db.execute('SELECT * FROM ledger_journals WHERE id=?',(jid,)).fetchone()
            lines=sorted(tuple(r) for r in db.execute('SELECT account,amount_ore FROM ledger_lines WHERE journal_id=?',(jid,)))
            if not journal or journal['state']!='posted' or journal['source_kind'] is not None or journal['reversal_of'] or lines!=sorted([('bank',amount),('membership',-amount)]):
                raise ValueError('Posten må vere ein vanleg medlemspengepost til Bank, med nøyaktig same sum som dei valde betalingane.')
            if db.execute('SELECT 1 FROM ledger_journals WHERE reversal_of=?',(jid,)).fetchone():raise ValueError('Ein reversert post kan ikkje brukast.')
            if db.execute('SELECT 1 FROM payment_ledger_links WHERE journal_id=?',(jid,)).fetchone() or db.execute('SELECT 1 FROM payment_ledger_corrections WHERE journal_id=?',(jid,)).fetchone():raise ValueError('Posten er allereie kopla.')
            if any(str(p['for_year'])!=journal['day'][:4] for p in payments):raise ValueError('Medlemsåret må samsvare med året for samleposten. Kontroller årstala manuelt.')
            for payment in payments:
                db.execute('INSERT INTO payment_group_links VALUES (?,?,?,?,?,?)',(payment['id'],jid,payment['amount_ore'],note,actor,stamp()))
                db.execute('DELETE FROM payment_import_errors WHERE payment_id=?',(payment['id'],))
            return jid

    def _check_link(self,db,jid,payment,evidence):
        if db.execute('SELECT 1 FROM payment_group_links WHERE payment_id=? AND journal_id=?',(payment['id'],jid)).fetchone():
            self._check_group(db,jid);return
        journal=db.execute("SELECT * FROM ledger_journals WHERE id=? AND state='posted'",(jid,)).fetchone()
        lines=[tuple(r) for r in db.execute('SELECT account,amount_ore FROM ledger_lines WHERE journal_id=?',(jid,))]
        expected=sorted([(evidence['account'],payment['amount_ore']),('membership',-payment['amount_ore'])])
        if not journal or journal['day']!=evidence['day'] or sorted(lines)!=expected or db.execute('SELECT 1 FROM ledger_journals WHERE reversal_of=?',(jid,)).fetchone():
            raise ValueError('Kopla føring avvik frå kjelda eller er reversert. Manuell retting er nødvendig.')

    def _candidates(self,db,payment,evidence):
        return [row[0] for row in db.execute('''SELECT j.id FROM ledger_journals j JOIN ledger_lines l ON l.journal_id=j.id
            WHERE j.state='posted' AND l.account='membership' AND l.amount_ore=? AND substr(j.day,1,4)=?
            AND j.reversal_of IS NULL AND NOT EXISTS(SELECT 1 FROM ledger_journals r WHERE r.reversal_of=j.id)
            AND j.source_kind IS NULL AND NOT EXISTS(SELECT 1 FROM payment_group_links g WHERE g.journal_id=j.id) AND NOT EXISTS(SELECT 1 FROM payment_ledger_links p WHERE p.journal_id=j.id)
            ORDER BY j.id''',(-payment['amount_ore'],evidence['day'][:4]))]

    def book(self,pid,evidence_id,actor,confirm_no_duplicate=False,automatic=False):
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE');payment,order,evidence=self._evidence(db,pid)
            if evidence['id']!=int(evidence_id): raise ValueError('Kjeldekontrollen er endra. Opne førehandsvisinga på nytt.')
            existing=self._linked(db,pid)
            if existing:
                self._check_link(db,existing,payment,evidence)
                db.execute('DELETE FROM payment_import_errors WHERE payment_id=?',(pid,))
                return existing
            if automatic:
                settings=db.execute('SELECT * FROM payment_import_settings WHERE id=1 AND enabled=1').fetchone()
                if not settings or not order or evidence['source']!='vipps-events' or order['status'] not in ('complete','redacted') or evidence['day']<settings['from_day']:
                    raise ValueError('Betalinga er ikkje omfatta av aktivert automatikk.')
                if datetime.now(timezone.utc)-datetime.fromisoformat(evidence['checked_at'])>timedelta(hours=1):
                    raise ValueError('Vipps-kontrollen er for gammal for automatisk bokføring.')
            candidates=self._candidates(db,payment,evidence)
            if candidates and (automatic or not confirm_no_duplicate): raise ValueError('Mogleg eksisterande føring. Kople til rett post eller stadfest etter kontroll.')
            jid=self.ledger._post(db,evidence['day'],[(evidence['account'],payment['amount_ore'],''),('membership',-payment['amount_ore'],'')],
                                  'Medlemskontingent','Betalingsår '+str(payment['for_year']),actor,'member-import-'+str(pid),
                                  evidence['note'],source_kind='membership_payment',source_id=str(pid))
            db.execute('INSERT INTO payment_ledger_links(payment_id,journal_id,evidence_id,actor,created_at) VALUES (?,?,?,?,?)',(pid,jid,evidence['id'],actor,stamp()))
            db.execute('DELETE FROM payment_import_errors WHERE payment_id=?',(pid,))
            return jid

    def correct_reversed(self,pid,evidence_id,old_jid,actor):
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE');payment,order,evidence=self._evidence(db,pid)
            if evidence['id']!=int(evidence_id): raise ValueError('Kjeldekontrollen er endra. Opne betalinga på nytt.')
            existing=self._linked(db,pid)
            if db.execute('SELECT 1 FROM payment_group_links WHERE payment_id=?',(pid,)).fetchone():raise ValueError('Ein reversert samlepost må rettast samla, ikkje som ei enkeltbetaling.')
            prior=db.execute('SELECT journal_id FROM payment_ledger_corrections WHERE payment_id=? AND old_journal_id=?',(pid,int(old_jid))).fetchone()
            if prior: return prior[0]
            if existing!=int(old_jid) or not db.execute('SELECT 1 FROM ledger_journals WHERE reversal_of=?',(existing,)).fetchone():
                raise ValueError('Berre den reverserte, kopla posten kan rettast her.')
            if self._candidates(db,payment,evidence): raise ValueError('Det finst ei mogleg eksisterande føring. Avklar henne før ny bokføring.')
            jid=self.ledger._post(db,evidence['day'],[(evidence['account'],payment['amount_ore'],''),('membership',-payment['amount_ore'],'')],
                'Medlemskontingent','Retta betalingskonto etter reversert P'+str(existing),actor,'member-correction-'+str(pid)+'-'+str(existing),
                evidence['note'],source_kind='membership_payment_correction',source_id=str(pid)+'-'+str(existing))
            db.execute('INSERT INTO payment_ledger_corrections(payment_id,old_journal_id,journal_id,evidence_id,actor,created_at) VALUES (?,?,?,?,?,?)',
                (pid,existing,jid,evidence['id'],actor,stamp()))
            db.execute('DELETE FROM payment_import_errors WHERE payment_id=?',(pid,))
            return jid

    def link(self,pid,evidence_id,jid,actor):
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE');payment,order,evidence=self._evidence(db,pid)
            if evidence['id']!=int(evidence_id): raise ValueError('Kjeldekontrollen er endra.')
            existing=self._linked(db,pid)
            if existing:
                if existing!=jid: raise ValueError('Betalinga er allereie kopla til ein annan post.')
                return existing
            journal=db.execute("SELECT * FROM ledger_journals WHERE id=? AND state='posted'",(jid,)).fetchone()
            lines=db.execute('SELECT account,amount_ore FROM ledger_lines WHERE journal_id=?',(jid,)).fetchall()
            expected=sorted([(evidence['account'],payment['amount_ore']),('membership',-payment['amount_ore'])])
            if not journal or journal['source_kind'] is not None or journal['reversal_of'] or journal['day']!=evidence['day'] or sorted(tuple(r) for r in lines)!=expected or db.execute('SELECT 1 FROM ledger_journals WHERE reversal_of=?',(jid,)).fetchone():
                raise ValueError('Posten må ha same dato, beløp og betalingskonto utan andre inntekter eller rettingar.')
            if db.execute('SELECT 1 FROM payment_ledger_links WHERE journal_id=?',(jid,)).fetchone() or db.execute('SELECT 1 FROM payment_group_links WHERE journal_id=?',(jid,)).fetchone(): raise ValueError('Posten er allereie kopla.')
            db.execute('INSERT INTO payment_ledger_links(payment_id,journal_id,evidence_id,actor,created_at) VALUES (?,?,?,?,?)',(pid,jid,evidence['id'],actor,stamp()))
            db.execute('DELETE FROM payment_import_errors WHERE payment_id=?',(pid,))
            return jid

    def configure(self,enabled,from_day,actor):
        from_day=iso_day(from_day)
        if from_day<today().isoformat(): raise ValueError('Automatikk skal starte i dag eller seinare. Historiske betalingar blir gjennomgått manuelt.')
        with managed_db(self.get_db) as db:
            if enabled and not db.execute('SELECT 1 FROM ledger_years WHERE opening_confirmed=1 AND year<=?',(int(from_day[:4]),)).fetchone():
                raise ValueError('Dokumenter inngåande balanse før automatikk blir aktivert.')
            db.execute('INSERT INTO payment_import_settings(id,enabled,from_day,actor,updated_at) VALUES (1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET enabled=excluded.enabled,from_day=excluded.from_day,actor=excluded.actor,updated_at=excluded.updated_at',(int(enabled),from_day,actor,stamp()))

    def run(self,fetch=False,limit=50,client_factory=None):
        counts=dict(checked=0,booked=0,review=0)
        with managed_db(self.get_db) as db:
            settings=db.execute('SELECT * FROM payment_import_settings WHERE id=1 AND enabled=1').fetchone()
            if not settings: return counts
            pids=[r[0] for r in db.execute('''SELECT p.id FROM payments p JOIN signup_orders o ON o.payment_id=p.id
                WHERE o.environment='production' AND o.status IN ('complete','review','redacted')
                ORDER BY COALESCE((SELECT MAX(checked_at) FROM payment_evidence e WHERE e.payment_id=p.id),'') ASC,p.id LIMIT ?''',(limit,))]
        for pid in pids:
            try:
                if fetch: self.fetch(pid,'vedlikehald',client_factory);counts['checked']+=1
                with managed_db(self.get_db) as db:
                    evidence=db.execute('SELECT * FROM payment_evidence WHERE payment_id=? ORDER BY revision DESC LIMIT 1',(pid,)).fetchone()
                    linked=self._linked(db,pid)
                    if linked and evidence:
                        payment,_=self._source(db,pid)
                        self._check_link(db,linked,payment,evidence)
                if not evidence: raise ValueError('Kjeldetidspunkt manglar. Hent Vipps-kontroll.')
                if evidence['refunded_ore']: raise ValueError('Refusjon observert; samanlikn med registrerte refusjonspostar.')
                if not linked:
                    self.book(pid,evidence['id'],'vedlikehald',automatic=True);counts['booked']+=1
            except (ValueError,VippsError,KeyError,TypeError):
                counts['review']+=1
                with managed_db(self.get_db) as db:
                    db.execute('INSERT INTO payment_import_errors(payment_id,message,checked_at) VALUES (?,?,?) ON CONFLICT(payment_id) DO UPDATE SET message=excluded.message,checked_at=excluded.checked_at',(pid,'Kjelde eller bokføring krev manuell kontroll. Opne betalingsimporten.',stamp()))
        return counts
