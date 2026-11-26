"""Eksplisitte driftskommandoar for Vipps-oppsett og innmeldingsvedlikehald."""

import os
import time
from pathlib import Path
from dotenv import set_key
from betalingsstatus import Ordrestatus, Vippsstatus
from database import managed_db
from vipps_client import VippsError


def install_commands(
    app, get_db, service, privacy_maintenance, sync_followups_safely, payments
):
    @app.cli.command("innmelding-testmodus")
    def test_mode():
        config = payments.credentials("test")
        if not all(
            config.get(key)
            for key in (
                "VIPPS_CLIENT_ID",
                "VIPPS_CLIENT_SECRET",
                "VIPPS_SUBSCRIPTION_KEY",
                "VIPPS_MSN",
            )
        ):
            raise SystemExit("Legg inn testnøklar med konfigurer_vipps.py først.")
        env = Path(__file__).resolve().parent / ".env"
        env.touch(mode=0o600, exist_ok=True)
        env.chmod(0o600)
        set_key(env, "VIPPS_SIGNUP_MODE", "test")
        print(
            "Testmodus er valt. Produksjonsnøklane er bevarte. Trykk Web → Reload, og opne /bli-medlem."
        )

    @app.cli.command("innmelding-produksjonsprove")
    def production_preview():
        """Vel produksjonsprøve berre for innlogga styret. Ikkje opne offentleg."""
        payments.client_for("production")  # Kontroller berre at alle verdiar er sette.
        env = Path(__file__).resolve().parent / ".env"
        env.touch(mode=0o600, exist_ok=True)
        env.chmod(0o600)
        set_key(env, "VIPPS_SIGNUP_MODE", "production-preview")
        print(
            "Produksjonsprøve er vald for innlogga styret. Registrer produksjonswebhook og trykk Web → Reload. Publikum får ikkje tilgang."
        )

    @app.cli.command("innmelding-webhook")
    def register_webhook():
        environment = os.environ.get("VIPPS_SIGNUP_MODE", "disabled")
        if environment == "production-preview":
            environment = "production"
        if environment not in ("test", "production"):
            raise SystemExit("Vel testmodus før webhook blir registrert.")
        config = payments.credentials(environment)
        if config.get("VIPPS_WEBHOOK_SECRET"):
            print("Webhook er allereie sett opp. Ingen ny registrering utført.")
            return
        origin = os.environ.get(
            "VIPPS_PUBLIC_ORIGIN", "https://bygdelista.oslobygda.no"
        ).rstrip("/")
        result = payments.client_for(environment)._authenticated(
            "POST",
            "/webhooks/v1/webhooks",
            {
                "url": origin + "/vipps/webhook/" + environment,
                "events": [
                    "epayments.payment." + event + ".v1"
                    for event in (
                        "authorized",
                        "captured",
                        "aborted",
                        "expired",
                        "terminated",
                        "cancelled",
                        "refunded",
                    )
                ],
            },
        )
        secret = result.get("secret", "")
        webhook_id = result.get("id", "")
        if (
            not isinstance(secret, str)
            or not secret
            or not isinstance(webhook_id, str)
            or not webhook_id
        ):
            raise SystemExit(
                "Kunne ikkje stadfeste webhook-oppsettet. Kontroller registreringa i Vipps-portalen før nytt forsøk."
            )
        env = Path(__file__).resolve().parent / (
            ".env.vipps-test" if environment == "test" else ".env"
        )
        env.touch(mode=0o600, exist_ok=True)
        env.chmod(0o600)
        set_key(env, "VIPPS_WEBHOOK_SECRET", secret)
        set_key(env, "VIPPS_WEBHOOK_ID", webhook_id)
        print(
            "Webhook registrert og løyndomen lagra. Trykk Web → Reload før du testar ei betaling."
        )

    @app.cli.command("innmelding-vedlikehald")
    def maintain():
        """Stadfest uferdige betalingar og prøv Brevo-køen på nytt."""
        with managed_db(get_db, commit_on_success=False) as db:
            refs = [
                r[0]
                for r in db.execute(
                    f"SELECT reference FROM signup_orders WHERE status NOT IN ('{Ordrestatus.COMPLETE}','{Ordrestatus.REVIEW}','{Vippsstatus.ABORTED}','{Vippsstatus.EXPIRED}','{Vippsstatus.TERMINATED}','{Ordrestatus.REDACTED}') ORDER BY checked_at LIMIT 100"
                )
            ]
            news = [
                r[0]
                for r in db.execute(
                    f"SELECT reference FROM signup_orders WHERE environment='production' AND status='{Ordrestatus.COMPLETE}' AND newsletter=1 AND newsletter_done=0 LIMIT 100"
                )
            ]
        with managed_db(get_db, commit_on_success=False) as db:
            confirmations = [
                row[0]
                for row in db.execute(
                    f"SELECT reference FROM signup_orders WHERE environment='production' AND status='{Ordrestatus.COMPLETE}' AND confirmation_status='pending' LIMIT 100"
                )
            ]
        for ref in confirmations:
            service.send_confirmation(ref)
        privacy_done = privacy_maintenance()
        problems = 0
        for ref in refs:
            try:
                service.reconcile(ref)
                sync_followups_safely(ref)
            except (VippsError, ValueError):
                problems += 1
        for ref in news:
            sync_followups_safely(ref)
        from kontingent import today
        from personvern_vedlikehald import prepare, send_pending

        newsletter_done = app.extensions.get(
            "member_newsletter_maintenance", lambda: 0
        )()
        with managed_db(get_db, commit_on_success=False) as db:
            db.execute("DELETE FROM member_challenges WHERE expires<=?", (time.time(),))
            db.execute("DELETE FROM login_limits WHERE expires<=?", (time.time(),))
            db.execute(
                "DELETE FROM signup_email_codes WHERE expires<=?", (time.time(),)
            )
            db.execute("DELETE FROM auth_mail_jobs WHERE expires<=?", (time.time(),))
            db.commit()
        from arsdokument import stamp
        from vipps_rapport_api import automate_reports
        import json

        financial = app.extensions["payment_import"].run(fetch=True)
        try:
            report_counts = automate_reports(app.extensions["vipps_reports"])
            with managed_db(get_db) as db:
                db.execute(
                    "INSERT INTO finance_runs(kind,started_at,finished_at,counts) VALUES ('reports',?,?,?)",
                    (stamp(), stamp(), json.dumps(report_counts)),
                )
            app.extensions["public_ledger"].refresh_enabled()
        except (ValueError, VippsError, KeyError, TypeError):
            with managed_db(get_db) as db:
                db.execute(
                    "INSERT INTO finance_runs(kind,started_at,finished_at,error) VALUES ('reports',?,?,?)",
                    (
                        stamp(),
                        stamp(),
                        "Rapporttenesta eller avstemming krev kontroll.",
                    ),
                )
            report_counts = {"review": 1}
            app.logger.warning("Vipps-rapport eller økonomikontroll krev oppfølging.")
        print(
            f"Økonomi: {financial['booked']} medlemsbetalingar bokførte, "
            f"{financial['review']} til kontroll. Rapport: {report_counts}."
        )
        if os.environ.get("GITHUB_DOCUMENTS_TOKEN", "").strip():
            try:
                app.extensions["document_publisher"].run(limit=5)
            except ValueError:
                app.logger.warning("Publiseringskøa blir prøvd igjen seinare.")
        cleaned = prepare(get_db, today())
        notified = send_pending(get_db, today())
        print(
            f"Kontrollert {len(refs)} betalingar; {problems} må prøvast igjen. Handsama {len(news)} Brevo-oppføringar, {newsletter_done} medlemsval og {privacy_done} slettingar. Anonymisert {cleaned} gamle ordrar og sendt {notified} styrevarsel."
        )
