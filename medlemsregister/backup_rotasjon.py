"""Tidsbasert backuprotasjon. Ukjende eller ukontrollerte filer blir aldri sletta."""

from datetime import datetime, timedelta, timezone


def created_time(value, now):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp > now + timedelta(minutes=5):
        raise ValueError("Ugyldig opprettingstid i backupmanifest.")
    return stamp.astimezone(timezone.utc)


def candidates(records, now=None):
    """records: (unik nøkkel, kontrollert UTC-tid). Bevar to nyaste som sikring.

    Éin nyaste kopi per UTC-dag dei siste 30 dagane, deretter per ISO-veke.
    Kopiar på eller over 90 dagar går ut, med unntak for dei to siste.
    """
    now = now or datetime.now(timezone.utc)
    records = sorted(records, key=lambda r: (r[1], str(r[0])), reverse=True)
    if len({r[0] for r in records}) != len(records):
        raise ValueError("Duplisert backupidentitet.")
    keep = {key for key, _ in records[:2]}
    buckets = set()
    for key, stamp in records:
        if stamp.tzinfo is None or stamp > now + timedelta(minutes=5):
            raise ValueError("Ugyldig backupdato.")
        age = now - stamp
        if age >= timedelta(days=90):
            continue
        if age < timedelta(days=30):
            bucket = ("day", stamp.astimezone(timezone.utc).date())
        else:
            iso = stamp.astimezone(timezone.utc).isocalendar()
            bucket = ("week", iso.year, iso.week)
        if bucket not in buckets:
            keep.add(key)
            buckets.add(bucket)
    return [key for key, _ in reversed(records) if key not in keep]


def plan_bundles(directory, now=None):
    """Read-only plan for strictly named, fully verified local recovery sets."""
    import re
    from pathlib import Path
    from okonomi_backup import verify_bundle

    now = now or datetime.now(timezone.utc)
    records = []
    for path in Path(directory).glob("okonomi-*"):
        if not re.fullmatch(r"okonomi-\d{8}T\d{12}Z-[0-9a-f]{32}", path.name):
            continue
        if path.is_symlink() or not path.is_dir():
            raise ValueError("Ugyldig lokalt backupsett; rotasjonen er stoppa.")
        manifest = verify_bundle(path)
        records.append((path, created_time(manifest["created_at"], now)))
    return candidates(records, now)
