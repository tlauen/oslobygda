"""Kontroller eigne Proton-arkiv før tidsrotasjon; papirkorga krev manuell sletting."""

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import fcntl
import json
from pathlib import Path
import re
import tempfile

from backup_rotasjon import candidates, created_time
from kryptert_backup import verified_archive
from okonomi_backup import verify_bundle_restore
from proton_backup import ProtonBackupError, Rclone, checksum, private_file, write_state


OWN_FILE = re.compile(
    r"(?:okonomi-\d{8}T\d{12}Z-[0-9a-f]{32}|"
    r"Oslobygda - tryggleikskopi - \d{4}-\d{2}-\d{2} kl "
    r"\d{2}\.\d{2}\.\d{2} - [0-9a-f]{8})\.bygdebackup"
)


def inspect_archive(path, password, now):
    with verified_archive(path, password) as restored:
        verify_bundle_restore(restored)
        manifest = json.loads((restored / "manifest.json").read_text())
        return created_time(manifest["created_at"], now)


def notify(report, sender=None):
    from epost import send_message

    message = EmailMessage()
    message["From"] = "Oslobygda kulturlag <folk@oslobygda.no>"
    message["To"] = "folk@oslobygda.no"
    message["Subject"] = "Backuprotasjon: manuell kontroll i Proton Drive"
    message.set_content(
        "Backuprotasjonen krev manuell kontroll.\n"
        "Berre filene nedanfor er flytta til Proton-papirkorga av rotasjonen.\n"
        "Slett desse permanent i Proton Drive. Ikkje tøm heile papirkorga.\n"
        "Etter kontroll: køyr proton_backup.py med --acknowledge-trash.\n\n"
        + "\n".join(report["trash_pending"])
        + "\n\nAvvik: "
        + "; ".join(report["warnings"])
    )
    (sender or send_message)(message)


def notify_failure(settings):
    """One attempt per UTC day; do not leak exception details or account secrets."""
    exports = Path(settings["export_directory"])
    path = exports / "rotation-alert.json"
    today = datetime.now(timezone.utc).date().isoformat()
    state = json.loads(private_file(path).read_text()) if path.exists() else {}
    if state.get("attempted_day") == today:
        return
    write_state(path, {"attempted_day": today})
    notify(
        {
            "trash_pending": [],
            "warnings": [
                "Backup eller rotasjon feila. Kontroller oppgåveloggen og rotation.json. "
                "Eventuelle ventande filnamn i rotation.json må kontrollerast i Proton-papirkorga."
            ],
        }
    )


def rotate(
    settings, apply=False, client=None, sender=None, acknowledge=False, now=None
):
    """Preview er berre lesing. Apply krev ein fersk, stadfesta offsite-backup.

    Alle fjerntilkopla arkiv blir lasta ned, dekrypterte og prøvde før sletting
    startar. Ingen dato frå eit filnamn eller rclone-mtime gir sletteløyve.
    """
    now = now or datetime.now(timezone.utc)
    exports = Path(settings["export_directory"])
    if exports.is_symlink() or not exports.is_dir():
        raise ProtonBackupError("Eksportmappa manglar eller er ei lenkje.")
    lock = exports / ".lock"
    if lock.is_symlink():
        raise ProtonBackupError("Ugyldig låsefil.")
    with lock.open("a") as handle:
        lock.chmod(0o600)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ProtonBackupError("Ei anna backupkøyring pågår.") from None
        history_path = exports / "rotation.json"
        history = (
            json.loads(private_file(history_path).read_text())
            if history_path.exists()
            else {}
        )
        if acknowledge:
            # Explicit human acknowledgement, not an API assertion about permanent deletion.
            history["trash_pending"] = []
            history["trash_acknowledged_at"] = now.isoformat()
            write_state(history_path, history)
            return {"status": "acknowledged"}
        if apply and history.get("completed_day") == now.date().isoformat():
            return {"status": "already_rotated"}
        state = json.loads(private_file(exports / "status.json").read_text())
        verified = created_time(state["verified_at"], now)
        if now - verified > timedelta(hours=36):
            raise ProtonBackupError(
                "Ingen fersk offsite-verifisering; rotasjonen er stoppa."
            )
        remote = settings["remote"].rstrip("/")
        identity = state["identity"]
        if identity["account"] != settings["account"] or not identity[
            "remote_file"
        ].startswith(remote + "/"):
            raise ProtonBackupError("Backupstatus gjeld ikkje dette målet.")
        password = private_file(settings["key_file"]).read_text().rstrip("\r\n")
        client = client or Rclone(
            settings["rclone_binary"], settings["rclone_config"], password
        )
        client.check_account(remote.split(":", 1)[0], settings["account"])
        entries = client.list_files(remote)
        remote_records, local_records, receipts = [], [], {}
        local_hashes = {}
        unknown = 0
        with tempfile.TemporaryDirectory(prefix=".rotation-", dir=exports) as temp:
            downloaded = Path(temp) / "archive.bygdebackup"
            seen = set()
            for entry in entries:
                name = entry["Path"]
                if entry.get("IsDir") or not OWN_FILE.fullmatch(name):
                    unknown += 1
                    continue
                if name in seen:
                    raise ProtonBackupError(
                        "Duplisert Proton-filnamn; rotasjonen er stoppa."
                    )
                seen.add(name)
                destination = remote + "/" + name
                client.download(destination, downloaded)
                if downloaded.is_symlink() or not downloaded.is_file():
                    raise ProtonBackupError("Nedlastinga er ikkje ei vanleg fil.")
                downloaded.chmod(0o600)
                digest = checksum(downloaded)
                stamp = inspect_archive(downloaded, password, now)
                if (
                    destination == identity["remote_file"]
                    and digest != state["artifact_sha256"]
                ):
                    raise ProtonBackupError(
                        "Den ferske Proton-kopien har endra innhald."
                    )
                remote_records.append((name, stamp))
                receipts[name] = {
                    "created_at": stamp.isoformat(),
                    "sha256": digest,
                    "verified_at": now.isoformat(),
                    "size": downloaded.stat().st_size,
                }
                downloaded.unlink()
            current_name = identity["remote_file"][len(remote) + 1 :]
            if current_name not in receipts:
                raise ProtonBackupError(
                    "Den ferske verifiserte kopien manglar i Proton-mappa."
                )
            if now - created_time(
                receipts[current_name]["created_at"], now
            ) > timedelta(hours=36):
                raise ProtonBackupError("Kjeldeinnhaldet er for gammalt til rotasjon.")
            for path in exports.glob("*.bygdebackup"):
                if path.is_symlink() or not OWN_FILE.fullmatch(path.name):
                    unknown += 1
                    continue
                stamp = inspect_archive(path, password, now)
                if checksum(path) not in {item["sha256"] for item in receipts.values()}:
                    unknown += 1
                    continue  # Preserve exports without a verified remote counterpart.
                local_hashes[path.name] = checksum(path)
                local_records.append((path.name, stamp))
            remote_delete = candidates(remote_records, now)
            local_delete = candidates(local_records, now)
            warnings = []
            for label, records, deleted in [
                ("Proton", remote_records, remote_delete),
                ("Lokal eksport", local_records, local_delete),
            ]:
                if any(
                    now - stamp >= timedelta(days=90) and name not in deleted
                    for name, stamp in records
                ):
                    warnings.append(
                        label + ": tryggingssperra bevarer kopi eldre enn 90 dagar"
                    )
            # Local recovery sets are rotated by the nightly writer. Report exceptions
            # and older standalone/code archives rather than guessing their age or purpose.
            for bundle in Path(settings["backup_directory"]).iterdir():
                if bundle.name.startswith("."):
                    continue
                if (
                    bundle.is_dir()
                    and not bundle.is_symlink()
                    and re.fullmatch(r"okonomi-\d{8}T\d{12}Z-[0-9a-f]{32}", bundle.name)
                ):
                    from okonomi_backup import verify_bundle

                    manifest = verify_bundle(bundle)
                    stamp = created_time(manifest["created_at"], now)
                    if now - stamp >= timedelta(days=90):
                        warnings.append(
                            "Lokalt backupsett eldre enn 90 dagar krev kontroll: "
                            + bundle.name
                        )
                else:
                    unknown += 1
            if unknown:
                warnings.append(f"{unknown} ukjende filer/mapper vart ikkje rørt")
            report = dict(
                status="preview",
                remote_delete=remote_delete,
                local_delete=local_delete,
                warnings=warnings,
                trash_pending=history.get("trash_pending", []),
            )
            report["remote_details"] = [
                dict(name=name, **receipts[name]) for name in remote_delete
            ]
            report["local_details"] = [
                dict(
                    name=name,
                    created_at=dict(local_records)[name].isoformat(),
                    size=(exports / name).stat().st_size,
                )
                for name in local_delete
            ]
            if not apply:
                return report
            history["receipts"] = receipts
            write_state(history_path, history)
            for name in remote_delete:
                # Recheck the exact object immediately before moving it to trash.
                client.download(remote + "/" + name, downloaded)
                if checksum(downloaded) != receipts[name]["sha256"]:
                    raise ProtonBackupError(
                        "Proton-fila endra seg før sletting; rotasjonen er stoppa."
                    )
                downloaded.unlink()
                # Persist intent first so interruption cannot hide a required trash check.
                pending = history.setdefault("trash_pending", [])
                if name not in pending:
                    pending.append(name)
                write_state(history_path, history)
                client.trash_file(remote + "/" + name)
            for name in local_delete:
                path = exports / name
                if path.is_symlink():
                    raise ProtonBackupError("Eksportfil vart endra under rotasjon.")
                # Validate again so a replaced file is never deleted using stale metadata.
                if (
                    checksum(path) != local_hashes[name]
                    or inspect_archive(path, password, now) != dict(local_records)[name]
                ):
                    raise ProtonBackupError("Eksportfil vart endra under rotasjon.")
                path.unlink()
            report["trash_pending"] = history.get("trash_pending", [])
            report["status"] = "rotated"
            if report["trash_pending"] or warnings:
                notify(report, sender)
            history["completed_day"] = now.date().isoformat()
            history["last_report"] = report
            write_state(history_path, history)
            return report
