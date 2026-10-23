"""Stadfest e-post, vel passord og stadfest TOTP før styretilgang vert gitt."""
import hashlib
from contextlib import contextmanager
import hmac
import os
import re
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage

import pyotp
import segno
from flask import abort, redirect, render_template, request, session
from werkzeug.security import generate_password_hash


def board_member(db, email):
    rows = db.execute('SELECT id, email, membership_type FROM members WHERE lower(trim(email))=?', (email,)).fetchall()
    return rows[0] if len(rows) == 1 and rows[0]['membership_type'] == 'styret' else None


@contextmanager
def managed_db(get_db):
    db = get_db()
    try:
        with db:
            yield db
    finally:
        db.close()


def eligible_account(user, db):
    # Konsollkontoar er eit medvite administrativt unntak for første administrator.
    if user['member_id'] is None:
        return True
    member = board_member(db, user['username'])
    return bool(member and member['id'] == user['member_id'])


def mail_ready():
    return all(os.environ.get(k, '').strip() for k in ('SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD', 'STYRE_EPOST_FRA'))


def send_code(email, code):
    message = EmailMessage()
    message['From'] = os.environ['STYRE_EPOST_FRA']
    message['To'] = email
    message['Subject'] = 'Stadfest styrekonto i Bygdelista'
    message.set_content(f'''Stadfestingskoden din er: {code}

Gå tilbake til registreringa i Bygdelista og skriv inn koden.
Koden gjeld i 15 minutt. Han gir ikkje tilgang utan passord og autentiseringsapp.

Dersom du ikkje bad om ein konto, kan du sjå bort frå denne e-posten.
''')
    port = int(os.environ.get('SMTP_PORT', '587'))
    context = ssl.create_default_context()
    if port == 465:
        smtp = smtplib.SMTP_SSL(os.environ['SMTP_HOST'], port, context=context, timeout=15)
    else:
        smtp = smtplib.SMTP(os.environ['SMTP_HOST'], port, timeout=15)
    with smtp:
        if port != 465:
            smtp.starttls(context=context)
        smtp.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
        smtp.send_message(message)


def render_account(row, error=None):
    uri = pyotp.TOTP(row['totp_secret']).provisioning_uri(
        name=row['email'], issuer_name='Bygdelista')
    # Innebygd PNG: inga ekstern teneste, ingen nøkkel i URL/loggar eller fil på disk.
    qr_image = segno.make_qr(uri, error='m').png_data_uri(scale=5, border=4)
    return render_template('styre_registrering.html', stage='account',
                           secret=row['totp_secret'], email=row['email'],
                           qr_image=qr_image, error=error)


def take_rate_limit(db, email, now):
    buckets = [('enroll-mail:' + hashlib.sha256(email.encode()).hexdigest(), 3),
               ('enroll-ip:' + (request.remote_addr or 'unknown'), 10)]
    db.execute('DELETE FROM login_limits WHERE expires<=?', (now,))
    for bucket, limit in buckets:
        row = db.execute('SELECT attempts FROM login_limits WHERE bucket=?', (bucket,)).fetchone()
        if row and row['attempts'] >= limit:
            return False
    for bucket, _ in buckets:
        db.execute('''INSERT INTO login_limits VALUES (?,1,?)
            ON CONFLICT(bucket) DO UPDATE SET attempts=attempts+1''', (bucket, now + 3600))
    return True


def install_registration(app, get_db, prefix_url):
    def pending(db):
        row = db.execute('SELECT * FROM board_enrollment WHERE id=? AND expires>? AND attempts<5',
                         (session.get('enrollment_id', ''), int(time.time()))).fetchone()
        if row:
            member = board_member(db, row['email'])
            exists = db.execute('SELECT 1 FROM board_users WHERE member_id=? OR username=?', (row['member_id'],row['email'])).fetchone()
            if member and member['id'] == row['member_id'] and not exists:
                return row
        return None

    @app.route('/registrer', methods=['GET', 'POST'])
    def board_register():
        if not mail_ready():
            return render_template('styre_registrering.html', stage='unavailable'), 503
        if request.method == 'GET':
            return render_template('styre_registrering.html', stage='email')
        email = request.form.get('email', '').strip().lower()
        if len(email) > 254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', email):
            return render_template('styre_registrering.html', stage='email', error='Skriv ei gyldig e-postadresse.'), 400
        now = int(time.time())
        identifier = secrets.token_urlsafe(32)
        code = f'{secrets.randbelow(100000000):08d}'
        should_send = False
        with managed_db(get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM board_enrollment WHERE expires<=?', (now,))
            if not take_rate_limit(db, email, now):
                db.commit()
                return render_template('styre_registrering.html', stage='email', error='For mange forsøk. Prøv igjen seinare.'), 429
            member = board_member(db, email)
            exists = db.execute('SELECT 1 FROM board_users WHERE username=? OR member_id=?', (email, member['id'] if member else -1)).fetchone()
            if member and not exists:
                db.execute('DELETE FROM board_enrollment WHERE member_id=?', (member['id'],))
                db.execute('INSERT INTO board_enrollment(id,member_id,email,code_hash,totp_secret,expires) VALUES (?,?,?,?,?,?)',
                           (identifier, member['id'], email, hashlib.sha256((identifier+code).encode()).hexdigest(), pyotp.random_base32(), now+900))
                should_send = True
            db.commit()
        session['enrollment_id'] = identifier
        if should_send:
            try:
                send_code(email, code)
            except Exception:
                # Ikkje logg kodar, e-postadresser, SMTP-passord eller leverandørmeldingar.
                app.logger.error('Sending av stadfestingskode feila. Kontroller SMTP-oppsettet.')
                with managed_db(get_db) as db:
                    db.execute('DELETE FROM board_enrollment WHERE id=?', (identifier,))
        # Same svar for ukjend adresse, eksisterande konto og leveringfeil.
        return redirect(prefix_url('board_verify_email'))

    @app.route('/registrer/stadfest', methods=['GET','POST'])
    def board_verify_email():
        if request.method == 'GET':
            return render_template('styre_registrering.html', stage='verify')
        with managed_db(get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            row = pending(db)
            code = request.form.get('email_code','')
            valid = bool(row and not row['verified'] and len(code) == 8 and code.isascii() and code.isdigit()
                         and hmac.compare_digest(row['code_hash'], hashlib.sha256((row['id']+code).encode()).hexdigest()))
            if valid:
                # Ein e-postkode kan berre stadfestast ein gong.
                db.execute('UPDATE board_enrollment SET verified=1, attempts=0 WHERE id=?', (row['id'],))
            elif row:
                db.execute('UPDATE board_enrollment SET attempts=attempts+1 WHERE id=?', (row['id'],))
            db.commit()
        if not valid:
            return render_template('styre_registrering.html', stage='verify', error='Koden er feil eller har gått ut. Start registreringa på nytt om nødvendig.'), 400
        return redirect(prefix_url('board_finish_registration'))

    @app.route('/registrer/konto', methods=['GET','POST'])
    def board_finish_registration():
        with managed_db(get_db) as db:
            if request.method == 'POST':
                db.execute('BEGIN IMMEDIATE')
            row = pending(db)
            if not row or not row['verified']:
                abort(400, 'Registreringa er ugyldig eller har gått ut. Start på nytt.')
            if request.method == 'GET':
                return render_account(row)
            password = request.form.get('password','')
            confirmation = request.form.get('confirmation','')
            code = request.form.get('code','')
            step = None
            now = int(time.time())
            if 14 <= len(password) <= 1024 and password == confirmation and len(code) == 6 and code.isascii() and code.isdigit():
                totp = pyotp.TOTP(row['totp_secret'])
                step = next((s for s in range(now//30-1, now//30+2) if hmac.compare_digest(totp.at(s*30),code)), None)
            if step is None:
                db.execute('UPDATE board_enrollment SET attempts=attempts+1 WHERE id=?', (row['id'],))
                db.commit()
                return render_account(row, error='Kontroller at passordet har minst 14 teikn, at passorda er like, og at koden frå appen er rett.'), 400
            db.execute('INSERT INTO board_users(username,password_hash,totp_secret,last_step,session_version,member_id) VALUES (?,?,?,?,?,?)',
                       (row['email'],generate_password_hash(password),row['totp_secret'],step,secrets.token_urlsafe(32),row['member_id']))
            db.execute('DELETE FROM board_enrollment WHERE member_id=?', (row['member_id'],))
            db.commit()
        session.clear()
        return render_template('styre_registrering.html', stage='done')
