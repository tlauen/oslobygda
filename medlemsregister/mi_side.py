"""Eigne medlemsopplysningar, samtykke og kontingent bak e-postkode."""

from datetime import datetime, timezone
from functools import wraps
import os
import time

from flask import abort, jsonify, redirect, render_template, request, session, url_for
from database import managed_db
from medlem_auth import MemberAuth
from medlem_nyhendebrev import choose, queue
import kontingent
from ny_innmelding import FIELDS, validate


def history(db, mid):
    rows = {}
    for row in db.execute(
        "SELECT for_year,SUM(amount_ore) AS total FROM payments WHERE member_id=? GROUP BY for_year",
        (mid,),
    ):
        if row["total"] > 0:
            rows[row["for_year"]] = dict(
                year=row["for_year"], status="Betalt", amount_ore=row["total"]
            )
    for table, label in [
        ("paid_membership_years", "Betalt (registrert av styret)"),
        ("free_membership_years", "Godkjent gratis"),
    ]:
        for row in db.execute(
            f"SELECT for_year FROM {table} WHERE member_id=?", (mid,)
        ):
            rows.setdefault(row[0], dict(year=row[0], status=label, amount_ore=None))
    return sorted(rows.values(), key=lambda r: r["year"], reverse=True)


def payment_state(db, member):
    year = kontingent.today().year
    free = bool(
        db.execute(
            "SELECT 1 FROM free_membership_years WHERE member_id=? AND for_year=?",
            (member["id"], year),
        ).fetchone()
    )
    paid = kontingent.member_paid(db, member["id"], year)
    covered = free or paid
    policy = error = None
    try:
        policy = kontingent.payable(db, year)
    except ValueError as exc:
        error = str(exc)
    mode = os.environ.get("VIPPS_SIGNUP_MODE", "disabled")
    ready = mode in ("production", "test")
    if not ready and not error:
        error = "Betaling på Mi side er ikkje opna enno."
    return dict(
        year=year,
        free=free and not paid,
        covered=covered,
        policy=policy,
        payment_error=error,
        can_pay=bool(policy and ready and not covered),
    )


def install_member_portal(app, get_db, prefix_url):
    auth = MemberAuth(app, get_db)
    app.extensions["member_auth"] = auth

    def require_member(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            member = auth.member(session)
            if not member:
                for key in ("member_id", "member_version", "member_logged_at"):
                    session.pop(key, None)
                return redirect(prefix_url("member_login"))
            return view(member, *args, **kwargs)

        return wrapped

    @app.route("/mi-side/logg-inn", methods=["GET", "POST"])
    def member_login():
        if auth.member(session):
            return redirect(prefix_url("member_home"))
        error = None
        if request.method == "POST":
            try:
                if not all(
                    os.environ.get(k)
                    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")
                ):
                    raise ValueError(
                        "Innlogging er mellombels utilgjengeleg. Kontakt folk@oslobygda.no om du treng hjelp."
                    )
                challenge = auth.start(
                    request.form.get("email", ""), request.remote_addr or "unknown"
                )
                session["member_challenge"] = challenge
                return redirect(prefix_url("member_verify"), code=303)
            except ValueError as exc:
                error = str(exc)
        return render_template(
            "medlem_innlogging.html", stage="email", error=error, environment=None
        ), 400 if error else 200

    @app.route("/mi-side/kode", methods=["GET", "POST"])
    def member_verify():
        error = None
        if request.method == "POST":
            result = auth.verify(
                session.get("member_challenge", ""), request.form.get("code", "")
            )
            if result:
                # Ny innlogging roterer økta; medlemskode skal aldri vidareføre styretilgang.
                session.clear()
                session.permanent = True
                session.update(
                    member_id=result[0],
                    member_version=result[1],
                    member_logged_at=time.time(),
                )
                return redirect(prefix_url("member_home"), code=303)
            error = "Koden er feil, brukt eller har gått ut. Du har høgst fem forsøk per kode."
        return render_template(
            "medlem_innlogging.html", stage="code", error=error, environment=None
        ), 400 if error else 200

    @app.post("/mi-side/logg-ut")
    def member_logout():
        session.clear()
        return redirect(prefix_url("member_login"), code=303)

    @app.route("/mi-side", methods=["GET", "POST"], strict_slashes=False)
    @require_member
    def member_home(member):
        error = None
        if request.method == "POST":
            try:
                action = request.form.get("action")
                with managed_db(get_db) as db:
                    db.execute("BEGIN IMMEDIATE")
                    current = db.execute(
                        "SELECT * FROM members WHERE id=? AND privacy_deleted=0",
                        (member["id"],),
                    ).fetchone()
                    access = db.execute(
                        "SELECT * FROM member_access WHERE member_id=?", (member["id"],)
                    ).fetchone()
                    if (
                        not current
                        or not access
                        or access["version"] != member["version"]
                    ):
                        abort(409)
                    if action == "profile":
                        # Fast kviteliste. Rolle, medlemsår, betaltstatus og e-post kjem aldri frå skjemaet.
                        values = {key: request.form.get(key, "") for key in FIELDS}
                        values.update(email=current["email"], terms="1", amount="5")
                        data, _ = validate(values, 500)
                        fields = [key for key in FIELDS if key != "email"]
                        full_name = " ".join(
                            data[k]
                            for k in ("fornamn", "mellomnamn", "etternamn")
                            if data[k]
                        )
                        db.execute(
                            "UPDATE members SET "
                            + ",".join(key + "=?" for key in fields)
                            + ",full_name=?,updated_at=? WHERE id=?",
                            [
                                data[key] or (None if key == "birth_date" else "")
                                for key in fields
                            ]
                            + [
                                full_name,
                                datetime.now(timezone.utc).isoformat(),
                                member["id"],
                            ],
                        )
                        pending = db.execute(
                            "SELECT desired FROM member_newsletter_jobs WHERE email=?",
                            (member["email"],),
                        ).fetchone()
                        if access["newsletter"] == 1 and not pending:
                            queue(db, member["id"], member["email"], 2)
                    elif action == "newsletter":
                        if request.form.get("newsletter") not in ("yes", "no"):
                            raise ValueError("Vel påmelding eller avmelding.")
                        choose(db, member, request.form["newsletter"] == "yes")
                    else:
                        abort(400)
                return redirect(prefix_url("member_home", saved=action), code=303)
            except ValueError as exc:
                error = str(exc)
        member = auth.member(session)
        if not member:
            return redirect(prefix_url("member_login"))
        with managed_db(get_db) as db:
            years = history(db, member["id"])
            state = payment_state(db, member)
            pending = bool(
                db.execute(
                    "SELECT 1 FROM member_newsletter_jobs WHERE member_id=?",
                    (member["id"],),
                ).fetchone()
            )
        return render_template(
            "mi_side.html",
            member=member,
            years=years,
            error=error,
            newsletter_pending=pending,
            saved=request.args.get("saved"),
            environment="test"
            if os.environ.get("VIPPS_SIGNUP_MODE") == "test"
            else None,
            **state,
        ), 400 if error else 200

    @app.post("/mi-side/betal")
    @require_member
    def member_pay(member):
        env = os.environ.get("VIPPS_SIGNUP_MODE", "disabled")
        if env not in ("test", "production"):
            abort(409, "Betaling er ikkje opna enno.")
        try:
            with managed_db(get_db) as db:
                state = payment_state(db, member)
                if not state["can_pay"]:
                    raise ValueError(
                        state["payment_error"]
                        or "Medlemskapen er allereie dekt for dette året."
                    )
            links = app.extensions["renewals"]
            _, token, _ = links.issue(
                member["id"], kontingent.today().year, env, access_kind="member"
            )
            link = links.resolve(token)
            ref = app.extensions["signup_service"].renew(link, request.form)
            session.update(
                renewal_link=link["id"],
                renewal_digest=link["token_hash"],
                signup_reference=ref,
            )
            return redirect(prefix_url("signup_status"), code=303)
        except ValueError as exc:
            return render_template(
                "medlem_melding.html",
                title="Betalinga kunne ikkje startast",
                message=str(exc),
                environment=None,
            ), 400

    @app.route("/mi-side/epost", methods=["GET", "POST"])
    @require_member
    def member_email(member):
        error = None
        if request.method == "POST":
            try:
                session["member_email_challenge"] = auth.start_email_change(
                    member,
                    request.form.get("email", ""),
                    request.remote_addr or "unknown",
                )
                return redirect(prefix_url("member_email_verify"), code=303)
            except ValueError as exc:
                error = str(exc)
        return render_template(
            "medlem_epost.html",
            stage="email",
            member=member,
            error=error,
            environment=None,
        ), 400 if error else 200

    @app.route("/mi-side/epost/stadfest", methods=["GET", "POST"])
    @require_member
    def member_email_verify(member):
        error = None
        if request.method == "POST":
            with managed_db(get_db) as db:
                db.execute("BEGIN IMMEDIATE")
                result = auth.change_email(
                    db,
                    member,
                    session.get("member_email_challenge", ""),
                    request.form.get("old_code", ""),
                    request.form.get("new_code", ""),
                )
                if result:
                    old_email, new_email, version = result
                    choose(db, {**member, "email": old_email}, False)
            if result:
                session.clear()
                session.permanent = True
                session.update(
                    member_id=member["id"],
                    member_version=version,
                    member_logged_at=time.time(),
                )
                return redirect(prefix_url("member_home", saved="email"), code=303)
            error = "Kodane er feil, brukte eller har gått ut, eller medlemsopplysningane er endra. Prøv igjen eller start e-postbytet på nytt."
        return render_template(
            "medlem_epost.html",
            stage="codes",
            member=member,
            error=error,
            environment=None,
        ), 400 if error else 200

    @app.get("/mi-side/last-ned")
    @require_member
    def member_export(member):
        with managed_db(get_db) as db:
            years = history(db, member["id"])
        data = {
            key: member[key]
            for key in (
                *FIELDS,
                "full_name",
                "membership_type",
                "payment_status",
                "consent_at",
                "created_at",
                "updated_at",
            )
        }
        data.update(medlemsar=years, nyhendebrev=member["newsletter"])
        response = jsonify(data)
        response.headers["Content-Disposition"] = (
            "attachment; filename=mine-medlemsopplysningar.json"
        )
        return response
