"""Medlemstilgang med nettlesarbundne eingongskodar. Gir aldri styretilgang."""

from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate
import hashlib
import hmac
import re
import secrets
import time

from database import managed_db
from epost import send_message

TTL = 600
SESSION_TTL = 8 * 3600


def clean_email(value):
    email = value.strip().casefold()
    if len(email) > 254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', email):
        raise ValueError('Skriv ei gyldig e-postadresse.')
    return email


def init_member_access(get_db):
    with managed_db(get_db) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS member_access (
                member_id INTEGER PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,
                version TEXT NOT NULL, newsletter INTEGER, newsletter_consent_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS member_challenges (
                id TEXT PRIMARY KEY, member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
                purpose TEXT NOT NULL, email TEXT NOT NULL, previous_email TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL, code_hash TEXT NOT NULL, extra_hash TEXT NOT NULL DEFAULT '',
                expires REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS member_challenge_member ON member_challenges(member_id);
            CREATE TABLE IF NOT EXISTS member_newsletter_jobs (
                email TEXT PRIMARY KEY, member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
                desired INTEGER NOT NULL, revision TEXT NOT NULL,
                lease_until REAL NOT NULL DEFAULT 0, lease_token TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL
            );
        """)


def revoke_access(db, mid):
    db.execute('UPDATE member_access SET version=? WHERE member_id=?', (secrets.token_urlsafe(32), mid))
    db.execute('DELETE FROM member_challenges WHERE member_id=?', (mid,))


def access_row(db, mid):
    db.execute('INSERT OR IGNORE INTO member_access(member_id,version) VALUES (?,?)', (mid, secrets.token_urlsafe(32)))
    return db.execute('SELECT * FROM member_access WHERE member_id=?', (mid,)).fetchone()


def send_code(email, code, purpose):
    message = EmailMessage()
    message['From'] = 'Oslobygda kulturlag <folk@oslobygda.no>'
    message['To'] = email
    message['Subject'] = 'Innloggingskode til Mi side' if purpose == 'login' else 'Stadfest byte av e-post på Mi side'
    message['Date'] = formatdate(usegmt=True)
    instruction = 'Skriv koden i nettlesaren der du bad om innlogging.' if purpose == 'login' else 'Skriv koden i det tilsvarande feltet på Mi side for å stadfeste e-postbytet.'
    message.set_content(f'Koden din er: {code}\n\n{instruction}\nKoden gjeld i 10 minutt og kan berre brukast éin gong.\n\n'
        'Me sender ingen innloggingslenkje. Ikkje del koden med andre, heller ikkje nokon som seier dei er frå laget.\n'
        'Dersom du ikkje bad om dette, kan du sjå bort frå meldinga.\n\nHelsing Oslobygda kulturlag')
    send_message(message)


class MemberAuth:
    def __init__(self, app, get_db):
        self.app, self.db = app, get_db

    def digest(self, purpose, value):
        key = self.app.secret_key
        key = key.encode() if isinstance(key, str) else key
        return hmac.new(key, (purpose + ':' + value).encode(), hashlib.sha256).hexdigest()

    def limits(self, db, email, ip, now, extra=None):
        buckets = [('member-mail:' + self.digest('address',email),3,900),
                   ('member-ip:' + ip,20,3600)]
        if extra is not None:
            buckets.append(('member-change:' + str(extra),3,900))
        db.execute('DELETE FROM login_limits WHERE expires<=?', (now,))
        if any((row := db.execute('SELECT attempts FROM login_limits WHERE bucket=?',(key,)).fetchone()) and row[0]>=maximum for key,maximum,_ in buckets):
            return False
        for key,_,duration in buckets:
            db.execute('INSERT INTO login_limits VALUES (?,1,?) ON CONFLICT(bucket) DO UPDATE SET attempts=attempts+1', (key,now+duration))
        return True

    def start(self, email, ip):
        email = clean_email(email)
        identifier = secrets.token_urlsafe(32)
        code = f'{secrets.randbelow(100000000):08d}'
        now = time.time()
        recipient = None
        with managed_db(self.db) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM member_challenges WHERE expires<=?', (now,))
            if not self.limits(db,email,ip,now):
                raise ValueError('For mange forsøk. Vent litt før du prøver igjen.')
            members = db.execute('SELECT id,email FROM members WHERE lower(trim(email))=? AND privacy_deleted=0',(email,)).fetchall()
            if len(members) == 1:
                member = members[0]
                access = access_row(db,member['id'])
                db.execute('INSERT INTO member_challenges(id,member_id,purpose,email,version,code_hash,expires) VALUES (?,?,?,?,?,?,?)',
                    (identifier,member['id'],'login',email,access['version'],self.digest('login',identifier+code),now+TTL))
                recipient = email
        if recipient:
            try:
                send_code(recipient,code,'login')
            except Exception:
                self.app.logger.warning('Sending av medlemskode kunne ikkje stadfestast. Ingen kode eller adresse er logga.')
                with managed_db(self.db) as db:
                    db.execute('DELETE FROM member_challenges WHERE id=?',(identifier,))
        # Same flyt for ukjend adresse, delt adresse og SMTP-feil.
        return identifier

    def verify(self, identifier, code):
        now=time.time()
        with managed_db(self.db) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("""SELECT c.*,m.email AS current_email,m.privacy_deleted,a.version AS current_version
                FROM member_challenges c JOIN members m ON m.id=c.member_id JOIN member_access a ON a.member_id=m.id
                WHERE c.id=? AND c.purpose='login'""", (identifier,)).fetchone()
            if not row:
                return None
            db.execute('UPDATE member_challenges SET attempts=attempts+1 WHERE id=?',(identifier,))
            if row['expires']<=now or row['attempts']>=5 or row['privacy_deleted'] or row['email']!=row['current_email'].strip().casefold() or row['version']!=row['current_version']:
                return None
            if not re.fullmatch(r'[0-9]{8}',code) or not hmac.compare_digest(row['code_hash'],self.digest('login',identifier+code)):
                return None
            db.execute("DELETE FROM member_challenges WHERE member_id=? AND purpose='login'",(row['member_id'],))
            return row['member_id'],row['version']

    def member(self, session):
        mid=session.get('member_id')
        age=time.time()-session.get('member_logged_at',0)
        if not isinstance(mid,int) or not 0<=age<SESSION_TTL:
            return None
        with managed_db(self.db) as db:
            row=db.execute('''SELECT m.*,a.version,a.newsletter,a.newsletter_consent_at FROM members m
                JOIN member_access a ON a.member_id=m.id WHERE m.id=? AND m.privacy_deleted=0''',(mid,)).fetchone()
            if row and hmac.compare_digest(row['version'],session.get('member_version','')):
                return dict(row)
        return None

    def start_email_change(self, member, email, ip):
        email=clean_email(email)
        if email==member['email'].strip().casefold():
            raise ValueError('Dette er allereie e-postadressa di.')
        now=time.time();identifier=secrets.token_urlsafe(32)
        new_code=f'{secrets.randbelow(100000000):08d}'
        old_code=f'{secrets.randbelow(100000000):08d}'
        with managed_db(self.db) as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT m.email,a.version FROM members m JOIN member_access a ON a.member_id=m.id WHERE m.id=? AND m.privacy_deleted=0',(member['id'],)).fetchone()
            if not current or current['version']!=member['version']:
                raise ValueError('Logg inn på nytt før du byter e-postadresse.')
            if db.execute('SELECT 1 FROM board_users WHERE member_id=? OR lower(trim(username))=?',(member['id'],member['email'].strip().casefold())).fetchone():
                raise ValueError('Du har ein styrekonto. Kontakt styret for samordna byte av e-postadresse.')
            if self.payment_in_progress(db,member['id']):
                raise ValueError('Avklar den pågåande betalinga før du byter e-postadresse.')
            if not self.limits(db,email,ip,now,member['id']):
                raise ValueError('For mange forsøk. Vent litt før du prøver igjen.')
            if self.email_taken(db,email,member['id']):
                raise ValueError('E-postbytet kunne ikkje startast. Kontroller adressa eller kontakt folk@oslobygda.no.')
            db.execute("DELETE FROM member_challenges WHERE member_id=? AND purpose='email'",(member['id'],))
            db.execute('''INSERT INTO member_challenges(id,member_id,purpose,email,previous_email,version,code_hash,extra_hash,expires)
                VALUES (?,?,'email',?,?,?,?,?,?)''',(identifier,member['id'],email,current['email'],current['version'],
                self.digest('email-new',identifier+new_code),self.digest('email-old',identifier+old_code),now+TTL))
        try:
            send_code(current['email'],old_code,'email')
            send_code(email,new_code,'email')
        except Exception:
            with managed_db(self.db) as db:db.execute('DELETE FROM member_challenges WHERE id=?',(identifier,))
            raise ValueError('Kodane kunne ikkje sendast. E-postadressa er ikkje endra. Prøv igjen seinare.') from None
        return identifier

    @staticmethod
    def payment_in_progress(db, mid):
        return db.execute("""SELECT 1 FROM signup_orders WHERE (member_id=? OR renewal_member_id=? OR lower(trim(email))=(SELECT lower(trim(email)) FROM members WHERE id=?))
            AND environment='production' AND (confirmation_status IN ('sending','review') OR status='review'
            OR (create_attempted=1 AND status NOT IN ('complete','ABORTED','EXPIRED','TERMINATED','redacted')))""",(mid,mid,mid)).fetchone()

    @staticmethod
    def email_taken(db, email, mid):
        return db.execute('SELECT 1 FROM members WHERE lower(trim(email))=? AND id<>? AND privacy_deleted=0',(email,mid)).fetchone() or db.execute("""SELECT 1 FROM signup_orders WHERE email=? AND status NOT IN
            ('ABORTED','EXPIRED','TERMINATED','redacted','complete') AND COALESCE(renewal_member_id,-1)<>?""",(email,mid)).fetchone()

    def change_email(self, db, member, identifier, old_code, new_code):
        row=db.execute("SELECT * FROM member_challenges WHERE id=? AND purpose='email' AND member_id=?",(identifier,member['id'])).fetchone()
        if not row:return None
        db.execute('UPDATE member_challenges SET attempts=attempts+1 WHERE id=?',(identifier,))
        current=db.execute('SELECT m.email,a.version,m.privacy_deleted FROM members m JOIN member_access a ON a.member_id=m.id WHERE m.id=?',(member['id'],)).fetchone()
        if not current or current['privacy_deleted'] or row['expires']<=time.time() or row['attempts']>=5 or current['email']!=row['previous_email'] or current['version']!=row['version']:
            return None
        valid=all(re.fullmatch(r'[0-9]{8}',value) for value in (old_code,new_code))
        if not valid or not hmac.compare_digest(row['extra_hash'],self.digest('email-old',identifier+old_code)) or not hmac.compare_digest(row['code_hash'],self.digest('email-new',identifier+new_code)):
            return None
        if self.payment_in_progress(db,member['id']) or self.email_taken(db,row['email'],member['id']):
            return None
        if db.execute('SELECT 1 FROM board_users WHERE member_id=? OR lower(trim(username))=?',(member['id'],row['previous_email'].strip().casefold())).fetchone():
            return None
        revoke_access(db,member['id'])
        db.execute('UPDATE members SET email=?,updated_at=? WHERE id=?',(row['email'],datetime.now(timezone.utc).isoformat(),member['id']))
        db.execute('UPDATE renewal_links SET revoked=1 WHERE member_id=?',(member['id'],))
        db.execute("UPDATE signup_orders SET email=? WHERE (member_id=? OR renewal_member_id=?) AND confirmation_status='pending'",(row['email'],member['id'],member['id']))
        # Eldre stadfestingar/nyhendebrev skal ikkje sendast til den gamle adressa frå signup-køen.
        db.execute("UPDATE signup_orders SET newsletter_done=1 WHERE (member_id=? OR renewal_member_id=?)",(member['id'],member['id']))
        return row['previous_email'],row['email'],db.execute('SELECT version FROM member_access WHERE member_id=?',(member['id'],)).fetchone()[0]
