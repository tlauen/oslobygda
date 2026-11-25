"""Faste lagringsverdiar for ordrestatus og betalingsstatus frå Vipps.

Verdiane er del av eksisterande database/API-format og skal ikkje omsetjast.
Ein fullført ordre er vår bokføringsstatus; AUTHORIZED er Vipps sin status,
òg etter trekk. E-postlevering har sin eigen status og er ikkje betalingsstatus.
"""

from enum import Enum


class _Status(str, Enum):
    def __str__(self):
        return self.value


class Ordrestatus(_Status):
    NEW = "new"
    COMPLETE = "complete"
    REVIEW = "review"
    REDACTED = "redacted"


class Vippsstatus(_Status):
    CREATED = "CREATED"
    AUTHORIZED = "AUTHORIZED"
    ABORTED = "ABORTED"
    EXPIRED = "EXPIRED"
    TERMINATED = "TERMINATED"

