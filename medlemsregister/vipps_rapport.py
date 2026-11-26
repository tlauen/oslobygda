"""Vipps CSV: varige kjelder, duplikatvern og eksplisitt avstemming."""

import csv
import io
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from arsdokument import canonical, stamp, today
from database import managed_db
from okonomi_automatikk import fingerprint as digest
from okonomi_automatikk import load_preview, save_preview
from rekneskap import Ledger, iso_day, label

HEADERS = {
    "msn": ("MSN/Vippsnummer", "MSN/Vipps number", "MSN/MobilePay number"),
    "day": ("Bokføringsdato", "Booking date"),
    "time": ("Tidspunkt", "Time"),
    "kind": ("Type",),
    "amount": ("Beløp", "Amount"),
    "currency": ("Valuta", "Currency"),
    "psp": ("PSP-referanse", "PSP reference"),
    "reference": ("Ordre-ID/Referanse", "Order ID/Reference"),
    "payout": ("Utbetalingsnummer", "Payout number"),
}
KINDS = {
    "belastning": "capture",
    "capture": "capture",
    "refusjon": "refund",
    "refund": "refund",
    "gebyrer fratrukket": "fee",
    "fees deducted": "fee",
    "utbetaling planlagt": "payout",
    "payout scheduled": "payout",
}


def money(raw):
    try:
        value = Decimal(
            str(raw).strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
        )
        if (
            not value.is_finite()
            or value * 100 != (value * 100).to_integral_value()
            or abs(value) > 10**10
        ):
            raise ValueError()
        return int(value * 100)
    except (InvalidOperation, ValueError):
        raise ValueError("Rapporten har eit ugyldig beløp.") from None


def csv_rows(content):
    if len(content) > 3 * 1024 * 1024:
        raise ValueError("Rapporten må vere høgst 3 MiB.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Lagre rapporten som UTF-8 CSV.") from None
    try:
        delimiter = csv.Sniffer().sniff(text[:8000], delimiters=",;\t").delimiter
    except csv.Error:
        raise ValueError("Kunne ikkje lese kolonnane i CSV-fila.") from None
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError("Ugyldige eller doble kolonnenamn.")
    rows = list(reader)
    if len(rows) > 10000:
        raise ValueError("Rapporten kan ha høgst 10 000 rader.")
    return reader.fieldnames, rows


def parse_report(content, msn):
    headers, rows = csv_rows(content)
    mapping = {
        key: next((name for name in names if name in headers), None)
        for key, names in HEADERS.items()
    }
    if any(
        not mapping[k]
        for k in ("msn", "day", "kind", "amount", "currency", "psp", "reference")
    ):
        raise ValueError(
            "Bruk den nye oppgjørsrapporten frå Vipps i norsk eller engelsk CSV-format."
        )
    result = []
    for row in rows:

        def val(key, row=row):
            return str(row.get(mapping.get(key)) or "").strip()

        if val("msn") != msn:
            raise ValueError(
                "Rapporten inneheld eit anna Vippsnummer/MSN. Eksporter eitt salssted om gongen."
            )
        if val("currency") != "NOK":
            raise ValueError("Berre rapportar i NOK kan importerast.")
        kind = KINDS.get(val("kind").lower(), "unknown")
        day = iso_day(val("day"))
        booking_day = day
        if kind in ("capture", "refund") and val("time"):
            try:
                when = datetime.fromisoformat(val("time").replace("Z", "+00:00"))
                if when.tzinfo:
                    when = when.astimezone(ZoneInfo("Europe/Oslo"))
                day = when.date().isoformat()
            except ValueError:
                raise ValueError(
                    "Ugyldig tidspunkt. Bruk originalrapporten frå Vipps."
                ) from None
        if day > today().isoformat():
            raise ValueError("Rapporten har datoar i framtida.")
        amount = money(val("amount"))
        if not amount:
            continue
        if (kind == "capture" and amount < 0) or (
            kind in ("refund", "payout") and amount > 0
        ):
            raise ValueError("Fortegn og hendingstype i rapporten stemmer ikkje.")
        psp = label(val("psp"), 200)
        ref = label(val("reference"), 200)
        payout = label(val("payout"), 200)
        identity = psp or (payout if kind == "payout" else "")
        if not identity:
            raise ValueError(
                "Ei rad manglar stabil referanse. Ingen automatisk import er utført."
            )
        payload = {
            "msn": msn,
            "kind": kind,
            "reference": ref,
            "psp_reference": psp,
            "day": day,
            "booking_day": booking_day,
            "amount_ore": amount,
            "payout": payout,
        }
        result.append((digest([msn, kind, identity]), payload))
    return result


class ReportImport:
    def __init__(self, get_db, update_member=None):
        self.get_db = get_db
        self.ledger = Ledger(get_db)
        self.update_member = update_member

    def ingest(self, content, msn):
        return self.ingest_entries(parse_report(content, label(msn, 30, True)))

    def ingest_entries(self, entries):
        counts = {"new": 0, "known": 0}
        with managed_db(self.get_db) as db:
            db.execute("BEGIN IMMEDIATE")
            for identity, payload in entries:
                if (
                    type(payload.get("amount_ore")) is not int
                    or abs(payload["amount_ore"]) > 10**12
                    or iso_day(payload["day"]) > today().isoformat()
                ):
                    raise ValueError("Ugyldig beløp eller framtidig rapportdato.")
                raw = canonical(payload)
                fingerprint = digest(
                    {
                        k: payload[k]
                        for k in ("msn", "kind", "psp_reference", "day", "amount_ore")
                    }
                )
                old = db.execute(
                    "SELECT content_hash,reference FROM vipps_report_entries WHERE identity=?",
                    (identity,),
                ).fetchone()
                if old:
                    if old[0] != fingerprint or (
                        payload["kind"] in ("capture", "refund")
                        and old["reference"]
                        and payload["reference"]
                        and old["reference"] != payload["reference"]
                    ):
                        raise ValueError(
                            "Same Vipps-referanse har endra innhald. Avklar avviket før import."
                        )
                    counts["known"] += 1
                    continue
                db.execute(
                    "INSERT INTO vipps_report_entries(identity,msn,kind,reference,psp_reference,day,amount_ore,payload,content_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        identity,
                        *(
                            payload[k]
                            for k in (
                                "msn",
                                "kind",
                                "reference",
                                "psp_reference",
                                "day",
                                "amount_ore",
                            )
                        ),
                        raw,
                        fingerprint,
                        stamp(),
                    ),
                )
                counts["new"] += 1
        return counts

    def source_match(self, db, row):
        if row["kind"] != "capture":
            return None
        orders = db.execute(
            "SELECT payment_id FROM signup_orders WHERE environment='production' AND msn=? AND reference=? AND amount_ore=? AND payment_id IS NOT NULL",
            (row["msn"], row["reference"], row["amount_ore"]),
        ).fetchall()
        if len(orders) == 1:
            return orders[0][0]
        return None

    def plan(self, db, row, choice):
        if row["journal_id"]:
            if db.execute(
                "SELECT 1 FROM ledger_journals WHERE reversal_of=?",
                (row["journal_id"],),
            ).fetchone():
                return {
                    "status": "review",
                    "message": "Kopla post er reversert. Avklar rettinga i rekneskapen før kjelda blir rekna som avstemd.",
                }
            return {"status": "booked", "journal_id": row["journal_id"]}
        from betalingsimport import PaymentImport

        payment_id = self.source_match(db, row)
        if payment_id:
            service = PaymentImport(self.get_db)
            linked = service._linked(db, payment_id)
            if not linked:
                return {
                    "status": "review",
                    "message": "Skjemabetaling: bruk den automatiske medlemsimporten først.",
                }
            payment, _order, evidence = service._evidence(db, payment_id)
            service._check_link(db, linked, payment, evidence)
            return {"status": "link", "journal_id": linked}
        kind = row["kind"]
        amount = abs(row["amount_ore"])
        category = choice.get("category", "")
        if kind == "capture":
            if category not in (
                "membership",
                "donations",
                "event_income",
                "other_income",
            ):
                return {"status": "review", "message": "Vel kva innbetalinga gjeld."}
            if category == "membership":
                member_id = int(choice.get("member_id") or 0)
                year = int(choice.get("year") or 0)
                if (
                    not db.execute(
                        "SELECT 1 FROM members WHERE id=?", (member_id,)
                    ).fetchone()
                    or not 2026 <= year <= 2200
                ):
                    return {
                        "status": "review",
                        "message": "Vel medlem og medlemsår. Betalarnamn er ikkje ein sikker medlemskopling.",
                    }
            if (
                category == "membership"
                and not choice.get("existing_journal")
                and db.execute(
                    "SELECT 1 FROM payments WHERE member_id=? AND for_year=? AND amount_ore=? AND substr(paid_at,1,10)=?",
                    (member_id, year, amount, row["day"]),
                ).fetchone()
            ):
                return {
                    "status": "review",
                    "message": "Medlemsbetalinga finst frå før. Kople henne til rekneskapen under Medlemspengar og oppgi P-nummeret her.",
                }
            lines = [("vipps", amount, ""), (category, -amount, "")]
        elif kind == "fee":
            lines = [("fees", -row["amount_ore"], ""), ("vipps", row["amount_ore"], "")]
            category = "fees"
        elif kind == "payout":
            confirmation = db.execute(
                "SELECT * FROM vipps_bank_confirmations WHERE identity=?",
                (row["identity"],),
            ).fetchone()
            if not confirmation:
                return {
                    "status": "review",
                    "message": "Ventar på samsvarande bankinnbetaling. Planlagt utbetaling er ikkje bankprov.",
                }
            lines = [("bank", amount, ""), ("vipps", -amount, "")]
            category = "payout"
        elif kind == "refund":
            original = int(choice.get("original_journal") or 0)
            journal = db.execute(
                "SELECT * FROM ledger_journals WHERE id=? AND state='posted' AND reversal_of IS NULL",
                (original,),
            ).fetchone()
            original_lines = db.execute(
                "SELECT account,amount_ore FROM ledger_lines WHERE journal_id=?",
                (original,),
            ).fetchall()
            income = [
                r
                for r in original_lines
                if r["account"]
                in ("membership", "donations", "event_income", "other_income")
                and r["amount_ore"] < 0
            ]
            if (
                not journal
                or len(income) != 1
                or ("vipps", -income[0]["amount_ore"])
                not in [(r["account"], r["amount_ore"]) for r in original_lines]
            ):
                return {
                    "status": "review",
                    "message": "Vel den opphavlege Vipps-inntekta for refusjonen.",
                }
            if db.execute(
                "SELECT 1 FROM ledger_journals WHERE reversal_of=?", (original,)
            ).fetchone():
                raise ValueError("Originalposten er reversert.")
            used = db.execute(
                "SELECT COALESCE(SUM(l.amount_ore),0) FROM ledger_journals j JOIN ledger_lines l ON l.journal_id=j.id WHERE j.related_to=? AND l.account=? AND l.amount_ore>0 AND NOT EXISTS(SELECT 1 FROM ledger_journals r WHERE r.reversal_of=j.id)",
                (original, income[0]["account"]),
            ).fetchone()[0]
            if used + amount > -income[0]["amount_ore"]:
                raise ValueError("Samla refusjon er større enn originalinntekta.")
            lines = [(income[0]["account"], amount, ""), ("vipps", -amount, "")]
            category = "refund"
        else:
            return {
                "status": "review",
                "message": "Denne rapporttypen krev manuell behandling.",
            }
        day = confirmation["day"] if kind == "payout" else row["day"]
        candidates = [
            r[0]
            for r in db.execute(
                "SELECT DISTINCT j.id FROM ledger_journals j JOIN ledger_lines l ON l.journal_id=j.id WHERE j.day=? AND j.state='posted' AND (j.source_kind IS NULL OR j.source_kind NOT IN ('membership_payment','vipps_report')) AND l.account=? AND l.amount_ore=? AND NOT EXISTS(SELECT 1 FROM ledger_journals r WHERE r.reversal_of=j.id)",
                (day, lines[0][0], lines[0][1]),
            )
        ]
        if candidates and not choice.get("existing_journal"):
            return {
                "status": "review",
                "message": "Mogleg eksisterande føring: "
                + ", ".join("P" + str(n) for n in candidates)
                + ". Oppgi rett P-nummer etter kontroll.",
            }
        if choice.get("existing_journal"):
            jid = int(choice["existing_journal"])
            existing = db.execute(
                "SELECT * FROM ledger_journals WHERE id=?", (jid,)
            ).fetchone()
            existing_lines = sorted(
                tuple(r)
                for r in db.execute(
                    "SELECT account,amount_ore,party FROM ledger_lines WHERE journal_id=?",
                    (jid,),
                )
            )
            if (
                not existing
                or existing["day"] != day
                or existing_lines != sorted(lines)
                or db.execute(
                    "SELECT 1 FROM ledger_journals WHERE reversal_of=?", (jid,)
                ).fetchone()
            ):
                raise ValueError(
                    "Den eksisterande posten har ikkje same dato, konto og beløp."
                )
            if db.execute(
                "SELECT 1 FROM vipps_report_entries WHERE journal_id=? AND identity!=?",
                (jid, row["identity"]),
            ).fetchone():
                raise ValueError("Posten er kopla til ei anna rapportrad.")
            return {"status": "link", "journal_id": jid}
        return {"status": "ready", "lines": lines, "day": day, "category": category}

    def preview(
        self, choices, actor, persist=True, automatic_from=None, identities=None
    ):
        rows = []
        with managed_db(self.get_db) as db:
            query = "SELECT * FROM vipps_report_entries WHERE (journal_id IS NULL OR EXISTS(SELECT 1 FROM ledger_journals r WHERE r.reversal_of=vipps_report_entries.journal_id))"
            args = ()
            if identities is not None:
                if not identities or len(identities) > 200:
                    raise ValueError("Vel ei gyldig side med rapportkjelder.")
                query += " AND identity IN (" + ",".join("?" for _ in identities) + ")"
                args = tuple(identities)
            if automatic_from:
                query += " AND day>=? AND (kind IN ('fee','payout') OR (kind='capture' AND EXISTS(SELECT 1 FROM signup_orders o WHERE o.environment='production' AND o.reference=vipps_report_entries.reference AND o.msn=vipps_report_entries.msn)))"
                args = (*args, automatic_from)
            query += " ORDER BY day DESC,identity" + (
                "" if automatic_from else " LIMIT 200"
            )
            for row in db.execute(query, args):
                choice = choices.get(row["identity"], {})
                try:
                    plan = self.plan(db, row, choice)
                except (ValueError, TypeError) as exc:
                    plan = {"status": "review", "message": str(exc)}
                rows.append(
                    {
                        "identity": row["identity"],
                        "content_hash": row["content_hash"],
                        "choice": choice,
                        "plan": plan,
                        "amount_ore": row["amount_ore"],
                        "day": row["day"],
                        "kind": row["kind"],
                        "origin": json.loads(row["payload"]).get("origin", "csv"),
                    }
                )
            token = save_preview(db, "report", rows, actor) if persist else None
        return token, rows

    def approve(self, token, actor):
        with managed_db(self.get_db) as db:
            db.execute("BEGIN IMMEDIATE")
            preview, rows = load_preview(db, token, "report")
            if preview["applied_at"]:
                return json.loads(preview["result"])
            result = []
            for item in rows:
                if item["plan"]["status"] not in ("ready", "link"):
                    continue
                row = db.execute(
                    "SELECT * FROM vipps_report_entries WHERE identity=?",
                    (item["identity"],),
                ).fetchone()
                if row["journal_id"]:
                    continue
                plan = self.plan(db, row, item["choice"])
                if row["content_hash"] != item["content_hash"] or canonical(
                    plan
                ) != canonical(item["plan"]):
                    raise ValueError(
                        "Grunnlaget er endra. Kontroller rapporten på nytt."
                    )
                if plan["status"] == "link":
                    jid = plan["journal_id"]
                else:
                    category = plan["category"]
                    original = int(item["choice"].get("original_journal") or 0)
                    text = {
                        "membership": "Medlemskontingent",
                        "donations": "Gåve",
                        "fees": "Vipps-gebyr",
                        "payout": "Vipps-oppgjer til bank",
                        "refund": "Refusjon av inntekt",
                        "event_income": "Tilskipingsinntekt",
                        "other_income": "Anna innkome",
                    }[category]
                    if category == "membership":
                        from betalingsimport import PaymentImport

                        mid = int(item["choice"]["member_id"])
                        year = int(item["choice"]["year"])
                        # A manually registered payment may already exist. Link it explicitly instead of guessing.
                        if db.execute(
                            "SELECT 1 FROM payments WHERE member_id=? AND amount_ore=? AND substr(paid_at,1,10)=?",
                            (mid, row["amount_ore"], row["day"]),
                        ).fetchone():
                            raise ValueError(
                                "Medlemsbetalinga kan vere registrert frå før. Avklar koplinga manuelt."
                            )
                        pid = db.execute(
                            "INSERT INTO payments(member_id,amount_ore,paid_at,created_at,for_year) VALUES (?,?,?,?,?)",
                            (mid, row["amount_ore"], row["day"], stamp(), year),
                        ).lastrowid
                        service = PaymentImport(self.get_db)
                        eid = service._record(
                            db,
                            pid,
                            {
                                "amount_ore": row["amount_ore"],
                                "day": row["day"],
                                "account": "vipps",
                                "captured_ore": row["amount_ore"],
                                "refunded_ore": 0,
                                "source": "vipps-report",
                                "source_reference": row["psp_reference"],
                            },
                            actor,
                            "Kontrollert Vipps-oppgjørsrapport.",
                        )
                        jid = service.book_in_db(db, pid, eid, actor)
                        if self.update_member:
                            self.update_member(db, mid)
                    else:
                        jid = self.ledger._post(
                            db,
                            plan["day"],
                            plan["lines"],
                            text,
                            "Rapportimport",
                            actor,
                            "vipps-report-" + row["identity"],
                            "Vipps-rapport kontrollert.",
                            source_kind="income_refund"
                            if category == "refund"
                            else "vipps_report",
                            source_id=row["identity"],
                            related_to=original or None,
                        )
                db.execute(
                    "UPDATE vipps_report_entries SET journal_id=?,resolution=? WHERE identity=?",
                    (
                        jid,
                        "linked" if plan["status"] == "link" else "booked",
                        row["identity"],
                    ),
                )
                result.append(jid)
            db.execute(
                "UPDATE finance_previews SET applied_at=?,result=? WHERE token=?",
                (stamp(), json.dumps(result), token),
            )
            return result

    def confirm_bank(self, identity, day, amount, reference, actor):
        day = iso_day(day)
        amount = money(amount)
        reference = label(reference, 500, True)
        with managed_db(self.get_db) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM vipps_report_entries WHERE identity=? AND kind='payout'",
                (identity,),
            ).fetchone()
            if (
                not row
                or amount != -row["amount_ore"]
                or day < row["day"]
                or day > today().isoformat()
            ):
                raise ValueError(
                    "Bankdato og beløp må svare til faktisk oppgjer. Kontroller kontoutskrifta."
                )
            old = db.execute(
                "SELECT * FROM vipps_bank_confirmations WHERE identity=?", (identity,)
            ).fetchone()
            if old:
                if (old["day"], old["amount_ore"], old["bank_reference"]) != (
                    day,
                    amount,
                    reference,
                ):
                    raise ValueError("Oppgjeret har anna bankgrunnlag frå før.")
                return
            db.execute(
                "INSERT INTO vipps_bank_confirmations VALUES (?,?,?,?,?,?)",
                (identity, day, amount, reference, actor, stamp()),
            )

    def bank_csv(self, content, actor):
        headers, rows = csv_rows(content)
        aliases = {
            "day": ("Dato", "Date", "Bokføringsdato"),
            "amount": ("Beløp", "Amount"),
            "reference": ("Referanse", "Reference", "Melding"),
        }
        mapping = {
            k: next((n for n in names if n in headers), None)
            for k, names in aliases.items()
        }
        if not all(mapping.values()):
            raise ValueError("Bankfila må ha kolonnane Dato, Beløp og Referanse.")
        matched = 0
        with managed_db(self.get_db) as db:
            db.execute("BEGIN IMMEDIATE")
            for raw in rows:
                amount = money(raw[mapping["amount"]])
                reference = raw[mapping["reference"]].strip()
                day = iso_day(raw[mapping["day"]])
                if amount <= 0:
                    continue
                candidates = []
                for row in db.execute(
                    "SELECT * FROM vipps_report_entries WHERE kind='payout' AND amount_ore=?",
                    (-amount,),
                ):
                    number = json.loads(row["payload"])["payout"]
                    if (
                        number
                        and len(number) >= 5
                        and __import__("re").search(
                            r"(?<!\d)" + __import__("re").escape(number) + r"(?!\d)",
                            reference,
                        )
                    ):
                        candidates.append(row)
                if len(candidates) != 1:
                    continue
                row = candidates[0]
                if day < row["day"] or day > today().isoformat():
                    raise ValueError("Bankdatoen stemmer ikkje med planlagt oppgjer.")
                old = db.execute(
                    "SELECT * FROM vipps_bank_confirmations WHERE identity=?",
                    (row["identity"],),
                ).fetchone()
                if old:
                    if (old["day"], old["amount_ore"], old["bank_reference"]) != (
                        day,
                        amount,
                        reference,
                    ):
                        raise ValueError("Same oppgjer har motstridande bankgrunnlag.")
                    continue
                db.execute(
                    "INSERT INTO vipps_bank_confirmations VALUES (?,?,?,?,?,?)",
                    (row["identity"], day, amount, reference, actor, stamp()),
                )
                matched += 1
        return matched
