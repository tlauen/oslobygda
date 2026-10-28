"""Årlege satsar og personlege fornyingslenkjer. Ingen utsending utan styrehandling."""
from contextlib import closing
from datetime import datetime, date
from email.message import EmailMessage
import hashlib
import os
import secrets
from zoneinfo import ZoneInfo

from flask import abort, redirect, render_template, request, session
from vipps_client import amount_ore, VippsError
from epost import send_message, DeliveryUncertain


def today():
    return datetime.now(ZoneInfo('Europe/Oslo')).date()


def init_periods(get_db):
    with closing(get_db()) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS membership_periods (
          year INTEGER PRIMARY KEY, minimum_ore INTEGER, superkul_ore INTEGER,
          opens_on TEXT NOT NULL, approved INTEGER NOT NULL DEFAULT 0,
          approved_on TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS renewal_links (
          id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, member_id INTEGER NOT NULL,
          for_year INTEGER NOT NULL, environment TEXT NOT NULL, created_at TEXT NOT NULL,
          revoked INTEGER NOT NULL DEFAULT 0, mail_status TEXT NOT NULL DEFAULT 'not_sent'
        );
        CREATE INDEX IF NOT EXISTS renewal_member_year ON renewal_links(member_id,for_year,environment);
        ''')
        # Historisk sats for stiftingsåret. 2027 krev eit uttrykkeleg vedtak etter årsmøtet.
        threshold=500
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_settings'").fetchone():
            old=db.execute("SELECT value FROM app_settings WHERE key='superkul_grense_ore'").fetchone()
            active=db.execute("SELECT value FROM app_settings WHERE key='medlemsbetalingsar'").fetchone()
            if old and (not active or str(active[0])=='2026'): threshold=int(old[0])
        db.execute("INSERT OR IGNORE INTO membership_periods VALUES (2026,500,?,'2026-01-01',1,'2026-01-01',1)",(threshold,))
        db.execute("INSERT OR IGNORE INTO membership_periods VALUES (2027,NULL,NULL,'2027-01-01',0,'',1)")
        db.commit()


def period(db,year):
    row=db.execute('SELECT * FROM membership_periods WHERE year=?',(year,)).fetchone()
    return dict(row) if row else None


def payable(db,year):
    policy=period(db,year)
    if not policy or not policy['approved'] or policy['minimum_ore'] is None or policy['superkul_ore'] is None:
        raise ValueError(f'Kontingenten for {year} er ikkje opna. For 2027 ventar me på vedtak frå årsmøtet i 2027.' if year==2027 else f'Kontingenten for {year} er ikkje vedteken enno.')
    if year!=today().year or today()<date.fromisoformat(policy['opens_on']):
        raise ValueError(f'Betaling for {year} er ikkje open no. Opningsdato: {policy["opens_on"]}.')
    return policy


def save_period(db,values):
    try:
        year=int(values.get('year',''))
        if not 2026<=year<=2100: raise ValueError()
        minimum=amount_ore(values.get('minimum',''))
        threshold=amount_ore(values.get('threshold',''))
        if threshold<minimum: raise ValueError()
        opens=date.fromisoformat(values.get('opens_on',''))
        approved=values.get('approved')=='1'
        adopted=date.fromisoformat(values.get('approved_on','')) if approved else None
        if opens.year!=year or (approved and (adopted>today() or opens<adopted)):
            raise ValueError()
        if year==2027 and approved and adopted.year!=2027:
            raise ValueError()
    except (ValueError,TypeError):
        raise ValueError('Kontroller år, beløp og datoar. Superkul-grensa må vere minst minimumssatsen. Vedtak for 2027 må vere gjort i 2027, før opning.') from None
    old=period(db,year)
    if old and db.execute("SELECT 1 FROM signup_orders WHERE for_year=? AND environment='production' AND create_attempted=1 LIMIT 1",(year,)).fetchone():
        # Ikkje endre prisgrunnlaget for allereie oppretta reelle betalingar.
        if minimum!=old['minimum_ore'] or threshold!=old['superkul_ore']:
            raise ValueError('Satsane er låste fordi det er starta produksjonsbetalingar for året.')
    db.execute('''INSERT INTO membership_periods(year,minimum_ore,superkul_ore,opens_on,approved,approved_on)
        VALUES (?,?,?,?,?,?) ON CONFLICT(year) DO UPDATE SET minimum_ore=excluded.minimum_ore,
        superkul_ore=excluded.superkul_ore,opens_on=excluded.opens_on,approved=excluded.approved,
        approved_on=excluded.approved_on,revision=membership_periods.revision+1''',
        (year,minimum,threshold,opens.isoformat(),int(approved),adopted.isoformat() if adopted else ''))


def member_paid(db,mid,year):
    return db.execute('SELECT COALESCE(SUM(amount_ore),0)>0 FROM payments WHERE member_id=? AND for_year=?',(mid,year)).fetchone()[0]


class Renewals:
    def __init__(self,get_db): self.db=get_db

    def issue(self,mid,year,environment):
        if environment not in ('test','production'): raise ValueError('Vel test eller production.')
        token=secrets.token_urlsafe(32)
        with closing(self.db()) as db:
            db.execute('BEGIN IMMEDIATE')
            payable(db,year)
            member=db.execute('SELECT * FROM members WHERE id=? AND privacy_deleted=0',(mid,)).fetchone()
            if not member or not member['email'] or member['payment_status']=='gratis':
                raise ValueError('Medlemmen manglar e-post, er sletta eller har gratis medlemskap.')
            if member_paid(db,mid,year): raise ValueError('Kontingenten er allereie registrert som betalt for dette året.')
            # Tidlegare lenkjer blir ugyldige; pågåande ordre blir ikkje sletta.
            db.execute('UPDATE renewal_links SET revoked=1 WHERE member_id=? AND for_year=? AND environment=?',(mid,year,environment))
            lid=db.execute('INSERT INTO renewal_links(token_hash,member_id,for_year,environment,created_at) VALUES (?,?,?,?,?)',
                (hashlib.sha256(token.encode()).hexdigest(),mid,year,environment,today().isoformat())).lastrowid
            db.commit()
        return lid,token,dict(member)

    def resolve(self,token):
        if not isinstance(token,str) or not 40<=len(token)<=60: return None
        with closing(self.db()) as db:
            row=db.execute('''SELECT l.* FROM renewal_links l JOIN members m ON m.id=l.member_id
                WHERE l.token_hash=? AND l.revoked=0 AND m.privacy_deleted=0''',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
            return dict(row) if row else None

    def send(self,mid,year,environment):
        if environment!='production': raise ValueError('Testlenkjer blir ikkje sende på e-post.')
        lid,token,member=self.issue(mid,year,environment)
        origin=os.environ.get('VIPPS_PUBLIC_ORIGIN','https://bygdelista.oslobygda.no').rstrip('/')
        url=origin+'/forny/'+token
        message=EmailMessage()
        message['From']='Oslobygda kulturlag <folk@oslobygda.no>'
        message['To']=member['email'];message['Reply-To']='folk@oslobygda.no'
        message['Subject']=f'Medlemspengar i Oslobygda for {year}'
        message['Message-ID']=f'<fornying-{lid}@oslobygda.no>'
        message.set_content(f'Hei!\n\nVil du vere med i Oslobygda i {year}? Vel sjølv beløpet på den personlege betalingssida di og betal med Vipps:\n\n{url}\n\nLenkja er personleg; ikkje del henne vidare. Førre års beløp bind deg ikkje.\n\nSpørsmål? Svar på denne e-posten.\n\nHelsing Oslobygda kulturlag')
        state='failed'
        try:
            send_message(message);state='sent'
        except DeliveryUncertain:
            state='review'
        except Exception:
            state='failed'
        finally:
            with closing(self.db()) as db:
                db.execute('UPDATE renewal_links SET mail_status=? WHERE id=?',(state,lid));db.commit()
        return state


def install_renewals(app,get_db,require_admin):
    links=Renewals(get_db)
    app.extensions['renewals']=links

    def environment():
        mode=os.environ.get('VIPPS_SIGNUP_MODE','disabled')
        if mode=='production-preview':
            if not app.extensions['styre_auth_valid'](): abort(503)
            return 'production'
        if mode not in ('test','production'): abort(503)
        return mode

    @app.route('/kontingent',methods=['GET','POST'])
    @require_admin
    def annual_fees():
        error=message=None;test_url=None
        if request.method=='POST':
            try:
                action=request.form.get('action')
                if action=='save':
                    with closing(get_db()) as db:
                        db.execute('BEGIN IMMEDIATE');save_period(db,request.form);db.commit()
                    message='Kontingentåret er lagra.'
                elif action in ('link','send'):
                    mid=int(request.form.get('member_id',''));year=int(request.form.get('year',''))
                    env=environment()
                    if action=='send':
                        state=links.send(mid,year,env)
                        message={'sent':'E-posten er send.','review':'Uvisst om e-posten kom fram. Kontroller før ny sending.','failed':'E-posten vart ikkje send.'}[state]
                    else:
                        if env!='test': raise ValueError('Manuell lenkjevising er berre tilgjengeleg i testmodus. Bruk e-postsending i produksjon.')
                        _,token,_=links.issue(mid,year,env);test_url='/forny/'+token
                else: raise ValueError('Ugyldig handling.')
            except ValueError as exc: error=str(exc)
        with closing(get_db()) as db:
            policies=[dict(r) for r in db.execute('SELECT * FROM membership_periods ORDER BY year DESC')]
            members=[dict(r) for r in db.execute("SELECT id,full_name FROM members WHERE privacy_deleted=0 ORDER BY full_name")]
        return render_template('kontingent.html',policies=policies,members=members,error=error,message=message,test_url=test_url,year=today().year),400 if error else 200

    @app.route('/forny/<token>')
    def renewal_entry(token):
        link=links.resolve(token)
        if not link or link['environment']!=environment(): abort(404)
        # Tokenen blir berre bytt mot ein sesjon. Ingen betaling eller utsending på GET.
        session['renewal_link']=link['id'];session['renewal_digest']=link['token_hash']
        return redirect('/forny',code=303)

    @app.route('/forny',methods=['GET','POST'])
    def renewal_form():
        env=environment();error=None;policy=None;paid=False
        with closing(get_db()) as db:
            row=db.execute('''SELECT l.* FROM renewal_links l JOIN members m ON m.id=l.member_id
                WHERE l.id=? AND l.token_hash=? AND l.revoked=0 AND m.privacy_deleted=0''',
                (session.get('renewal_link'),session.get('renewal_digest'))).fetchone()
            if not row or row['environment']!=env: abort(404)
            link=dict(row)
            paid=bool(member_paid(db,link['member_id'],link['for_year'])) if env=='production' else False
            try: policy=payable(db,link['for_year'])
            except ValueError as exc: error=str(exc)
        if request.method=='POST' and not error and not paid:
            try:
                service=app.extensions['signup_service']
                ref=service.renew(link,request.form)
                session['signup_reference']=ref
                return redirect('/bli-medlem/status',code=303)
            except ValueError as exc: error=str(exc)
        return render_template('forny.html',environment=env,policy=policy,paid=paid,error=error,year=link['for_year']),400 if error and request.method=='POST' else 200
