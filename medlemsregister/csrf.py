"""CSRF-vern for skjema og eksplisitte unntak for signerte maskinkall."""

import hmac
import secrets
from flask import abort, request, session


def csrf_exempt(view):
    """Bruk berre på ruter med eige autentiseringsvern eller utan sideeffektar.

    Plasser under @app.route/@app.post, slik at den registrerte view-funksjonen
    blir merkt. Markøren følgjer funksjonen ved endra endpoint-/blueprintnamn.
    """
    view._bygdelista_csrf_exempt = True
    return view


def install_csrf(app):
    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return session["csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def protect_changes():
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return
        view = app.view_functions.get(request.endpoint)
        if getattr(view, "_bygdelista_csrf_exempt", False):
            return
        expected = session.get("csrf_token", "")
        supplied = request.headers.get("X-CSRF-Token") or request.form.get(
            "csrf_token", ""
        )
        if not expected or not hmac.compare_digest(
            expected.encode(), supplied.encode()
        ):
            abort(400, "Ugyldig skjema. Last sida på nytt.")
