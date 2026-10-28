"""Passordbyte krev e-postkode og eksisterande TOTP; gir aldri ny styretilgang."""
import hashlib
import hmac
import re
import secrets
import time

import pyotp
from flask import redirect, render_template, request, session
from werkzeug.security import generate_password_hash

from database import managed_db
from styre_registrering import eligible_account, mail_ready, send_code, take_rate_limit


def install_password_reset(app, get_db, prefix_url):
    @app.route('/gløymt-passord', methods=['GET', 'POST'])
    def forgot_password():
        if not mail_ready():
            return render_template('passord_reset.html', stage='unavailable'), 503
        if request.method == 'GET':
            return render_template('passord_reset.html', stage='email')
        email = request.form.get('email', '').strip().casefold()
        if len(email) > 100 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', email):
            return render_template('passord_reset.html', stage='email', error='Skriv ei gyldig e-postadresse.'), 400
        now = int(time.time())
        identifier = secrets.token_urlsafe(32)
        code = f'{secrets.randbelow(100000000):08d}'
        should_send = False
        with managed_db(get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM board_password_reset WHERE expires<=?', (now,))
            if not take_rate_limit(db, 'password-reset:' + email, now):
                return render_template('passord_reset.html', stage='email', error='For mange forsøk. Prøv igjen seinare.'), 429
            user = db.execute('SELECT * FROM board_users WHERE username=? AND active=1', (email,)).fetchone()
            if user and eligible_account(user, db):
                # Avgrensa tal rader; ei ny førespurnad opphevar den førre koden.
                db.execute('DELETE FROM board_password_reset WHERE username=?', (email,))
                db.execute('INSERT INTO board_password_reset(id,username,code_hash,session_version,expires) VALUES (?,?,?,?,?)',
                           (identifier, email, hashlib.sha256((identifier + code).encode()).hexdigest(), user['session_version'], now + 900))
                should_send = True
        session['password_reset_id'] = identifier
        if should_send:
            try:
                send_code(email, code, password_reset=True)
            except Exception:
                app.logger.error('Sending av passordkode feila. Kontroller SMTP-oppsettet.')
                with managed_db(get_db) as db:
                    db.execute('DELETE FROM board_password_reset WHERE id=?', (identifier,))
        # Same svar for ukjende/sperra kontoar og leveringsfeil.
        return redirect(prefix_url('reset_password'))

    @app.route('/gløymt-passord/byt', methods=['GET', 'POST'])
    def reset_password():
        if request.method == 'GET':
            return render_template('passord_reset.html', stage='reset')
        now = int(time.time())
        password = request.form.get('password', '')
        email_code = request.form.get('email_code', '')
        code = request.form.get('code', '')
        matched = None
        with managed_db(get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM board_password_reset WHERE id=? AND expires>? AND attempts<5',
                             (session.get('password_reset_id', ''), now)).fetchone()
            user = db.execute('SELECT * FROM board_users WHERE username=? AND active=1', (row['username'],)).fetchone() if row else None
            valid = (user and eligible_account(user, db)
                     and hmac.compare_digest(row['session_version'], user['session_version'])
                     and 14 <= len(password) <= 1024
                     and password == request.form.get('confirmation', '')
                     and len(email_code) == 8 and email_code.isascii() and email_code.isdigit()
                     and hmac.compare_digest(row['code_hash'], hashlib.sha256((row['id'] + email_code).encode()).hexdigest()))
            if valid and len(code) == 6 and code.isascii() and code.isdigit():
                totp = pyotp.TOTP(user['totp_secret'])
                matched = next((step for step in range(now // 30 - 1, now // 30 + 2)
                                if step > user['last_step'] and hmac.compare_digest(totp.at(step * 30), code)), None)
            if matched is None:
                if row:
                    db.execute('UPDATE board_password_reset SET attempts=attempts+1 WHERE id=?', (row['id'],))
                return render_template('passord_reset.html', stage='reset', error='Kontroller kodane og at passorda er like og har minst 14 teikn. Kodane kan ha gått ut; start på nytt etter fem forsøk.'), 400
            db.execute('UPDATE board_users SET password_hash=?,last_step=?,session_version=? WHERE username=?',
                       (generate_password_hash(password), matched, secrets.token_urlsafe(32), user['username']))
            db.execute('DELETE FROM board_password_reset WHERE username=?', (user['username'],))
            db.execute('DELETE FROM login_limits WHERE bucket=?', ('user:' + hashlib.sha256(user['username'].encode()).hexdigest(),))
        session.clear()
        return render_template('passord_reset.html', stage='done')
