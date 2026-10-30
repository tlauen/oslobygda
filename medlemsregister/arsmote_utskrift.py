"""Utskrift av faste dokumentkopiar. Ingen publisering eller databaseendring."""
import json
from flask import abort,render_template,request
from database import managed_db
from arsdokument import public_payload
from offentleg_rekneskap import validate_ledger
from budsjett import validate_budget


def install_print(app,get_db,require_admin):
    @app.route('/arsmote/dokument/rekneskap/<int:year>')
    @require_admin
    def ledger_document_preview(year):
        from dokumentvising import render_document
        return render_document(app.extensions['public_ledger'].preview(year))

    @app.route('/arsmote/utskrift/<kind>/<int:version_id>')
    @require_admin
    def annual_print(kind,version_id):
        structured_report=None
        with managed_db(get_db) as db:
            if kind=='arsmelding':
                row=db.execute('SELECT * FROM annual_versions WHERE id=?',(version_id,)).fetchone()
                if not row: abort(404)
                report=public_payload(row)
                structured_report=json.loads(json.loads(row['snapshot']).get('report_json','{}')) or None
            elif kind=='rekneskap':
                row=db.execute('SELECT payload FROM public_ledger_versions WHERE id=?',(version_id,)).fetchone()
                if not row: abort(404)
                report=json.loads(row['payload']);validate_ledger(report)
            elif kind=='budsjett':
                row=db.execute('SELECT payload FROM budget_versions WHERE id=?',(version_id,)).fetchone()
                if not row: abort(404)
                report=json.loads(row['payload']);validate_budget(report)
            else: abort(404)
        from dokumentvising import render_document
        return render_document(report)
