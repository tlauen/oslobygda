"""Opt-in, GET-only Report API for eiga ePayment-salseining."""

import os
import re
from datetime import datetime
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from arsdokument import stamp
from database import managed_db
from okonomi_automatikk import finance_lock
from okonomi_automatikk import fingerprint as digest
from vipps_client import VippsError


def fetch_reports(service, client_factory=None, max_pages=5):
    ledger = os.environ.get("VIPPS_REPORT_LEDGER_ID", "").strip()
    if os.environ.get("VIPPS_REPORT_FETCH_ENABLED") != "1" or not ledger:
        return {"new": 0, "known": 0}
    if not re.fullmatch(r"[0-9]{1,30}", ledger):
        raise ValueError("Ugyldig Report API-ledger.")
    if client_factory is None:
        from ny_innmelding import client_for

        client_factory = lambda: client_for("production")
    client = client_factory()
    msn = client.headers["Merchant-Serial-Number"]
    handle = "api:" + msn
    result = {"new": 0, "known": 0}
    with finance_lock(service.get_db, "reports") as renew:
        ledgers = client._authenticated(
            "GET",
            "/settlement/v1/ledgers?"
            + urlencode({"settlesForRecipientHandles": handle}),
        )
        matches = [
            item
            for item in ledgers.get("items", [])
            if str(item.get("ledgerId")) == ledger
        ]
        if (
            len(matches) != 1
            or matches[0].get("currency") != "NOK"
            or set(matches[0].get("settlesForRecipientHandles", [])) != {handle}
        ):
            raise ValueError(
                "Report API-ledgeren må tilhøyre berre denne ePayment-salseininga i NOK. Kontroller tilgang og ledger-ID."
            )
        with managed_db(service.get_db) as db:
            row = db.execute(
                "SELECT cursor FROM vipps_report_cursors WHERE ledger=?", (ledger,)
            ).fetchone()
            cursor = row[0] if row else None
        for _ in range(max_pages):
            renew()
            path = "/report/v2/ledgers/" + quote(ledger, safe="") + "/funds/feed"
            if cursor:
                path += "?" + urlencode({"cursor": cursor})
            data = client._authenticated("GET", path)
            if (
                not isinstance(data, dict)
                or not isinstance(data.get("items"), list)
                or len(data["items"]) > 10000
            ):
                raise VippsError("Rapporttenesta gav eit ugyldig svar.")
            entries = []
            for item in data["items"]:
                kind = {
                    "capture": "capture",
                    "refund": "refund",
                    "fees-retained": "fee",
                    "payout-scheduled": "payout",
                }.get(item.get("entryType"), "unknown")
                recipient = item.get("recipientHandle")
                if recipient and recipient != handle:
                    raise ValueError("Rapporten inneheld ei anna salseining.")
                if (
                    item.get("currency") != "NOK"
                    or type(item.get("amount")) is not int
                    or abs(item["amount"]) > 10**12
                ):
                    raise VippsError("Rapporttenesta gav eit ugyldig beløp.")
                amount = item["amount"]
                psp = str(item.get("pspReference") or "")
                if not psp or len(psp) > 200:
                    raise ValueError("Rapporthendinga manglar stabil identitet.")
                if (kind == "capture" and amount <= 0) or (
                    kind in ("refund", "payout") and amount >= 0
                ):
                    raise VippsError("Fortegn og rapporttype stemmer ikkje.")
                booking = datetime.fromisoformat(item["ledgerDate"]).date().isoformat()
                when = datetime.fromisoformat(item["time"].replace("Z", "+00:00"))
                if when.tzinfo is None:
                    raise ValueError("API-tidspunktet manglar tidssone.")
                day = (
                    when.astimezone(ZoneInfo("Europe/Oslo")).date().isoformat()
                    if kind in ("capture", "refund")
                    else booking
                )
                payout = psp.rsplit("-", 1)[-1] if kind == "payout" else ""
                payload = {
                    "msn": msn,
                    "kind": kind,
                    "reference": str(item.get("reference") or ""),
                    "psp_reference": psp,
                    "day": day,
                    "booking_day": booking,
                    "amount_ore": amount,
                    "payout": payout,
                }
                payload["origin"] = "api"
                identity = [msn, kind, psp]
                if kind == "unknown":
                    payload["original_type"] = str(item.get("entryType", ""))[:200]
                    identity.extend(
                        [
                            payload["original_type"],
                            item["time"],
                            item.get("balanceBefore"),
                            item.get("balanceAfter"),
                        ]
                    )
                entries.append((digest(identity), payload))
            counts = service.ingest_entries(entries)
            for key in result:
                result[key] += counts[key]
            next_cursor = data.get("cursor")
            if (
                not isinstance(next_cursor, str)
                or not next_cursor
                or len(next_cursor) > 10000
            ):
                raise VippsError("Rapporttenesta manglar gyldig framdriftsmarkør.")
            with managed_db(service.get_db) as db:
                db.execute(
                    "INSERT INTO vipps_report_cursors VALUES (?,?,?) ON CONFLICT(ledger) DO UPDATE SET cursor=excluded.cursor,updated_at=excluded.updated_at",
                    (ledger, next_cursor, stamp()),
                )
            if next_cursor == cursor or not data["items"] or data.get("tryLater"):
                break
            cursor = next_cursor
    return result


def automate_reports(service):
    with managed_db(service.get_db) as db:
        settings = db.execute(
            "SELECT * FROM payment_import_settings WHERE id=1 AND enabled=1"
        ).fetchone()
    if not settings:
        return {"new": 0, "known": 0, "booked": 0}
    result = fetch_reports(service)
    token, rows = service.preview(
        {}, "vedlikehald", persist=False, automatic_from=settings["from_day"]
    )
    # Direct income, refunds and unconfirmed payouts always remain in the review list.
    allowed = [
        row
        for row in rows
        if row.get("origin") == "api"
        and row["day"] >= settings["from_day"]
        and row["plan"]["status"] in ("ready", "link")
        and (row["kind"] in ("fee", "payout") or row["plan"]["status"] == "link")
    ]
    if not allowed:
        return {**result, "booked": 0}
    from okonomi_automatikk import save_preview

    with managed_db(service.get_db) as db:
        token = save_preview(db, "report", allowed, "vedlikehald")
    result["booked"] = len(service.approve(token, "vedlikehald"))
    return result
