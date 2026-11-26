"""Små felles reglar for å unngå versjonar utan innhaldsendring."""

from arsdokument import canonical


def material(value):
    return canonical(
        {
            k: v
            for k, v in value.items()
            if k
            not in (
                "version_id",
                "snapshot_number",
                "source_revision",
                "generated_at",
                "as_of",
            )
        }
    )


def without_check_time(value):
    if isinstance(value, dict):
        return {
            k: without_check_time(v)
            for k, v in value.items()
            if k not in ("checked_at", "captured_at")
        }
    if isinstance(value, list):
        return [without_check_time(v) for v in value]
    return value
