"""Styreverna medlemsruter, betalingar, årsoversikt og innsynseksport.

Database- og årsfunksjonar blir sende inn av appen; ingen import frå app.py.
Rutene blir registrerte med dei eksisterande endepunktnamna.
"""

import csv
import io
from datetime import date, datetime, timezone
from flask import request, jsonify, Response
from betalingsreglar import manual_amount_ore as _nok_to_ore
from database import managed_db
from personvern import erase_member


def _build_full_name(fornamn, mellomnamn, etternamn):
    return " ".join(filter(None, [fornamn, mellomnamn, etternamn])).strip()


def _medlemstype_visning(membership_type: str, *, med_beskrivelse: bool = False) -> str:
    """Returner visningsnamn for medlemstype (vanleg→Kul, kul→Superkul)."""
    if membership_type == "styret":
        return "Styret"
    if membership_type == "kul":
        return "Superkul (meir enn 5 kr)" if med_beskrivelse else "Superkul"
    return "Kul (5 kr)" if med_beskrivelse else "Kul"


def _csv_cell(value):
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(
        ("\t", "\r", "\n")
    ):
        return "'" + text
    return text


def install_members(
    app, get_db, require_admin, get_year, get_threshold, refresh_member, refresh_all
):
    @app.route("/api/members", methods=["GET"])
    @require_admin
    def list_members():
        try:
            with managed_db(get_db) as conn:
                ar = get_year(conn)
                rows = conn.execute(
                    """SELECT m.id, m.full_name, m.fornamn, m.mellomnamn, m.etternamn, m.email, m.phone, m.adresse, m.postnummer, m.poststad,
                              m.birth_date, m.membership_type, m.payment_status, m.consent_at, m.created_at, m.updated_at,
                              COALESCE(SUM(CASE WHEN p.for_year = ? THEN p.amount_ore ELSE 0 END), 0) AS total_paid_ore
                       FROM members m
                       LEFT JOIN payments p ON p.member_id = m.id
                       WHERE m.privacy_deleted=0
                       GROUP BY m.id
                       ORDER BY m.full_name""",
                    (ar,),
                ).fetchall()
            return jsonify([dict(r) for r in rows])
        except Exception:
            app.logger.exception("Kunne ikkje hente medlemsoversikta")
            return jsonify({"error": "Kunne ikkje hente medlemsoversikta."}), 500

    @app.route("/api/members", methods=["POST"])
    @require_admin
    def create_member():
        data = request.get_json() or {}
        fornamn = (data.get("fornamn") or "").strip()
        mellomnamn = (data.get("mellomnamn") or "").strip()
        etternamn = (data.get("etternamn") or "").strip()
        full_name = _build_full_name(fornamn, mellomnamn, etternamn)
        email = (data.get("email") or "").strip().lower()
        phone = (data.get("phone") or "").strip()
        adresse = (data.get("adresse") or "").strip()
        postnummer = (data.get("postnummer") or "").strip()
        poststad = (data.get("poststad") or "").strip()
        birth_date = (data.get("birth_date") or "").strip() or None
        membership_type = (data.get("membership_type") or "").strip()
        payment_status = (data.get("payment_status") or "").strip()
        consent_at = data.get("consent_at") or datetime.now(timezone.utc).isoformat()

        if not fornamn or not etternamn:
            return jsonify({"error": "Fornamn og etternamn er påkrevd"}), 400
        if not email:
            return jsonify({"error": "Epost er påkrevd"}), 400
        if not membership_type:
            membership_type = "vanleg"
        if not payment_status:
            payment_status = "ikkje betalt"

        now = datetime.now(timezone.utc).isoformat()
        with managed_db(get_db) as conn:
            cur = conn.execute(
                """INSERT INTO members (full_name, fornamn, mellomnamn, etternamn, email, phone, adresse, postnummer, poststad, birth_date, membership_type, payment_status, consent_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    full_name,
                    fornamn,
                    mellomnamn,
                    etternamn,
                    email,
                    phone,
                    adresse,
                    postnummer,
                    poststad,
                    birth_date,
                    membership_type,
                    payment_status,
                    consent_at,
                    now,
                    now,
                ),
            )
            mid = cur.lastrowid
            if payment_status in ("gratis", "betalt"):
                from personvern_vedlikehald import approve_year

                approve_year(conn, mid, get_year(conn), payment_status)
        return jsonify({"id": mid, "message": "Medlem lagt til"}), 201

    @app.route("/api/members/<int:mid>", methods=["GET", "PUT", "DELETE"])
    @require_admin
    def member(mid):
        with managed_db(get_db) as conn:
            row = conn.execute(
                "SELECT * FROM members WHERE id = ? AND privacy_deleted=0", (mid,)
            ).fetchone()
        if not row:
            return jsonify({"error": "Medlem finst ikkje"}), 404
        row = dict(row)

        if request.method == "GET":
            return jsonify(row)

        if request.method == "PUT":
            data = request.get_json() or {}
            fornamn = (data.get("fornamn", row.get("fornamn")) or "").strip()
            mellomnamn = (data.get("mellomnamn", row.get("mellomnamn")) or "").strip()
            etternamn = (data.get("etternamn", row.get("etternamn")) or "").strip()
            full_name = _build_full_name(fornamn, mellomnamn, etternamn)
            email = (data.get("email", row.get("email")) or "").strip().casefold()
            phone = (data.get("phone", row.get("phone")) or "").strip()
            adresse = (data.get("adresse", row.get("adresse")) or "").strip()
            postnummer = (data.get("postnummer", row.get("postnummer")) or "").strip()
            poststad = (data.get("poststad", row.get("poststad")) or "").strip()
            birth_date = (
                data.get("birth_date", row.get("birth_date")) or ""
            ).strip() or None
            membership_type = (
                data.get("membership_type", row.get("membership_type")) or ""
            ).strip()
            payment_status = (
                data.get("payment_status", row.get("payment_status")) or ""
            ).strip()
            if not fornamn or not etternamn:
                return jsonify({"error": "Fornamn og etternamn er påkrevd"}), 400
            if not email:
                return jsonify({"error": "Epost er påkrevd"}), 400
            now = datetime.now(timezone.utc).isoformat()
            with managed_db(get_db) as conn:
                conn.execute("BEGIN IMMEDIATE")
                current = conn.execute(
                    "SELECT * FROM members WHERE id=? AND privacy_deleted=0", (mid,)
                ).fetchone()
                if not current or dict(current) != row:
                    return jsonify(
                        {"error": "Medlemmen er endra. Last opplysningane på nytt."}
                    ), 409
                if email != row["email"]:
                    from medlem_auth import update_email
                    from medlem_nyhendebrev import choose

                    try:
                        update_email(conn, row, email)
                    except ValueError as exc:
                        return jsonify({"error": str(exc)}), 409
                    choose(conn, row, False)
                conn.execute(
                    """UPDATE members SET full_name=?, fornamn=?, mellomnamn=?, etternamn=?, email=?, phone=?, adresse=?, postnummer=?, poststad=?, birth_date=?, membership_type=?, payment_status=?, updated_at=?
                       WHERE id=?""",
                    (
                        full_name,
                        fornamn,
                        mellomnamn,
                        etternamn,
                        email,
                        phone,
                        adresse,
                        postnummer,
                        poststad,
                        birth_date,
                        membership_type,
                        payment_status,
                        now,
                        mid,
                    ),
                )
                # Ein uendra status i eit fullt profilskjema er ikkje eit nytt vedtak.
                if "payment_status" in data and (
                    payment_status != row["payment_status"]
                    or data.get("approve_payment_status") is True
                    or set(data) == {"payment_status"}
                ):
                    from personvern_vedlikehald import approve_year

                    if payment_status in ("gratis", "betalt"):
                        approve_year(conn, mid, get_year(conn), payment_status)
                    elif payment_status == "ikkje betalt":
                        conn.execute(
                            "DELETE FROM free_membership_years WHERE member_id=? AND for_year=?",
                            (mid, get_year(conn)),
                        )
                        conn.execute(
                            "DELETE FROM paid_membership_years WHERE member_id=? AND for_year=?",
                            (mid, get_year(conn)),
                        )
                conn.commit()
            return jsonify({"message": "Oppdatert"})

        if request.method == "DELETE":
            with managed_db(get_db) as conn:
                conn.execute("BEGIN IMMEDIATE")
                result, status = erase_member(conn, mid)
            return jsonify(result), status

        return jsonify({"error": "Ugyldig metode"}), 405

    @app.route("/api/members/<int:mid>/payments", methods=["GET", "POST"])
    @require_admin
    def member_payments(mid):
        with managed_db(get_db) as conn:
            member_exists = conn.execute(
                "SELECT 1 FROM members WHERE id = ? AND privacy_deleted=0", (mid,)
            ).fetchone()
            if not member_exists:
                return jsonify({"error": "Medlem finst ikkje"}), 404

            if request.method == "GET":
                ar = get_year(conn)
                rows = conn.execute(
                    """SELECT id, amount_ore, paid_at, note, created_at, for_year,
                              EXISTS(SELECT 1 FROM signup_orders WHERE payment_id=payments.id) AS vipps
                       FROM payments
                       WHERE member_id = ?
                       ORDER BY paid_at DESC, id DESC""",
                    (mid,),
                ).fetchall()
                total_all = conn.execute(
                    "SELECT COALESCE(SUM(amount_ore), 0) FROM payments WHERE member_id = ?",
                    (mid,),
                ).fetchone()[0]
                total_year = conn.execute(
                    "SELECT COALESCE(SUM(amount_ore), 0) FROM payments WHERE member_id = ? AND for_year = ?",
                    (mid, ar),
                ).fetchone()[0]
                return jsonify(
                    {
                        "payments": [dict(r) for r in rows],
                        "total_ore": int(total_year or 0),
                        "total_ore_all": int(total_all or 0),
                        "medlemsbetalingsar": ar,
                    }
                )

            data = request.get_json() or {}
            amount_nok = data.get("amount_nok")
            paid_at = (data.get("paid_at") or "").strip()
            note = (data.get("note") or "").strip() or None
            try:
                amount_ore = _nok_to_ore(amount_nok)
            except ValueError as error:
                return jsonify({"error": str(error)}), 400
            if not paid_at:
                paid_at = datetime.now(timezone.utc).isoformat()
            elif len(paid_at) == 10:
                paid_at = f"{paid_at}T12:00:00"
            created_at = datetime.now(timezone.utc).isoformat()
            ar = get_year(conn)
            cur = conn.execute(
                """INSERT INTO payments (member_id, amount_ore, paid_at, note, created_at, for_year)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (mid, amount_ore, paid_at, note, created_at, ar),
            )
            refresh_member(conn, mid)
            conn.commit()
            return jsonify(
                {
                    "id": cur.lastrowid,
                    "message": "Betaling registrert. Betalingsstatus og medlemstype er oppdaterte.",
                }
            ), 201

    @app.route("/api/members/<int:mid>/payments/<int:pid>", methods=["DELETE"])
    @require_admin
    def delete_member_payment(mid, pid):
        with managed_db(get_db) as conn:
            conn.execute("BEGIN IMMEDIATE")
            payment = conn.execute(
                "SELECT for_year FROM payments WHERE id=? AND member_id=?", (pid, mid)
            ).fetchone()
            if not payment:
                return jsonify(
                    {"error": "Betalinga finst ikkje på denne medlemmen."}
                ), 404
            if (
                conn.execute(
                    "SELECT 1 FROM payment_group_links WHERE payment_id=?", (pid,)
                ).fetchone()
                or conn.execute(
                    "SELECT 1 FROM payment_ledger_links WHERE payment_id=?", (pid,)
                ).fetchone()
                or conn.execute(
                    "SELECT 1 FROM ledger_journals WHERE source_kind='membership_payment' AND source_id=?",
                    (str(pid),),
                ).fetchone()
            ):
                return jsonify(
                    {
                        "error": "Betalinga er kopla til bokført rekneskap og kan ikkje slettast. Rett rekneskapen med sporbar reversering."
                    }
                ), 409
            if conn.execute(
                "SELECT 1 FROM signup_orders WHERE payment_id=?", (pid,)
            ).fetchone():
                return jsonify(
                    {
                        "error": "Vipps-betalingar må refunderast og avstemmast. Dei kan ikkje slettast som manuelle feilregistreringar."
                    }
                ), 409
            year = get_year(conn)
            if (
                payment["for_year"] != year
                or conn.execute(
                    "SELECT 1 FROM medlemsar_arkiv WHERE ar=?", (payment["for_year"],)
                ).fetchone()
            ):
                return jsonify(
                    {
                        "error": "Betalingar frå avslutta medlemsår kan ikkje slettast her."
                    }
                ), 409
            conn.execute("DELETE FROM payments WHERE id=? AND member_id=?", (pid, mid))
            refresh_member(conn, mid, reset_empty=True)
            conn.commit()
        return jsonify(
            {
                "message": "Betalingsregistreringa er sletta. Status og medlemstype er oppdaterte."
            }
        )

    @app.route("/api/innstillingar/kontingent", methods=["GET", "PUT"])
    @require_admin
    def kontingent_innstillingar():
        with managed_db(get_db) as conn:
            if request.method == "PUT":
                data = request.get_json() or {}
                try:
                    ore = _nok_to_ore(data.get("superkul_grense_nok"), allow_zero=True)
                except ValueError as error:
                    return jsonify({"error": str(error)}), 400
                current_year = get_year(conn)
                if (
                    ore != get_threshold(conn)
                    and conn.execute(
                        "SELECT 1 FROM signup_orders WHERE for_year=? AND environment='production' AND create_attempted=1 LIMIT 1",
                        (current_year,),
                    ).fetchone()
                ):
                    return jsonify(
                        {
                            "error": "Satsen er låst etter at produksjonsbetalingar er starta."
                        }
                    ), 409
                conn.execute(
                    "INSERT INTO app_settings(key,value) VALUES ('superkul_grense_ore',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(ore),),
                )
                conn.execute(
                    "UPDATE membership_periods SET superkul_ore=?,revision=revision+1 WHERE year=?",
                    (ore, get_year(conn)),
                )
                refresh_all(conn)
                conn.commit()
            return jsonify({"superkul_grense_ore": get_threshold(conn)})

    @app.route("/api/okonomi-sammendrag", methods=["GET"])
    @app.route("/api/medlemsoversikt", methods=["GET"])
    @require_admin
    def api_medlemsoversikt():
        """Samanlagd medlemstal (alder) + innbetaling/arkiv for gjeldande medlemsår."""
        idag = date.today()
        with managed_db(get_db) as conn:
            ar = get_year(conn)
            tot = conn.execute(
                "SELECT COALESCE(SUM(amount_ore), 0) FROM payments WHERE for_year = ?",
                (ar,),
            ).fetchone()[0]
            n_med = conn.execute(
                "SELECT COUNT(DISTINCT member_id) FROM payments WHERE for_year = ? AND amount_ore > 0",
                (ar,),
            ).fetchone()[0]
            ark = conn.execute(
                "SELECT ar, totalt_ore, antall_medlemer_med_betaling, oppretta FROM medlemsar_arkiv ORDER BY ar DESC"
            ).fetchall()
            fødsel_rader = conn.execute(
                "SELECT birth_date FROM members WHERE privacy_deleted=0"
            ).fetchall()
        from aldersfordeling import age_distribution

        ages = age_distribution(fødsel_rader, idag)
        al_0_25 = ages["age_0_14"] + ages["age_15_25"]
        al_26_eldre = ages["age_26_plus"]
        al_ukjent = ages["unknown"]
        return jsonify(
            {
                "medlemsbetalingsar": ar,
                "totalt_innbetalt_ore": int(tot or 0),
                "antall_medlemer_med_betaling": int(n_med or 0),
                "arkiv": [dict(r) for r in ark],
                "antall_medlemer_totalt": al_0_25 + al_26_eldre + al_ukjent,
                "alder_0_25": al_0_25,
                "alder_0_14": ages["age_0_14"],
                "alder_15_25": ages["age_15_25"],
                "alder_26_eller_eldre": al_26_eldre,
                "alder_utan_fodselsdato": al_ukjent,
            }
        )

    @app.route("/api/medlemsar/lukk", methods=["POST"])
    @require_admin
    def api_medlemsar_lukk():
        """
        Arkivert avslutta medlemsår (sum + tal), oppdaterer til neste kalenderår,
        og nullstiller betalingsstatus så nye kontingentar kan føreleggjast
        (gratis medlemskap krev eit vedtak for det nye året).
        """
        data = request.get_json() or {}
        try:
            bekreft = int(data.get("bekreft_ar"))
        except (TypeError, ValueError):
            return (
                jsonify(
                    {
                        "error": 'Send JSON med { "bekreft_ar": <år> } – same tal som står som «Gjeldande medlemsår» (år du avsluttar).'
                    }
                ),
                400,
            )
        now = datetime.now(timezone.utc).isoformat()
        with managed_db(get_db) as conn:
            ar = get_year(conn)
            if bekreft != ar:
                return (
                    jsonify(
                        {
                            "error": f"Bekreftinga ({bekreft}) samsvarer ikkje med gjeldande medlemsår ({ar})."
                        }
                    ),
                    400,
                )
            if conn.execute(
                "SELECT 1 FROM medlemsar_arkiv WHERE ar = ?", (ar,)
            ).fetchone():
                return jsonify({"error": f"År {ar} er allereie arkivert."}), 400
            tot = conn.execute(
                "SELECT COALESCE(SUM(amount_ore), 0) FROM payments WHERE for_year = ?",
                (ar,),
            ).fetchone()[0]
            n_med = conn.execute(
                "SELECT COUNT(DISTINCT member_id) FROM payments WHERE for_year = ? AND amount_ore > 0",
                (ar,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO medlemsar_arkiv (ar, totalt_ore, antall_medlemer_med_betaling, oppretta) VALUES (?, ?, ?, ?)",
                (ar, int(tot or 0), int(n_med or 0), now),
            )
            nytt = ar + 1
            upd = conn.execute(
                "UPDATE app_settings SET value = ? WHERE key = 'medlemsbetalingsar'",
                (str(nytt),),
            )
            if upd.rowcount == 0:
                conn.execute(
                    "INSERT INTO app_settings (key, value) VALUES ('medlemsbetalingsar', ?)",
                    (str(nytt),),
                )
            conn.execute(
                """UPDATE members SET payment_status=CASE WHEN EXISTS
                (SELECT 1 FROM paid_membership_years p WHERE p.member_id=members.id AND p.for_year=?)
                THEN 'betalt' WHEN EXISTS
                (SELECT 1 FROM free_membership_years f WHERE f.member_id=members.id AND f.for_year=?)
                THEN 'gratis' ELSE 'ikkje betalt' END WHERE privacy_deleted=0""",
                (nytt, nytt),
            )
            refresh_all(conn)
            conn.commit()
        return jsonify(
            {
                "message": f"Medlemsår {ar} er arkivert. Gjeldande medlemsår er no {nytt}. "
                f"Betalingsstatus er oppdatert etter betalingar og gratisvedtak for det nye året.",
                "forrige_ar": ar,
                "nytt_ar": nytt,
            }
        )

    @app.route("/api/export/excel")
    @require_admin
    def export_excel():
        """Last ned medlemslista som CSV (Excel-kompatibel)."""
        with managed_db(get_db) as conn:
            rows = conn.execute(
                """SELECT fornamn, mellomnamn, etternamn, email, phone, adresse, postnummer, poststad,
                          birth_date, membership_type, payment_status, consent_at
                   FROM members WHERE privacy_deleted=0 ORDER BY full_name"""
            ).fetchall()
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=";")
        writer.writerow(
            [
                "Fornamn",
                "Mellomnamn",
                "Etternamn",
                "Epost",
                "Telefon",
                "Adresse",
                "Postnummer",
                "Poststad",
                "Fødselsdato",
                "Medlemstype",
                "Betalingsstatus",
                "Samtykke",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    _csv_cell(value)
                    for value in [
                        r["fornamn"] or "",
                        r["mellomnamn"] or "",
                        r["etternamn"] or "",
                        r["email"] or "",
                        r["phone"] or "",
                        r["adresse"] or "",
                        r["postnummer"] or "",
                        r["poststad"] or "",
                        r["birth_date"] or "",
                        _medlemstype_visning(r["membership_type"] or "vanleg"),
                        r["payment_status"] or "",
                        r["consent_at"] or "",
                    ]
                ]
            )
        # UTF-8 med BOM slik at Excel opnar teiknsettet riktig
        body = "\ufeff" + buf.getvalue()
        return Response(
            body,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=medlemsliste.csv"},
        )

    @app.route("/api/gdpr/export/<int:mid>")
    @require_admin
    def gdpr_export(mid):
        with managed_db(get_db) as conn:
            row = conn.execute(
                "SELECT * FROM members WHERE id = ? AND privacy_deleted=0", (mid,)
            ).fetchone()
        if not row:
            return jsonify({"error": "Medlem finst ikkje"}), 404
        return jsonify(dict(row))

    @app.route("/api/gdpr/delete/<int:mid>", methods=["POST"])
    @require_admin
    def gdpr_delete(mid):
        with managed_db(get_db) as conn:
            conn.execute("BEGIN IMMEDIATE")
            result, status = erase_member(conn, mid)
        return jsonify(result), status
