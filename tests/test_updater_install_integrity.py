"""The updater must verify installed code, not trust a copied version label."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
import snapgen_updater as updater


class UpdaterInstallIntegrityTests(unittest.TestCase):
    def test_completed_receipt_wins_over_misleading_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = root / "snapgen_data" / "meta" / "snapgen_version.json"
            metadata.parent.mkdir(parents=True)
            metadata.write_text(json.dumps({"version": "1.0.192"}), encoding="utf-8")
            receipt = root / "snapgen_update_last.json"
            receipt.write_text(json.dumps({"version": "1.0.188"}), encoding="utf-8")
            self.assertEqual("1.0.188", updater.current_version(root))
            self.assertFalse(updater.verify_installed_files(root)[0])

    def _stage(self, base, content=b"new executable"):
        root = base / "installed"
        root.mkdir()
        (root / "app.py").write_bytes(b"old executable")
        (root / "snapgen_update_last.json").write_text(
            json.dumps({"version": "1.0.188"}), encoding="utf-8")
        stage = base / "staging"
        file = stage / "files" / "app.py"
        file.parent.mkdir(parents=True)
        file.write_bytes(content)
        item = {"path": "app.py", "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content)}
        (stage / "apply.json").write_text(
            json.dumps({"version": "1.0.193", "files": [item]}), encoding="utf-8")
        return root, stage

    def test_successful_apply_commits_verifiable_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, stage = self._stage(Path(temporary))
            with patch.object(updater, "_pid_running", return_value=False), \
                    patch.object(updater, "_start_after_update"):
                updater._apply(stage, root, 12345)
            self.assertEqual("1.0.193", updater.current_version(root))
            self.assertEqual(b"new executable", (root / "app.py").read_bytes())
            self.assertEqual((True, ""), updater.verify_installed_files(root))
            (root / "app.py").write_bytes(b"wrong")
            self.assertFalse(updater.verify_installed_files(root)[0])

    def test_corrupted_apply_rolls_back_without_false_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, stage = self._stage(Path(temporary))
            replace = updater.os.replace

            def damage_after_replace(src, dst):
                replace(src, dst)
                if Path(dst) == root / "app.py":
                    Path(dst).write_bytes(b"corrupt after write")

            with patch.object(updater, "_pid_running", return_value=False), \
                    patch.object(updater, "_start_after_update"), \
                    patch.object(updater.os, "replace", side_effect=damage_after_replace):
                with self.assertRaises(updater.UpdateError):
                    updater._apply(stage, root, 12345)
            self.assertEqual(b"old executable", (root / "app.py").read_bytes())
            self.assertEqual("1.0.188", updater.current_version(root))

    def test_latest_release_offers_repair_if_installed_files_are_damaged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, stage = self._stage(Path(temporary))
            with patch.object(updater, "_pid_running", return_value=False), \
                    patch.object(updater, "_start_after_update"):
                updater._apply(stage, root, 12345)
            release = {
                "tag_name": "v1.0.193",
                "assets": [{"name": updater.ASSET_NAME,
                            "browser_download_url": "https://example.test/patch.zip"}],
            }
            with patch.object(updater, "_fetch_from_repositories",
                              return_value=([release], [])):
                self.assertFalse(updater.check_latest(root)["available"])
                (root / "app.py").write_bytes(b"damage")
                update = updater.check_latest(root)
                self.assertTrue(update["available"])
                self.assertTrue(update["repair"])


if __name__ == "__main__":
    unittest.main()
