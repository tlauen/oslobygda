"""Felles beløpsvalidering og medlemskategori, utan database eller nettverk."""

from decimal import Decimal, InvalidOperation
import re

ORE_PER_KRONE = 100
MANUAL_MIN_ORE = 1
MANUAL_MAX_ORE = 100_000_000_000  # Eksisterande administrativ grense: 1 milliard kr.
VIPPS_MIN_ORE = 100
VIPPS_MAX_ORE = 100_000_000  # Eksisterande grense i vår Vipps-flyt: 1 million kr.
VIPPS_MAX_NOK = VIPPS_MAX_ORE // ORE_PER_KRONE


def _parse_nok(value, *, minimum_ore, maximum_ore):
    """Konverter utan float-rekning eller avrunding av delar av eit øre."""
    number = Decimal(str(value).strip().replace(",", "."))
    if (
        not number.is_finite()
        or number < Decimal(minimum_ore) / ORE_PER_KRONE
        or number > Decimal(maximum_ore) / ORE_PER_KRONE
    ):
        raise ValueError("Beløpet er utanfor grensene.")
    # Samanlikn originalverdien før multiplikasjon: Decimal-konteksten kan elles
    # runde bort svært små restar i lange inputstrengar.
    if number != number.quantize(Decimal("0.01")):
        raise ValueError("Beløpet må vere heile øre.")
    return int(number * ORE_PER_KRONE)


def manual_amount_ore(value, *, allow_zero=False):
    """Manuell medlemsbetaling (eller null for innstilling av kategorigrense)."""
    try:
        return _parse_nok(
            value,
            minimum_ore=0 if allow_zero else MANUAL_MIN_ORE,
            maximum_ore=MANUAL_MAX_ORE,
        )
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        raise ValueError(
            "Beløpet må vere eit gyldig kronebeløp med høgst to desimalar."
        ) from None


def vipps_amount_ore(text):
    """Offentleg betalingsskjema: berre vanleg desimaltekst, ikkje eksponentar."""
    if not isinstance(text, str) or not re.fullmatch(
        r"\d{1,7}([.,]\d{1,2})?", text.strip()
    ):
        raise ValueError("Skriv beløpet med høgst to desimalar.")
    try:
        return _parse_nok(text, minimum_ore=VIPPS_MIN_ORE, maximum_ore=VIPPS_MAX_ORE)
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        raise ValueError("Beløpet må vere mellom 1 og 1 000 000 kroner.") from None


def valid_vipps_ore(value):
    """API-kall krev eit heiltalsbeløp; bool er ikkje eit beløp."""
    return type(value) is int and VIPPS_MIN_ORE <= value <= VIPPS_MAX_ORE


def member_kind(total_ore, threshold_ore, current_kind="vanleg"):
    """Styret er manuelt valt; kul krev strengt meir enn gjeldande årssats."""
    if current_kind.strip().lower() == "styret":
        return current_kind
    return "kul" if total_ore > threshold_ore else "vanleg"
