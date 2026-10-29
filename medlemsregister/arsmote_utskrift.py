"""Utskrift av faste dokumentkopiar. Ingen publisering eller databaseendring."""
import json
from flask import abort,render_template
from database import managed_db
from arsdokument import public_payload
from offentleg_rekneskap import validate_ledger
from budsjett import validate_budget


def install_print(app,get_db,require_admin):
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
        return render_template('arsmote_utskrift.html',kind=kind,report=report,
                               title=report.get('title',f'Rekneskap {report["report_year"]}'),structured_report=structured_report)
