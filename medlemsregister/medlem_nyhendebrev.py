"""Varige, uttrykkelege nyhendebrevval frå Mi side. Berre namn/e-post til Brevo."""

from datetime import datetime, timezone
import os
import secrets
import time
from urllib.parse import quote

from database import managed_db
from medlem_auth import access_row


def queue(db, mid, email, desired):
    email=email.strip().casefold()
    db.execute('''INSERT INTO member_newsletter_jobs(email,member_id,desired,revision,created_at)
        VALUES (?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET member_id=excluded.member_id,
        desired=excluded.desired,revision=excluded.revision,created_at=excluded.created_at''',
        (email,mid,int(desired),secrets.token_urlsafe(24),time.time()))


def choose(db, member, desired):
    access_row(db,member['id'])
    db.execute('UPDATE member_access SET newsletter=?,newsletter_consent_at=? WHERE member_id=?',
        (int(desired),datetime.now(timezone.utc).isoformat(),member['id']))
    # Gamle signup-jobbar får ikkje overstyre eit nyare, uttrykkeleg val.
    db.execute('UPDATE signup_orders SET newsletter_done=1 WHERE member_id=? OR renewal_member_id=?',(member['id'],member['id']))
    queue(db,member['id'],member['email'],desired)


def sync_contact(api, email, desired, member):
    key=os.environ.get('BREVO_API_KEY','').strip()
    list_id=os.environ.get('BREVO_INNMELDING_LIST_ID') or os.environ.get('BREVO_LIST_ID','')
    if not key or not str(list_id).isdigit():return False
    if desired == 2:
        status,_=api('PUT','/contacts/'+quote(email,safe=''),key,{'attributes':{'FIRSTNAME':member['fornamn'] or '','LASTNAME':member['etternamn'] or ''}})
        return status in (200,204,404)
    if desired:
        # Berre ein ny, uttrykkeleg påmelding på Mi side kan oppheve avmelding.
        status,_=api('POST','/contacts',key,{'email':email,'attributes':{'FIRSTNAME':member['fornamn'] or '',
            'LASTNAME':member['etternamn'] or ''},'listIds':[int(list_id)],'updateEnabled':True,'emailBlacklisted':False})
        return status in (200,201,204)
    status,_=api('PUT','/contacts/'+quote(email,safe=''),key,{'unlinkListIds':[int(list_id)]})
    return status in (200,204,404)


def process(get_db, api):
    with managed_db(get_db) as db:
        jobs=[dict(row) for row in db.execute('SELECT * FROM member_newsletter_jobs WHERE lease_until<? ORDER BY created_at LIMIT 100',(time.time(),))]
    done=0
    for job in jobs:
        claim=secrets.token_urlsafe(24)
        with managed_db(get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('''UPDATE member_newsletter_jobs SET lease_until=?,lease_token=?
                WHERE email=? AND revision=? AND lease_until<?''',(time.time()+120,claim,job['email'],job['revision'],time.time())).rowcount:
                continue
            member=db.execute('SELECT * FROM members WHERE id=? AND privacy_deleted=0',(job['member_id'],)).fetchone()
            # Ei gammal avmelding skal ikkje endre ein annan medlem sin adresse som seinare er teken i bruk.
            reassigned=db.execute('SELECT 1 FROM members WHERE lower(trim(email))=? AND id<>? AND privacy_deleted=0',
                                  (job['email'],job['member_id'])).fetchone()
            discard=not member or reassigned or (job['desired'] and member['email'].strip().casefold()!=job['email'])
            if discard:
                db.execute('DELETE FROM member_newsletter_jobs WHERE email=? AND lease_token=?',(job['email'],claim))
                continue
            member=dict(member)
        success=False
        try:
            success=sync_contact(api,job['email'],job['desired'],member)
        except Exception:
            pass  # Varig kø; ikkje logg adresser eller leverandørsvar.
        with managed_db(get_db) as db:
            live=db.execute('SELECT 1 FROM members WHERE id=? AND privacy_deleted=0',(job['member_id'],)).fetchone()
            if not live:
                # Sletting kan ha skjedd medan Brevo tok imot eit upsert-kall.
                db.execute('INSERT OR IGNORE INTO privacy_jobs(email,created_at) VALUES (?,?)',(job['email'],time.time()))
            if success:
                done+=db.execute('DELETE FROM member_newsletter_jobs WHERE email=? AND revision=? AND lease_token=?',
                    (job['email'],job['revision'],claim)).rowcount
            db.execute('UPDATE member_newsletter_jobs SET lease_until=0,lease_token=\'\' WHERE email=? AND lease_token=?',(job['email'],claim))
    return done
