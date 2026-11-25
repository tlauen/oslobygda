"""Offentlege, vedtekne satsar frå same regelverk som betalingsskjemaet."""

import os
from flask import jsonify
from database import managed_db
from kontingent import payable, today


def install_public_rates(app, get_db):
    @app.get("/api/kontingent")
    def public_membership_rates():
        year = today().year
        data = {"year": year, "currency": "NOK", "open": False}
        with managed_db(get_db, commit_on_success=False) as db:
            try:
                policy = payable(db, year)
            except ValueError:
                policy = None
        if (
            policy is not None
            and os.environ.get("VIPPS_SIGNUP_MODE", "disabled") == "production"
        ):
            data.update(
                open=True,
                minimum_ore=policy["minimum_ore"],
                superkul_ore=policy["superkul_ore"],
            )
        response = jsonify(data)
        # Public policy only: no credentials, member data, drafts or old-year fallback.
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Cache-Control"] = "no-store"
        return response
