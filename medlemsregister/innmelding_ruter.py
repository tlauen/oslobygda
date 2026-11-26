"""Offentlege innmeldingsruter og styret si ordreoversikt."""

from datetime import datetime, timezone
import json
import os
import secrets
from flask import abort, redirect, render_template, request, session
from csrf import csrf_exempt
from betalingsreglar import VIPPS_MAX_NOK
from betalingsstatus import Ordrestatus, Vippsstatus
from database import managed_db
from vipps_client import VippsError


def install_routes(
    app, get_db, service, require_admin, sync_followups_safely, payments
):
    @app.context_processor
    def payment_status_constants():
        return {
            "Ordrestatus": Ordrestatus,
            "Vippsstatus": Vippsstatus,
            "vipps_max_nok": VIPPS_MAX_NOK,
        }

    def mode():
        selected = os.environ.get("VIPPS_SIGNUP_MODE", "disabled")
        if selected == "production-preview":
            if not app.extensions["styre_auth_valid"]():
                abort(
                    503,
                    "Nyinnmelding er snart klar. Kontakt folk@oslobygda.no i mellomtida.",
                )
            return "production"
        if selected not in ("test", "production"):
            abort(503, "Nyinnmelding med Vipps er ikkje opna enno.")
        return selected

    @app.route("/bli-medlem", methods=["GET", "POST"])
    def new_signup():
        environment = mode()
        key = session.setdefault("signup_key", secrets.token_urlsafe(32))
        values = {}
        error = None
        if request.method == "POST":
            values = request.form.to_dict()
            try:
                if values.get("website"):
                    raise ValueError("Ugyldig innsending.")
                reference = service.new(
                    values, key, environment, request.remote_addr or "unknown"
                )
                session["signup_reference"] = reference
                from signup_stadfesting import issue

                issue(app, get_db, service.order(reference))
                return redirect("/bli-medlem/status", code=303)
            except ValueError as exc:
                error = str(exc)
                app.logger.warning(
                    "Nyinnmelding: validering stoppa innsendinga (%s)", error
                )
        with managed_db(get_db, commit_on_success=False) as db:
            from kontingent import today, payable

            year = today().year
            try:
                policy = payable(db, year)
            except ValueError as exc:
                return render_template(
                    "kontingent_stengt.html", environment=environment, reason=str(exc)
                ), 200
            threshold = policy["superkul_ore"]
        return render_template(
            "ny_innmelding.html",
            values=values,
            error=error,
            environment=environment,
            year=year,
            threshold=threshold,
            minimum=policy["minimum_ore"],
        ), 400 if error else 200

    def owned():
        reference = session.get("signup_reference", "")
        order = service.order(reference)
        if (
            not order
            or order["status"] == Ordrestatus.REDACTED
            or order["environment"] != mode()
        ):
            abort(404)
        if order.get("renewal_link_id"):
            with managed_db(get_db, commit_on_success=False) as db:
                link = db.execute(
                    "SELECT * FROM renewal_links WHERE id=? AND revoked=0",
                    (order["renewal_link_id"],),
                ).fetchone()
                if (
                    not link
                    or session.get("renewal_link") != link["id"]
                    or session.get("renewal_digest") != link["token_hash"]
                ):
                    abort(404)
                if link["access_kind"] == "member":
                    member = app.extensions["member_auth"].member(session)
                    if not member or member["id"] != link["member_id"]:
                        abort(404)
        return order

    @app.route("/bli-medlem/rediger", methods=["GET", "POST"])
    def signup_edit():
        order = owned()
        if (
            order["status"] != Ordrestatus.NEW
            or order["create_attempted"]
            or order["renewal_member_id"]
        ):
            abort(
                409,
                "Betaling er allereie forsøkt oppretta eller dette er ei fornying. Kontakt styret for retting.",
            )
        values = {
            **json.loads(order["details"]),
            "amount": order["amount_ore"] // 100,
            "newsletter": "1" if order["newsletter"] else "",
            "terms": "1",
        }
        error = None
        if request.method == "POST":
            values = request.form.to_dict()
            try:
                service.edit(order["reference"], values)
                updated = service.order(order["reference"])
                if updated["email"] != order["email"]:
                    session.pop("signup_verified_email", None)
                    from signup_stadfesting import issue

                    issue(app, get_db, updated)
                return redirect("/bli-medlem/status", code=303)
            except ValueError as exc:
                error = str(exc)
        with managed_db(get_db, commit_on_success=False) as db:
            from kontingent import payable

            try:
                policy = payable(db, order["for_year"])
            except ValueError as exc:
                abort(409, str(exc))
        return render_template(
            "ny_innmelding.html",
            values=values,
            error=error,
            environment=order["environment"],
            year=order["for_year"],
            threshold=policy["superkul_ore"],
            minimum=policy["minimum_ore"],
            editing=True,
        ), 400 if error else 200

    @app.route("/bli-medlem/status", methods=["GET", "POST"])
    def signup_status():
        order = owned()
        error = None
        needs_verification = (
            order["status"] == Ordrestatus.NEW
            and not order["create_attempted"]
            and not order.get("renewal_member_id")
            and session.get("signup_verified_email")
            != [order["reference"], order["email"]]
        )
        if needs_verification:
            from signup_stadfesting import issue, verify

            if request.method == "POST":
                if request.form.get("action") == "verify" and verify(
                    app, get_db, order, request.form.get("code", "")
                ):
                    session["signup_verified_email"] = [
                        order["reference"],
                        order["email"],
                    ]
                    return redirect("/bli-medlem/status", code=303)
                if request.form.get("action") == "resend":
                    issue(app, get_db, order)
                else:
                    error = "Stadfest e-postadressa med koden før du går vidare. Koden kan vere feil eller utgått."
            return render_template(
                "innmelding_epostkode.html",
                order=order,
                environment=order["environment"],
                error=error,
            ), 400 if error else 200
        if request.method == "POST":
            try:
                if request.form.get("action") == "pay":
                    origin = os.environ.get(
                        "VIPPS_PUBLIC_ORIGIN", "https://bygdelista.oslobygda.no"
                    ).rstrip("/")
                    return redirect(
                        service.create(
                            order["reference"],
                            origin + "/bli-medlem/status",
                            verified_email=order["email"]
                            if not order.get("renewal_member_id")
                            else None,
                        ),
                        code=303,
                    )
                service.reconcile(order["reference"])
                sync_followups_safely(order["reference"])
            except VippsError as exc:
                error = str(exc)
            order = service.order(order["reference"])
        return render_template(
            "innmelding_status.html",
            order=order,
            error=error,
            environment=order["environment"],
            details=json.loads(order["details"]),
            can_edit=order["status"] == Ordrestatus.NEW
            and not order["create_attempted"]
            and not order["renewal_member_id"],
        )

    @app.route("/bli-medlem/prov-igjen", methods=["POST"])
    def signup_restart():
        order = owned()
        if order["status"] not in (
            Vippsstatus.ABORTED,
            Vippsstatus.EXPIRED,
            Vippsstatus.TERMINATED,
        ):
            abort(409)
        session.pop("signup_reference", None)
        session["signup_key"] = secrets.token_urlsafe(32)
        return redirect(
            "/forny" if order.get("renewal_member_id") else "/bli-medlem", code=303
        )

    @app.route("/vipps/webhook/<environment>", methods=["POST"])
    @csrf_exempt
    def signup_webhook(environment):
        if environment not in ("test", "production"):
            abort(404)
        secret = payments.credentials(environment).get("VIPPS_WEBHOOK_SECRET", "")
        if not secret or not payments.webhook_valid(request, secret):
            abort(401)
        payload = request.get_json(silent=True) or {}
        reference = payload.get("reference", "")
        order = service.order(reference) if isinstance(reference, str) else None
        if (
            order
            and order["environment"] == environment
            and str(payload.get("msn", "")) == order["msn"]
        ):
            try:
                service.reconcile(reference)
                sync_followups_safely(reference)
            except VippsError:
                return "", 503
        return "", 200

    @app.route("/innmeldingar")
    @require_admin
    def signup_overview():
        with managed_db(get_db, commit_on_success=False) as db:
            orders = [
                dict(row)
                for row in db.execute(
                    "SELECT o.*,p.paid_at FROM signup_orders o LEFT JOIN payments p ON p.id=o.payment_id WHERE o.overview_archived=0 ORDER BY o.created_at DESC LIMIT 100"
                )
            ]
        for order in orders:
            order["member_details"] = json.loads(order["details"])
            order["created_display"] = datetime.fromtimestamp(
                order["created_at"], timezone.utc
            ).isoformat()
        return render_template("innmeldingar.html", orders=orders)
