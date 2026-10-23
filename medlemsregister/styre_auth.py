"""Personlege styrekontoar med passord og TOTP. Stadfesta registrering for styremedlemmar."""
import hashlib
import hmac
import secrets
import time

import click
import pyotp
from flask import abort, redirect, render_template, request, session
from styre_registrering import install_registration, eligible_account, managed_db
from werkzeug.security import check_password_hash, generate_password_hash


def init_auth_db(get_db):
    with managed_db(get_db) as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS board_users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                totp_secret TEXT NOT NULL,
                last_step INTEGER NOT NULL DEFAULT -1,
                session_version TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS login_limits (
                bucket TEXT PRIMARY KEY,
                attempts INTEGER NOT NULL,
                expires INTEGER NOT NULL
            );
        ''')
        columns = {row[1] for row in db.execute('PRAGMA table_info(board_users)')}
        if 'member_id' not in columns:
            db.execute('ALTER TABLE board_users ADD COLUMN member_id INTEGER')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_board_member ON board_users(member_id) WHERE member_id IS NOT NULL')
        db.execute("""CREATE TABLE IF NOT EXISTS board_enrollment (
            id TEXT PRIMARY KEY, member_id INTEGER NOT NULL, email TEXT NOT NULL,
            code_hash TEXT NOT NULL, totp_secret TEXT NOT NULL, expires INTEGER NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0, verified INTEGER NOT NULL DEFAULT 0
        )""")


def install_auth(app, get_db, prefix_url):
    dummy_hash = generate_password_hash(secrets.token_urlsafe(32))

    def valid_session():
        username = session.get('board_username')
        version = session.get('board_version')
        logged_in_at = session.get('board_logged_in_at', 0)
        if not username or not version or not 0 <= time.time() - logged_in_at < 8 * 3600:
            return False
        with managed_db(get_db) as db:
            row = db.execute('SELECT * FROM board_users WHERE username=? AND active=1', (username,)).fetchone()
            return bool(row and eligible_account(db=db, user=row) and hmac.compare_digest(row['session_version'], version))

    app.extensions['styre_auth_valid'] = valid_session

    def csrf_token():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_urlsafe(32)
        return session['csrf_token']

    app.jinja_env.globals['csrf_token'] = csrf_token

    @app.before_request
    def protect_changes():
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.endpoint != 'api_innmelding':
            expected = session.get('csrf_token', '')
            supplied = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token', '')
            if not expected or not hmac.compare_digest(expected.encode(), supplied.encode()):
                abort(400, 'Ugyldig skjema. Last sida på nytt.')

    @app.after_request
    def private_responses(response):
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'GET':
            return render_template('innlogging.html')
        username = request.form.get('username', '').strip().casefold()[:100]
        password = request.form.get('password', '')
        code = request.form.get('code', '')
        now = int(time.time())
        # Vedvarande, delt mellom web workers. Ikkje stol på vilkårlege proxy-headerar.
        buckets = ['user:' + hashlib.sha256(username.encode()).hexdigest(),
                   'ip:' + (request.remote_addr or 'unknown')]
        error = 'Feil brukarnamn, passord eller eingongskode.'
        with managed_db(get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM login_limits WHERE expires <= ?', (now,))
            for bucket, maximum in zip(buckets, (5, 30)):
                row = db.execute('SELECT attempts FROM login_limits WHERE bucket=?', (bucket,)).fetchone()
                if row and row['attempts'] >= maximum:
                    db.commit()
                    return render_template('innlogging.html', error='For mange forsøk. Vent fem minutt og prøv igjen.'), 429
            for bucket in buckets:
                db.execute('''INSERT INTO login_limits VALUES (?, 1, ?)
                    ON CONFLICT(bucket) DO UPDATE SET attempts=attempts+1''', (bucket, now + 300))
            user = db.execute('SELECT * FROM board_users WHERE username=? AND active=1', (username,)).fetchone()
            password_ok = check_password_hash(user['password_hash'] if user else dummy_hash, password[:1024]) and len(password) <= 1024
            matched = None
            if user and eligible_account(db=db, user=user) and password_ok and len(code) == 6 and code.isascii() and code.isdigit():
                totp = pyotp.TOTP(user['totp_secret'])
                for step in range(now // 30 - 1, now // 30 + 2):
                    if step > user['last_step'] and hmac.compare_digest(totp.at(step * 30), code):
                        matched = step
                        break
            if matched is None:
                db.commit()
                return render_template('innlogging.html', error=error), 401
            db.execute('UPDATE board_users SET last_step=? WHERE username=?', (matched, username))
            db.execute('DELETE FROM login_limits WHERE bucket=?', (buckets[0],))
            db.commit()
        session.clear()
        session.permanent = True
        session['board_username'] = username
        session['board_version'] = user['session_version']
        session['board_logged_in_at'] = now
        return redirect(prefix_url('index'))

    @app.route('/logout', methods=['POST'])
    def logout():
        session.clear()
        return redirect(prefix_url('login'))

    install_registration(app, get_db, prefix_url)

    @app.cli.command('styrekonto')
    @click.argument('username')
    @click.option('--sperr', is_flag=True, help='Sperr konto og eksisterande innloggingar.')
    @click.option('--nullstill', is_flag=True, help='Byt passord og autentiseringsnøkkel for eksisterande konto.')
    def manage_user(username, sperr, nullstill):
        """Opprett ein konto, nullstill ved mista telefon, eller sperr tilgang."""
        init_auth_db(get_db)
        username = username.strip().casefold()
        if not username or len(username) > 100 or (sperr and nullstill):
            raise click.ClickException('Ugyldig brukarnamn eller kombinasjon av val.')
        with managed_db(get_db) as db:
            exists = db.execute('SELECT 1 FROM board_users WHERE username=?', (username,)).fetchone()
            if sperr:
                if not exists:
                    raise click.ClickException('Kontoen finst ikkje.')
                db.execute('UPDATE board_users SET active=0, session_version=? WHERE username=?', (secrets.token_urlsafe(32), username))
                click.echo('Tilgangen er sperra.')
                return
            if bool(exists) != nullstill:
                raise click.ClickException('Bruk --nullstill for eksisterande konto; utan flagg for ny konto.')
        password = click.prompt('Nytt personleg passord (minst 14 teikn)', hide_input=True, confirmation_prompt=True)
        if len(password) < 14 or len(password) > 1024:
            raise click.ClickException('Passordet må ha mellom 14 og 1024 teikn.')
        secret = pyotp.random_base32()
        click.echo('Legg til tidsbasert kode i autentiseringsappen. Hald nøkkelen hemmeleg:')
        click.echo('Konto: Bygdelista / ' + username)
        click.echo('Oppsettsnøkkel: ' + secret)
        code = click.prompt('Stadfest med sekssifra kode frå appen', hide_input=True)
        now = int(time.time())
        totp = pyotp.TOTP(secret)
        step = next((s for s in range(now // 30 - 1, now // 30 + 2) if hmac.compare_digest(totp.at(s * 30), code)), None)
        if step is None:
            raise click.ClickException('Feil kode. Kontoen vart ikkje endra.')
        with managed_db(get_db) as db:
            values = (generate_password_hash(password), secret, step, secrets.token_urlsafe(32), username)
            if nullstill:
                db.execute('UPDATE board_users SET password_hash=?, totp_secret=?, last_step=?, session_version=?, active=1 WHERE username=?', values)
            else:
                db.execute('INSERT INTO board_users(password_hash,totp_secret,last_step,session_version,username) VALUES (?,?,?,?,?)', values)
        click.echo('Kontoen er klar. Vent til neste eingongskode før innlogging.')
