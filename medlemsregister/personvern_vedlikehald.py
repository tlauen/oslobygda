"""Friststyrt ordreopprydding og styregodkjend medlemssletting."""

from datetime import date, datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate
import hashlib
import hmac
import json
import os
import secrets
import time

from flask import abort, redirect, render_template, request
from database import managed_db
from epost import send_message, DeliveryUncertain
from personvern import erase_member

DAY = 86400


def init_retention(get_db, active_year):
    with managed_db(get_db) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS free_membership_years (
                member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
                for_year INTEGER NOT NULL, approved_at TEXT NOT NULL,
                PRIMARY KEY(member_id,for_year)
            );
            CREATE TABLE IF NOT EXISTS paid_membership_years (
                member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
                for_year INTEGER NOT NULL, approved_at TEXT NOT NULL,
                PRIMARY KEY(member_id,for_year)
            );
            CREATE TABLE IF NOT EXISTS privacy_candidates (
                member_id INTEGER PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,
                fingerprint TEXT NOT NULL, notified_at REAL
            );
            CREATE TABLE IF NOT EXISTS board_notifications (
                event_key TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending', claimed_at REAL NOT NULL DEFAULT 0,
                claim_token TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL
            );
        """)
        db.execute('BEGIN IMMEDIATE')
        # Ein gong: den eksisterande gratisstatusen gjeld det aktive medlemsåret.
        # Ikkje forny gratis medlemskap automatisk ved seinare oppstartar.
        if not db.execute("SELECT 1 FROM app_settings WHERE key='free_years_migrated'").fetchone():
            db.execute("""INSERT OR IGNORE INTO free_membership_years
                SELECT id,?,? FROM members WHERE payment_status='gratis' AND privacy_deleted=0""",
                (active_year(db), datetime.now(timezone.utc).isoformat()))
            db.execute("""INSERT OR IGNORE INTO paid_membership_years
                SELECT id,?,? FROM members WHERE payment_status='betalt' AND privacy_deleted=0""",
                (active_year(db), datetime.now(timezone.utc).isoformat()))
            db.execute("INSERT INTO app_settings VALUES ('free_years_migrated','1')")


def approve_free(db, mid, year):
    approve_year(db, mid, year, 'gratis')


def approve_year(db, mid, year, status):
    tables = {'gratis': 'free_membership_years', 'betalt': 'paid_membership_years'}
    if status not in tables:
        raise ValueError('Ugyldig medlemsstatus.')
    if not db.execute("SELECT 1 FROM members WHERE id=? AND privacy_deleted=0", (mid,)).fetchone():
        raise ValueError("Medlemmen finst ikkje.")
    other = tables['betalt' if status == 'gratis' else 'gratis']
    db.execute(f'DELETE FROM {other} WHERE member_id=? AND for_year=?', (mid,year))
    db.execute(f"INSERT OR IGNORE INTO {tables[status]} VALUES (?,?,?)",
               (mid, year, datetime.now(timezone.utc).isoformat()))
    db.execute("DELETE FROM privacy_candidates WHERE member_id=?", (mid,))


def candidates(db, today):
    """To heile kalenderår utan dekning: sist dekt 2026 -> tidlegast 1.1.2029."""
    result = []
    for row in db.execute("SELECT * FROM members WHERE privacy_deleted=0 ORDER BY full_name,id"):
        member = dict(row)
        paid = db.execute("""SELECT MAX(for_year) FROM (
            SELECT for_year FROM payments WHERE member_id=? GROUP BY for_year HAVING SUM(amount_ore)>0
            UNION SELECT for_year FROM free_membership_years WHERE member_id=?
            UNION SELECT for_year FROM paid_membership_years WHERE member_id=?)""",
            (row['id'], row['id'], row['id'])).fetchone()[0]
        # Nyregistrerte utan betaling får minst like lang frist som andre.
        try:
            joined = date.fromisoformat(row['created_at'][:10]).year
        except (ValueError, TypeError):
            continue  # Ukjend alder på oppføringa må avklarast manuelt.
        anchor = max(paid or joined, joined)
        if today.year < anchor + 3:
            continue
        if db.execute("""SELECT 1 FROM board_users WHERE member_id=? AND active=1
            OR (lower(trim(username))=lower(trim(?)) AND active=1)""", (row['id'], row['email'])).fetchone():
            continue  # Ikkje fjern aktiv styretilgang gjennom ein oppryddingsjobb.
        blocked = db.execute("""SELECT 1 FROM signup_orders WHERE environment='production'
            AND (member_id=? OR renewal_member_id=? OR (email<>'' AND lower(trim(email))=lower(trim(?))))
            AND (status NOT IN ('complete','ABORTED','EXPIRED','TERMINATED','redacted')
                 OR confirmation_status IN ('sending','review'))""", (row['id'], row['id'], row['email'])).fetchone()
        if blocked:
            continue
        member['last_covered'] = paid
        member['eligible_on'] = f'{anchor + 3}-01-01'
        member['fingerprint'] = hashlib.sha256(json.dumps(
            [row['id'], paid, row['updated_at'], row['full_name'], row['email'], anchor],
            ensure_ascii=True).encode()).hexdigest()
        result.append(member)
    return result


def enqueue(db, key, kind, payload, now):
    db.execute("INSERT OR IGNORE INTO board_notifications(event_key,kind,payload,created_at) VALUES (?,?,?,?)",
               (key, kind, json.dumps(payload), now))


def prepare(get_db, today, now=None):
    now = time.time() if now is None else now
    with managed_db(get_db) as db:
        db.execute('BEGIN IMMEDIATE')
        # Ukjent betalingsutfall blir aldri anonymisert. Terminalstatus er verifisert av Vipps-flyten.
        cleaned = db.execute("""UPDATE signup_orders SET details='{}',email='',browser_key='',
            payer_name='',payer_phone='',redirect_url=NULL,consent_at='',newsletter=0,
            newsletter_done=1,confirmation_status='skipped',status='redacted',problem='',
            member_id=NULL,renewal_member_id=NULL,renewal_link_id=NULL,lease_token=NULL,lease_until=0
            WHERE created_at<? AND (status IN ('ABORTED','EXPIRED','TERMINATED')
                OR (status='new' AND create_attempted=0)) AND lease_until<?
                AND member_id IS NULL AND payment_id IS NULL AND confirmation_status NOT IN ('sending','review')""",
            (now - 30 * DAY, now)).rowcount
        for row in db.execute("""SELECT reference,status,problem,confirmation_status FROM signup_orders
            WHERE environment='production' AND (status='review' OR confirmation_status='review'
                OR (confirmation_status='sending' AND confirmation_started_at<?)
                OR (created_at<? AND create_attempted=1 AND status NOT IN
                    ('complete','ABORTED','EXPIRED','TERMINATED','redacted')))""", (now-3600, now-30*DAY)):
            digest = hashlib.sha256(json.dumps(list(row)).encode()).hexdigest()
            enqueue(db, 'review:' + digest, 'review', {'reference': row['reference']}, now)
        current = candidates(db, today)
        live = {m['id'] for m in current}
        for old in db.execute('SELECT member_id FROM privacy_candidates').fetchall():
            if old[0] not in live:
                db.execute('DELETE FROM privacy_candidates WHERE member_id=?', (old[0],))
        changes = []
        for member in current:
            old = db.execute('SELECT * FROM privacy_candidates WHERE member_id=?', (member['id'],)).fetchone()
            if not old or old['fingerprint'] != member['fingerprint']:
                db.execute("""INSERT INTO privacy_candidates VALUES (?,?,NULL)
                    ON CONFLICT(member_id) DO UPDATE SET fingerprint=excluded.fingerprint,notified_at=NULL""",
                    (member['id'], member['fingerprint']))
                changes.append([member['id'], member['fingerprint']])
        if changes:
            digest = hashlib.sha256(json.dumps(changes).encode()).hexdigest()
            enqueue(db, 'deletions:' + digest + ':' + secrets.token_hex(8), 'deletions', changes, now)
        # Eit avbrote SMTP-forsøk kan ha levert. Ikkje send automatisk dobbelt.
        db.execute("UPDATE board_notifications SET state='uncertain' WHERE state='sending' AND claimed_at<?", (now-3600,))
    return cleaned


def message_for(db, item, today):
    origin = os.environ.get('VIPPS_PUBLIC_ORIGIN', 'https://bygdelista.oslobygda.no').rstrip('/')
    payload = json.loads(item['payload'])
    message = EmailMessage()
    message['From'] = 'Oslobygda kulturlag <folk@oslobygda.no>'
    message['To'] = 'folk@oslobygda.no'
    message['Date'] = formatdate(usegmt=True)
    digest = hashlib.sha256(item['event_key'].encode()).hexdigest()
    message['Message-ID'] = f'<styrevarsel-{digest}@oslobygda.no>'
    notified = []
    if item['kind'] == 'review':
        row = db.execute('SELECT * FROM signup_orders WHERE reference=?', (payload['reference'],)).fetchone()
        if not row or not (row['status'] == 'review' or row['confirmation_status'] == 'review'
                or (row['confirmation_status'] == 'sending' and row['confirmation_started_at'] < time.time()-3600)
                or (row['created_at'] < time.time()-30*DAY and row['create_attempted'] and row['status'] not in ('complete','ABORTED','EXPIRED','TERMINATED','redacted'))):
            return None, []
        message['Subject'] = 'Innmelding krev manuell kontroll – Bygdelista'
        message.set_content(f"Ei innmelding krev manuell kontroll.\n\nReferanse: {row['reference']}\n"
            f"Medlemsår: {row['for_year']}\nBeløp: {row['amount_ore']/100:.2f} kr\n"
            f"Status: {row['status']}\nStadfestingsmail: {row['confirmation_status']}\n"
            f"Merknad: {row['problem']}\n\nKontroller opplysningane i Bygdelista og faktisk trekt/refundert beløp i Vipps.\n"
            f"{origin}/innmeldingar\n\nIngen automatisk sletting er utført for denne ordren.")
    else:
        eligible = {m['id']: m for m in candidates(db, today)}
        names = []
        for mid, fingerprint in payload:
            member = eligible.get(mid)
            snapshot = db.execute('SELECT * FROM privacy_candidates WHERE member_id=?', (mid,)).fetchone()
            if member and snapshot and snapshot['fingerprint'] == fingerprint == member['fingerprint']:
                names.append(f"- {member['full_name']} (medlemsnummer {mid}); sist dekt medlemsår: {member['last_covered'] or 'ingen registrert'}")
                notified.append([mid, fingerprint])
        if not names:
            return None, []
        message['Subject'] = 'Godkjenn sletting av tidlegare medlemmar – Bygdelista'
        message.set_content('Desse medlemmane har vore utan betalt eller godkjent gratis medlemskap i to heile kalenderår:\n\n'
            + '\n'.join(names) + f'\n\nIngen er sletta. Logg inn i Bygdelista, kontroller lista og godkjenn kvar sletting:\n{origin}/personvern-oppfolging\n\n'
            'Ny betaling eller nytt gratisvedtak før godkjenning stoppar slettinga. Ikkje vidaresend denne namnelista unødig.')
    return message, notified


def send_pending(get_db, today, sender=None):
    sender = sender or send_message
    if not all(os.environ.get(k) for k in ('SMTP_HOST','SMTP_USER','SMTP_PASSWORD')):
        return 0
    with managed_db(get_db) as db:
        keys = [r[0] for r in db.execute("SELECT event_key FROM board_notifications WHERE state='pending' ORDER BY created_at LIMIT 100")]
    sent = 0
    for key in keys:
        token = secrets.token_urlsafe(24)
        with managed_db(get_db) as db:
            claimed = db.execute("UPDATE board_notifications SET state='sending',claim_token=?,claimed_at=? WHERE event_key=? AND state='pending'",
                                 (token, time.time(), key))
            if not claimed.rowcount:
                continue
            item = dict(db.execute('SELECT * FROM board_notifications WHERE event_key=?', (key,)).fetchone())
            message, notified = message_for(db, item, today)
        state = 'sent'
        try:
            if message is not None:
                sender(message)
                sent += 1
        except DeliveryUncertain:
            state = 'uncertain'
        except Exception:
            state = 'pending'  # Neste timelege jobb prøver ei avvist sending igjen.
        with managed_db(get_db) as db:
            changed = db.execute('UPDATE board_notifications SET state=? WHERE event_key=? AND claim_token=? AND state=\'sending\'', (state, key, token))
            if changed.rowcount and state == 'sent' and message is not None:
                for mid, fingerprint in notified:
                    db.execute('UPDATE privacy_candidates SET notified_at=? WHERE member_id=? AND fingerprint=?', (time.time(), mid, fingerprint))
    return sent


def approve_deletion(db, mid, fingerprint, today):
    snapshot = db.execute('SELECT * FROM privacy_candidates WHERE member_id=?', (mid,)).fetchone()
    current = next((m for m in candidates(db, today) if m['id'] == mid), None)
    if not snapshot or not snapshot['notified_at'] or not current or not hmac.compare_digest(
            snapshot['fingerprint'], fingerprint) or not hmac.compare_digest(current['fingerprint'], fingerprint):
        raise ValueError('Lista er endra, medlemmen er ikkje lenger aktuell, eller e-postvarselet er ikkje sendt. Last sida på nytt.')
    result, status = erase_member(db, mid)
    if status != 200:
        raise ValueError(result['error'])
    db.execute('DELETE FROM privacy_candidates WHERE member_id=?', (mid,))
    # Fjern gamle kømeldingar som kan innehalde denne medlemmen sin identifikator.
    # Utsende e-postar har si eiga oppbevaring hos laget.
    return result['message']


def install_retention(app, get_db, require_admin):
    from kontingent import today

    @app.route('/personvern-oppfolging', methods=['GET','POST'])
    @require_admin
    def privacy_followup():
        error = message = None
        if request.method == 'POST':
            try:
                if request.form.get('action') == 'delete':
                    if request.form.get('confirm') != '1':
                        raise ValueError('Stadfest at du har kontrollert medlemskapen før sletting.')
                    with managed_db(get_db) as db:
                        db.execute('BEGIN IMMEDIATE')
                        message = approve_deletion(db, int(request.form['member_id']), request.form.get('fingerprint',''), today())
                elif request.form.get('action') == 'retry':
                    with managed_db(get_db) as db:
                        db.execute("UPDATE board_notifications SET state='pending' WHERE event_key=? AND state='uncertain'", (request.form.get('event_key',''),))
                    message = 'Varslet er køa for nytt forsøk. Det kan vere levert frå før.'
                else:
                    abort(400)
            except (ValueError, KeyError) as exc:
                error = str(exc)
        with managed_db(get_db) as db:
            rows = []
            for member in candidates(db, today()):
                snapshot = db.execute('SELECT * FROM privacy_candidates WHERE member_id=? AND fingerprint=?', (member['id'], member['fingerprint'])).fetchone()
                if snapshot:
                    member['notified'] = bool(snapshot['notified_at'])
                    rows.append(member)
            notifications = [dict(r) for r in db.execute("SELECT event_key,kind,state FROM board_notifications WHERE state<>'sent' ORDER BY created_at")]
        return render_template('personvern_oppfolging.html', candidates=rows, notifications=notifications, error=error, message=message), 400 if error else 200
