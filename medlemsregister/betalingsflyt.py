"""Kø, samla kontroll og avgrensa automatisk bokføring."""

import json

from arsdokument import stamp
from database import managed_db
from okonomi_automatikk import attempt, finance_lock, load_preview, save_preview
from vipps_client import VippsError


class PaymentFlow:
    def __init__(self, service):
        self.service = service
        self.get_db = service.get_db

    def candidates(self, db, limit):
        return [
            row[0]
            for row in db.execute(
                """SELECT DISTINCT p.id FROM payments p
          JOIN signup_orders o ON o.payment_id=p.id LEFT JOIN payment_attempts a ON a.payment_id=p.id
          WHERE o.environment='production' AND o.status IN ('complete','review','redacted')
          AND (a.next_at IS NULL OR a.next_at<=?)
          AND (a.status IS NULL OR a.status!='historical' OR EXISTS(SELECT 1 FROM payment_ledger_links l WHERE l.payment_id=p.id))
          ORDER BY CASE WHEN a.payment_id IS NULL THEN 0 ELSE 1 END,
          COALESCE(a.attempted_at,''),p.id LIMIT ?""",
                (stamp(), limit),
            )
        ]

    def inspect(self, pid, fetch, client_factory=None, automatic=False):
        service = self.service
        if fetch:
            service.fetch(pid, "betalingskontroll", client_factory)
        with managed_db(self.get_db) as db:
            payment, _order, evidence = service._evidence(db, pid)
            linked = service._linked(db, pid)
            if linked:
                service._check_link(db, linked, payment, evidence)
                attempt(db, pid, "booked")
                return {"payment_id": pid, "status": "booked", "journal_id": linked}
            settings = db.execute(
                "SELECT * FROM payment_import_settings WHERE id=1"
            ).fetchone()
            if settings and evidence["day"] < settings["from_day"]:
                attempt(db, pid, "historical")
                return {"payment_id": pid, "status": "historical"}
            candidates = service._candidates(db, payment, evidence)
            if candidates:
                raise ValueError(
                    "Mogleg eksisterande føring. Kople til rett post etter kontroll."
                )
            member = db.execute(
                "SELECT full_name FROM members WHERE id=?", (payment["member_id"],)
            ).fetchone()
            return {
                "payment_id": pid,
                "evidence_id": evidence["id"],
                "amount_ore": payment["amount_ore"],
                "for_year": payment["for_year"],
                "day": evidence["day"],
                "name": member[0] if member else "Medlem",
                "status": "ready",
            }

    def record_error(self, pid, exc):
        message = (
            str(exc)
            if isinstance(exc, ValueError) and not isinstance(exc, VippsError)
            else "Vipps kunne ikkje kontrollerast. Systemet prøver igjen seinare."
        )
        with managed_db(self.get_db) as db:
            attempt(db, pid, "error", message)
            db.execute(
                "INSERT INTO payment_import_errors VALUES (?,?,?) ON CONFLICT(payment_id) DO UPDATE SET message=excluded.message,checked_at=excluded.checked_at",
                (pid, message[:500], stamp()),
            )
        return {"payment_id": pid, "status": "review", "message": message[:500]}

    def preview(self, actor, limit=20, client_factory=None):
        rows = []
        with finance_lock(self.get_db, "payments") as renew:
            with managed_db(self.get_db) as db:
                pids = self.candidates(db, min(200, max(1, limit)))
            for pid in pids:
                renew()
                try:
                    rows.append(self.inspect(pid, True, client_factory))
                except (ValueError, VippsError, KeyError, TypeError) as exc:
                    rows.append(self.record_error(pid, exc))
            with managed_db(self.get_db) as db:
                token = save_preview(db, "payments", rows, actor)
        return token, rows

    def approve(self, token, actor):
        with managed_db(self.get_db) as db:
            db.execute("BEGIN IMMEDIATE")
            row, rows = load_preview(db, token, "payments")
            if row["applied_at"]:
                return json.loads(row["result"])
            result = []
            for item in rows:
                if item["status"] != "ready":
                    continue
                payment, _order, evidence = self.service._evidence(
                    db, item["payment_id"]
                )
                if (
                    any(evidence[key] != item[key] for key in ("amount_ore", "day"))
                    or payment["for_year"] != item["for_year"]
                ):
                    raise ValueError(
                        "Betalingsgrunnlaget er endra. Kontroller på nytt."
                    )
                jid = self.service.book_in_db(
                    db, item["payment_id"], item["evidence_id"], actor
                )
                attempt(db, item["payment_id"], "booked")
                result.append(jid)
            db.execute(
                "UPDATE finance_previews SET applied_at=?,result=? WHERE token=?",
                (stamp(), json.dumps(result), token),
            )
            return result

    def run(self, fetch=False, limit=50, client_factory=None):
        counts = {"checked": 0, "booked": 0, "review": 0}
        with managed_db(self.get_db) as db:
            if not db.execute(
                "SELECT 1 FROM payment_import_settings WHERE id=1 AND enabled=1"
            ).fetchone():
                return counts
        try:
            with finance_lock(self.get_db, "payments") as renew:
                with managed_db(self.get_db) as db:
                    run = db.execute(
                        "INSERT INTO finance_runs(kind,started_at) VALUES ('payments',?)",
                        (stamp(),),
                    ).lastrowid
                    pids = self.candidates(db, min(200, max(1, limit)))
                for pid in pids:
                    renew()
                    try:
                        item = self.inspect(pid, fetch, client_factory, True)
                        if fetch:
                            counts["checked"] += 1
                        if item["status"] == "ready":
                            self.service.book(
                                pid, item["evidence_id"], "vedlikehald", automatic=True
                            )
                            counts["booked"] += 1
                            with managed_db(self.get_db) as db:
                                attempt(db, pid, "booked")
                    except (ValueError, VippsError, KeyError, TypeError) as exc:
                        self.record_error(pid, exc)
                        counts["review"] += 1
                with managed_db(self.get_db) as db:
                    db.execute(
                        "UPDATE finance_runs SET finished_at=?,counts=? WHERE id=?",
                        (stamp(), json.dumps(counts), run),
                    )
        except ValueError as exc:
            if "køyrer allereie" not in str(exc):
                raise
        return counts
