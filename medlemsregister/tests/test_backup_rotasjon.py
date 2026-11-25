from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from backup_rotasjon import candidates
from kryptert_backup import encrypt_bundle
from proton_rotasjon import rotate
import test_proton_backup as existing
from proton_backup import perform, ProtonBackupError


class PolicyTests(unittest.TestCase):
    def test_daily_weekly_boundary_and_two_newest(self):
        now = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
        records = [(str(day), now - timedelta(days=day)) for day in range(110)]
        deleted = candidates(records, now)
        self.assertFalse(set(map(str, range(30))) & set(deleted))
        self.assertTrue(set(map(str, range(90, 110))) <= set(deleted))
        self.assertLessEqual(
            len([name for name, _ in records if name not in deleted]), 41
        )
        self.assertEqual(
            candidates(
                [
                    ("one", now - timedelta(days=100)),
                    ("two", now - timedelta(days=101)),
                ],
                now,
            ),
            [],
        )

    def test_future_and_timezone(self):
        now = datetime(2026, 11, 25, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            candidates(
                [("a", now), ("b", now), ("future", now + timedelta(days=1))], now
            )


class RotationTests(unittest.TestCase):
    setUp = existing.ProtonBackupTests.setUp
    tearDown = existing.ProtonBackupTests.tearDown

    def ready(self):
        perform(self.settings, self.client)
        self.client.list_files = lambda remote: [
            {"Path": name.split("/")[-1], "IsDir": False} for name in self.client.files
        ]
        self.client.trash_file = Mock(
            side_effect=lambda name: self.client.files.pop(name)
        )

    def old_archive(self, days, index):
        manifest = self.bundle / "manifest.json"
        original = manifest.read_bytes()
        data = json.loads(original)
        data["created_at"] = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).isoformat()
        manifest.write_text(json.dumps(data))
        path = (
            self.root
            / "exports"
            / f"okonomi-20200101T000000000000Z-{index:032x}.bygdebackup"
        )
        try:
            encrypt_bundle(
                self.bundle, path, Path(self.settings["key_file"]).read_text()
            )
        finally:
            manifest.write_bytes(original)
        self.client.files[self.settings["remote"] + "/" + path.name] = path.read_bytes()
        return path

    def test_preview_no_deletion_then_apply_and_mail(self):
        self.ready()
        self.old_archive(10, 1)
        old = self.old_archive(100, 2)
        sender = Mock()
        report = rotate(self.settings, client=self.client)
        self.assertIn(old.name, report["remote_delete"])
        self.assertTrue(old.exists())
        self.client.trash_file.assert_not_called()
        self.assertFalse((self.root / "exports/rotation.json").exists())
        report = rotate(self.settings, client=self.client, apply=True, sender=sender)
        self.assertFalse(old.exists())
        self.assertIn(old.name, report["trash_pending"])
        sender.assert_called_once()
        self.assertEqual(
            rotate(self.settings, client=self.client, apply=True)["status"],
            "already_rotated",
        )
        rotate(self.settings, client=self.client, acknowledge=True)
        self.assertEqual(
            json.loads((self.root / "exports/rotation.json").read_text())[
                "trash_pending"
            ],
            [],
        )

    def test_corrupt_remote_prevents_all_deletions(self):
        self.ready()
        self.old_archive(10, 1)
        old = self.old_archive(100, 2)
        self.client.corrupt = True
        with self.assertRaises(ValueError):
            rotate(self.settings, client=self.client, apply=True)
        self.assertTrue(old.exists())
        self.client.trash_file.assert_not_called()

    def test_missing_current_stops_and_unknown_names_are_preserved(self):
        self.ready()
        self.client.files[self.settings["remote"] + "/unrelated.bygdebackup"] = (
            b"private"
        )
        report = rotate(self.settings, client=self.client)
        self.assertTrue(report["warnings"])
        state = json.loads((self.root / "exports/status.json").read_text())
        del self.client.files[state["identity"]["remote_file"]]
        with self.assertRaises(ProtonBackupError):
            rotate(self.settings, client=self.client, apply=True)
        self.client.trash_file.assert_not_called()

    def test_export_without_verified_remote_copy_is_not_deleted(self):
        self.ready()
        self.old_archive(10, 1)
        orphan = self.old_archive(100, 2)
        del self.client.files[self.settings["remote"] + "/" + orphan.name]
        sender = Mock()
        report = rotate(self.settings, client=self.client, apply=True, sender=sender)
        self.assertTrue(orphan.exists())
        self.assertNotIn(orphan.name, report["local_delete"])
        self.assertTrue(report["warnings"])
        sender.assert_called_once()

    def test_failed_notice_preserves_pending_trash_list(self):
        self.ready()
        self.old_archive(10, 1)
        old = self.old_archive(100, 2)
        with self.assertRaises(RuntimeError):
            rotate(
                self.settings,
                client=self.client,
                apply=True,
                sender=Mock(side_effect=RuntimeError("smtp")),
            )
        history = json.loads((self.root / "exports/rotation.json").read_text())
        self.assertIn(old.name, history["trash_pending"])
        self.assertNotIn("completed_day", history)

    def test_local_bundle_policy_uses_manifest_dates(self):
        from okonomi_backup import create_bundle
        import shutil

        manifest = json.loads((self.bundle / "manifest.json").read_text())
        for days in (10, 40, 100):
            dest = self.root / "backups" / f"okonomi-20200101T000000000000Z-{days:032x}"
            shutil.copytree(self.bundle, dest)
            manifest["created_at"] = (
                datetime.now(timezone.utc) - timedelta(days=days)
            ).isoformat()
            (dest / "manifest.json").write_text(json.dumps(manifest))
        create_bundle(
            self.root / "source.db", self.root / "receipts", self.root / "backups"
        )
        self.assertFalse(
            (
                self.root / "backups" / f"okonomi-20200101T000000000000Z-{100:032x}"
            ).exists()
        )
        self.assertTrue(
            (
                self.root / "backups" / f"okonomi-20200101T000000000000Z-{40:032x}"
            ).exists()
        )
