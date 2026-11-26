"""Ein enkel inngang for Vipps-rapport, bankgrunnlag og samla godkjenning."""

import os

from arsdokument import today
from database import managed_db
from flask import render_template, request, session
from vipps_client import VippsError
from vipps_rapport import ReportImport


def install_reports(app, get_db, require_admin, update_member):
    service = ReportImport(get_db, update_member)
    app.extensions["vipps_reports"] = service

    @app.cli.command("hent-vippsrapport")
    def fetch_report_command():
        import click
        from vipps_rapport_api import fetch_reports

        click.echo(fetch_reports(service))

    @app.route("/okonomi/vippsrapport", methods=["GET", "POST"])
    @require_admin
    def vipps_report_index():
        error = message = None
        preview = None
        token = None
        status = 200
        if request.method == "POST":
            try:
                action = request.form.get("action")
                if request.form.get("confirm_payout"):
                    action = "confirm_bank"
                actor = session["board_username"]
                if action == "confirm_bank":
                    identity = request.form["confirm_payout"]
                    service.confirm_bank(
                        identity,
                        request.form.get("bank_day_" + identity),
                        request.form.get("bank_amount_" + identity),
                        request.form.get("bank_reference_" + identity),
                        actor,
                    )
                    message = "Bankoppgjeret er kontrollert. Det kjem med blant dei klare forslaga."
                elif action == "fetch_api":
                    from vipps_rapport_api import fetch_reports

                    result = fetch_reports(service)
                    message = f"{result['new']} nye rapportkjelder frå API."
                elif action in ("upload", "bank"):
                    upload = request.files.get("report")
                    if not upload:
                        raise ValueError("Vel ei CSV-fil.")
                    content = upload.read(3 * 1024 * 1024 + 1)
                    if action == "upload":
                        result = service.ingest(content, request.form.get("msn", ""))
                        message = f"{result['new']} nye kjelder; {result['known']} kjende kjelder vart hoppa over."
                    else:
                        message = f"{service.bank_csv(content, actor)} oppgjer kopla til bankgrunnlag."
                elif action == "preview":
                    choices = {}
                    for identity in request.form.getlist("identity"):
                        choices[identity] = {
                            key: request.form.get(key + "_" + identity, "")
                            for key in (
                                "category",
                                "member_id",
                                "year",
                                "original_journal",
                                "existing_journal",
                            )
                        }
                    token, preview = service.preview(
                        choices, actor, identities=request.form.getlist("identity")
                    )
                elif action == "approve":
                    if request.form.get("confirmed") != "yes":
                        raise ValueError("Stadfest kontrollen før bokføring.")
                    result = service.approve(request.form.get("token"), actor)
                    app.extensions["public_ledger"].refresh_enabled(actor)
                    message = f"{len(result)} føringar er bokførte eller kopla. Ingen pengar er overførte."
                else:
                    raise ValueError("Vel ei gyldig handling.")
            except (ValueError, TypeError, VippsError, KeyError) as exc:
                error = (
                    str(exc)
                    if not isinstance(exc, (VippsError, KeyError))
                    else "Rapporttenesta kunne ikkje kontrollerast. Prøv igjen seinare."
                )
                status = 503 if isinstance(exc, (VippsError, KeyError)) else 400
        try:
            page = max(1, min(1000, int(request.args.get("page", "1"))))
        except ValueError:
            page = 1
        with managed_db(get_db) as db:
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT *,EXISTS(SELECT 1 FROM ledger_journals r WHERE r.reversal_of=vipps_report_entries.journal_id) AS reversed FROM vipps_report_entries WHERE journal_id IS NULL OR EXISTS(SELECT 1 FROM ledger_journals r WHERE r.reversal_of=vipps_report_entries.journal_id) ORDER BY day DESC,identity LIMIT 200 OFFSET ?",
                    ((page - 1) * 200,),
                )
            ]
            members = db.execute(
                "SELECT id,full_name FROM members ORDER BY full_name"
            ).fetchall()
            report_error = db.execute(
                "SELECT error FROM finance_runs WHERE kind='reports' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            pending = db.execute(
                "SELECT COUNT(*) FROM vipps_report_entries WHERE journal_id IS NULL"
            ).fetchone()[0]
        return render_template(
            "vipps_rapport.html",
            api_ready=os.getenv("VIPPS_REPORT_FETCH_ENABLED") == "1"
            and bool(os.getenv("VIPPS_REPORT_LEDGER_ID")),
            rows=rows,
            members=members,
            preview=preview,
            token=token,
            error=error,
            message=message,
            year=today().year,
            pending=pending,
            page=page,
            report_error=report_error[0] if report_error else None,
        ), status
