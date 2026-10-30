"""Årsdokument, kalenderimport og faste versjonar. Ingen økonomiføring."""
import hashlib
import json
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from flask import abort, redirect, render_template, request, session
from database import managed_db
from arsmelding import report_from, merge_calendar, edit_report, add_manual, compose, check_ready, STATUSES
from tilskipingar import GithubCalendar, CalendarError

KINDS = {'arsmelding': 'Årsmelding', 'rekneskap': 'Rekneskap', 'budsjett': 'Budsjett'}


class DocumentConflict(ValueError):
    pass


def init_documents(get_db):
    with managed_db(get_db) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS annual_documents (
          id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('arsmelding','rekneskap','budsjett')),
          report_year INTEGER NOT NULL CHECK(report_year BETWEEN 1900 AND 2200),
          meeting_year INTEGER NOT NULL CHECK(meeting_year BETWEEN 1900 AND 2200),
          revision INTEGER NOT NULL DEFAULT 1, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
          updated_by TEXT NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(kind,report_year)
        );
        CREATE TABLE IF NOT EXISTS annual_document_edits (
          document_id INTEGER NOT NULL REFERENCES annual_documents(id), revision INTEGER NOT NULL,
          title TEXT NOT NULL, body TEXT NOT NULL, meeting_year INTEGER NOT NULL,
          actor TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(document_id,revision)
        );
        CREATE TRIGGER IF NOT EXISTS annual_edits_no_update
        BEFORE UPDATE ON annual_document_edits BEGIN SELECT RAISE(ABORT,'Endringshistorikk er fast'); END;
        CREATE TRIGGER IF NOT EXISTS annual_edits_no_delete
        BEFORE DELETE ON annual_document_edits BEGIN SELECT RAISE(ABORT,'Endringshistorikk er fast'); END;
        CREATE TABLE IF NOT EXISTS annual_versions (
          id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES annual_documents(id),
          source_revision INTEGER NOT NULL, status TEXT NOT NULL CHECK(status IN ('meeting','approved')),
          snapshot TEXT NOT NULL, content_hash TEXT NOT NULL,
          created_by TEXT NOT NULL, created_at TEXT NOT NULL, decision_date TEXT,
          UNIQUE(document_id,source_revision,status)
        );
        CREATE TABLE IF NOT EXISTS annual_publication_queue (
          id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL UNIQUE REFERENCES annual_versions(id),
          payload TEXT NOT NULL, content_hash TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sending','stored','visible','failed')),
          attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT NOT NULL DEFAULT '',
          created_by TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TRIGGER IF NOT EXISTS annual_versions_no_update
        BEFORE UPDATE ON annual_versions BEGIN SELECT RAISE(ABORT,'Fast dokumentversjon kan ikkje endrast'); END;
        CREATE TRIGGER IF NOT EXISTS annual_versions_no_delete
        BEFORE DELETE ON annual_versions BEGIN SELECT RAISE(ABORT,'Fast dokumentversjon kan ikkje slettast'); END;
        CREATE TRIGGER IF NOT EXISTS annual_queue_payload_immutable
        BEFORE UPDATE OF version_id,payload,content_hash ON annual_publication_queue
        BEGIN SELECT RAISE(ABORT,'Publiseringsinnhald kan ikkje endrast'); END;
        ''')
        for table in ('annual_documents', 'annual_document_edits'):
            columns = {row[1] for row in db.execute(f'PRAGMA table_info({table})')}
            if 'report_json' not in columns:
                db.execute(f"ALTER TABLE {table} ADD COLUMN report_json TEXT NOT NULL DEFAULT '{{}}'")


def today():
    return datetime.now(ZoneInfo('Europe/Oslo')).date()


def record_edit(db, doc_id):
    db.execute("""INSERT INTO annual_document_edits
        (document_id,revision,title,body,meeting_year,actor,created_at,report_json)
        SELECT id,revision,title,body,meeting_year,updated_by,updated_at,report_json
        FROM annual_documents WHERE id=?""", (doc_id,))


def stamp():
    return datetime.now(timezone.utc).isoformat()


def integer(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError('Ugyldig tal.') from None


def year(value):
    value = integer(value)
    if not 1900 <= value <= 2200:
        raise ValueError('Årstalet må vere mellom 1900 og 2200.')
    return value


def text_fields(title, body):
    title, body = title.strip(), body.strip()
    if not title or len(title) > 200 or len(body) > 30000:
        raise ValueError('Fyll inn tittel (maks 200 teikn) og tekst (maks 30 000 teikn).')
    return title, body


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def public_payload(row):
    """Eige avgrensa skjema. Ingen rå DB-objekt eller interne brukarnamn."""
    snapshot = json.loads(row['snapshot'])
    payload = dict(schema_version=1, version_id=row['id'], kind=snapshot['kind'],
                   report_year=snapshot['report_year'], meeting_year=snapshot['meeting_year'],
                   source_revision=row['source_revision'], status=row['status'],
                   title=snapshot['title'], body=snapshot['body'],
                   decision_date=row['decision_date'])
    structured=json.loads(snapshot.get('report_json','{}'))
    if structured:
        from arsmelding_offentleg import presentation
        payload['presentation']=presentation(structured)
    validate_public(payload)
    return payload


def validate_public(payload):
    fields = {'schema_version','version_id','kind','report_year','meeting_year',
              'source_revision','status','title','body','decision_date'}
    if not isinstance(payload, dict) or set(payload) not in (fields,fields|{'presentation'}):
        raise ValueError('Ugyldige offentlege felt.')
    if 'presentation' in payload:
        from arsmelding_offentleg import validate_presentation
        validate_presentation(payload['presentation'])
    if payload['schema_version'] != 1 or payload['kind'] != 'arsmelding':
        raise ValueError('Denne versjonen støttar berre offentleg årsmeldingstekst.')
    for key in ('version_id', 'source_revision'):
        if type(payload[key]) is not int or payload[key] < 1:
            raise ValueError('Ugyldig versjon.')
    for key in ('report_year', 'meeting_year'):
        if type(payload[key]) is not int:
            raise ValueError('Ugyldig år.')
        year(payload[key])
    if not isinstance(payload['title'], str) or not isinstance(payload['body'], str):
        raise ValueError('Ugyldig tekst.')
    text_fields(payload['title'], payload['body'])
    if payload['status'] not in ('meeting', 'approved'):
        raise ValueError('Ugyldig status.')
    if payload['status'] == 'approved':
        date.fromisoformat(payload['decision_date'])
    elif payload['decision_date'] is not None:
        raise ValueError('Sakspapir skal ikkje ha vedtaksdato.')


class Documents:
    def __init__(self, get_db):
        self.get_db = get_db

    def create(self, kind, report_year, meeting_year, actor):
        if kind != 'arsmelding':
            raise ValueError('Rekneskap og budsjett blir tilgjengelege i seinare steg.')
        report_year, meeting_year = year(report_year), year(meeting_year)
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM annual_documents WHERE kind=? AND report_year=?', (kind, report_year)).fetchone():
                raise DocumentConflict('Dokumentet finst allereie for dette året.')
            doc_id = db.execute('''INSERT INTO annual_documents
                (kind,report_year,meeting_year,title,updated_by,updated_at) VALUES (?,?,?,?,?,?)''',
                (kind, report_year, meeting_year, f'{KINDS[kind]} {report_year}', actor, stamp())).lastrowid
            record_edit(db, doc_id)
            return doc_id

    def save(self, doc_id, revision, title, body, meeting_year, actor):
        title, body = text_fields(title, body)
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT report_json FROM annual_documents WHERE id=?', (doc_id,)).fetchone()
            if current and current['report_json'] != '{}':
                raise ValueError('Bruk skjemaet for strukturert årsmelding.')
            changed = db.execute('''UPDATE annual_documents SET title=?,body=?,meeting_year=?,
                revision=revision+1,updated_by=?,updated_at=? WHERE id=? AND revision=?''',
                (title, body, year(meeting_year), actor, stamp(), doc_id, integer(revision)))
            if changed.rowcount != 1:
                raise DocumentConflict('Dokumentet er endra av nokon andre. Opne det på nytt før du lagrar.')
            record_edit(db, doc_id)

    def update_report(self, doc_id, revision, actor, action, form=None, calendar=None):
        form = form or {}
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            doc = db.execute('SELECT * FROM annual_documents WHERE id=?', (doc_id,)).fetchone()
            if not doc or doc['revision'] != integer(revision):
                raise DocumentConflict('Dokumentet er endra. Kopier teksten og opne siste revisjon.')
            report = report_from(doc)
            if action == 'import_calendar':
                source_revision, events = calendar
                report = merge_calendar(report, events, doc['report_year'], source_revision)
            elif action == 'save_report':
                report = edit_report(report, form)
                for item in report['activities']:
                    if item['origin'] == 'manual' and date.fromisoformat(item['source']['dato']).year != doc['report_year']:
                        raise ValueError('Manuell aktivitet må ha dato i rapportåret.')
                    prefix = 'activity_' + item['key'] + '_'
                    if form.get(prefix + 'acknowledge') == 'yes':
                        item['source_missing'] = False
                        item['source_changed'] = False
                title, _ = text_fields(form.get('title', doc['title']), '')
                meeting_year = year(form.get('meeting_year', doc['meeting_year']))
                db.execute('UPDATE annual_documents SET title=?,meeting_year=? WHERE id=?', (title, meeting_year, doc_id))
            elif action == 'add_manual':
                report = add_manual(report, form, doc['report_year'])
            elif action == 'refresh_membership':
                archived = db.execute('SELECT antall_medlemer_med_betaling FROM medlemsar_arkiv WHERE ar=?', (doc['report_year'],)).fetchone()
                count = archived[0] if archived else db.execute("""SELECT COUNT(*) FROM
                    (SELECT member_id FROM payments WHERE for_year=? GROUP BY member_id HAVING SUM(amount_ore)>0)""", (doc['report_year'],)).fetchone()[0]
                report['membership'] = dict(year=doc['report_year'], count=count, source='archive' if archived else 'payments', checked_at=stamp())
            elif action == 'refresh_board':
                from styremodul import load_board
                report['board'] = load_board(doc['report_year'])
            elif action == 'remove_board':
                report.pop('board',None)
            elif action == 'remove_membership':
                report['membership'] = None
            else:
                raise ValueError('Ugyldig handling.')
            body = compose(report)
            text_fields(doc['title'], body)
            db.execute("""UPDATE annual_documents SET report_json=?,body=?,revision=revision+1,
                updated_by=?,updated_at=? WHERE id=?""", (canonical(report), body, actor, stamp(), doc_id))
            record_edit(db, doc_id)

    def freeze(self, doc_id, revision, status, decision_date, actor):
        if status not in ('meeting', 'approved'):
            raise ValueError('Ugyldig dokumentstatus.')
        decision_date = date.fromisoformat(decision_date).isoformat() if status == 'approved' else None
        if decision_date and decision_date > today().isoformat():
            raise ValueError('Vedtaksdato kan ikkje vere i framtida.')
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            doc = db.execute('SELECT * FROM annual_documents WHERE id=?', (doc_id,)).fetchone()
            if not doc or doc['revision'] != integer(revision):
                raise DocumentConflict('Dokumentet er endra. Last det på nytt før du lagrar ein fast versjon.')
            if doc['kind'] != 'arsmelding' or not doc['body'].strip():
                raise ValueError('Årsmeldinga må ha tekst før ein fast versjon kan lagrast.')
            if doc['report_json'] != '{}':
                check_ready(report_from(doc),allow_unconfirmed=status=='meeting')
            old = db.execute('SELECT id,decision_date FROM annual_versions WHERE document_id=? AND source_revision=? AND status=?',
                             (doc_id, doc['revision'], status)).fetchone()
            if old:
                if old['decision_date'] != decision_date:
                    raise DocumentConflict('Versjonen har ein annan vedtaksdato. Lag eit nytt arbeidsutkast for rettinga.')
                return old['id']
            snapshot = canonical({k: doc[k] for k in ('kind','report_year','meeting_year','title','body','report_json')})
            return db.execute('''INSERT INTO annual_versions
                (document_id,source_revision,status,snapshot,content_hash,created_by,created_at,decision_date)
                VALUES (?,?,?,?,?,?,?,?)''', (doc_id, doc['revision'], status, snapshot, digest(snapshot), actor, stamp(), decision_date)).lastrowid

    def enqueue(self, version_id, actor):
        with managed_db(self.get_db) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM annual_versions WHERE id=?', (version_id,)).fetchone()
            if not row:
                raise ValueError('Versjonen finst ikkje.')
            payload = canonical(public_payload(row))
            db.execute('''INSERT OR IGNORE INTO annual_publication_queue
                (version_id,payload,content_hash,created_by,created_at) VALUES (?,?,?,?,?)''',
                (version_id, payload, digest(payload), actor, stamp()))


def install_documents(app, get_db, require_admin):
    service = Documents(get_db)
    app.extensions['annual_documents'] = service

    @app.route('/arsmote', methods=['GET','POST'])
    @require_admin
    def annual_documents():
        error = None
        status = 200
        if request.method == 'POST':
            try:
                doc_id = service.create(request.form.get('kind'), request.form.get('report_year'),
                                        request.form.get('meeting_year'), session['board_username'])
                return redirect(app.jinja_env.globals['prefix_url']('annual_document', doc_id=doc_id))
            except ValueError as exc:
                error, status = str(exc), 400
        with managed_db(get_db) as db:
            docs = db.execute('SELECT * FROM annual_documents ORDER BY report_year DESC,kind').fetchall()
        return render_template('arsdokument.html', docs=docs, doc=None, error=error, year=today().year), status

    @app.route('/arsmote/<int:doc_id>', methods=['GET','POST'])
    @require_admin
    def annual_document(doc_id):
        error, status = None, 200
        if request.method == 'POST':
            try:
                actor = session['board_username']
                action = request.form.get('action')
                revision = request.form.get('revision')
                if action == 'save':
                    service.save(doc_id, revision, request.form.get('title',''), request.form.get('body',''), request.form.get('meeting_year'), actor)
                elif action in ('save_report', 'add_manual', 'refresh_membership', 'remove_membership', 'import_calendar', 'refresh_board', 'remove_board'):
                    calendar = None
                    if action == 'import_calendar':
                        _, source_revision, events = GithubCalendar().read()
                        calendar = (source_revision, events)
                    service.update_report(doc_id, revision, actor, action, request.form, calendar)
                elif action == 'freeze':
                    service.freeze(doc_id, revision, request.form.get('status'), request.form.get('decision_date',''), actor)
                else:
                    raise ValueError('Ugyldig handling.')
                return redirect(app.jinja_env.globals['prefix_url']('annual_document', doc_id=doc_id))
            except (ValueError, CalendarError) as exc:
                error = str(exc)
                status = 409 if isinstance(exc, DocumentConflict) else (503 if isinstance(exc, CalendarError) else 400)
        with managed_db(get_db) as db:
            doc = db.execute('SELECT * FROM annual_documents WHERE id=?', (doc_id,)).fetchone()
            if not doc:
                abort(404)
            versions = db.execute('SELECT * FROM annual_versions WHERE document_id=? ORDER BY id DESC', (doc_id,)).fetchall()
        return render_template('arsdokument.html', doc=doc, versions=versions, error=error,
                               submitted=request.form if status != 200 else {}, report=report_from(doc), activity_statuses=STATUSES,conflict=status==409), status

    @app.get('/arsmote/styrebilete/<filename>')
    @require_admin
    def annual_board_photo(filename):
        from flask import send_from_directory
        from styremodul import ROOT,board_file
        if not filename.lower().endswith(('.jpg','.jpeg','.png','.webp')): abort(404)
        directory=board_file().parent/'styreportrett'
        if not (directory/filename).is_file():directory=ROOT/'lutar'/'bilete'/'styret'
        response=send_from_directory(directory,filename)
        response.headers['X-Content-Type-Options']='nosniff'
        return response

    @app.route('/arsmote/versjon/<int:version_id>', methods=['GET','POST'])
    @require_admin
    def annual_version(version_id):
        with managed_db(get_db) as db:
            row = db.execute('SELECT * FROM annual_versions WHERE id=?', (version_id,)).fetchone()
            if not row:
                abort(404)
        if request.method == 'POST':
            if request.form.get('confirmed') != 'yes':
                abort(400, 'Stadfest at teksten er gjennomgått for offentleg publisering.')
            service.enqueue(version_id, session['board_username'])
            return redirect(app.jinja_env.globals['prefix_url']('annual_version', version_id=version_id))
        with managed_db(get_db) as db:
            queued = db.execute('SELECT status FROM annual_publication_queue WHERE version_id=?', (version_id,)).fetchone()
        return render_template('arsversjon.html', version=row, public=public_payload(row), queued=queued, report=json.loads(json.loads(row['snapshot']).get('report_json','{}')))
