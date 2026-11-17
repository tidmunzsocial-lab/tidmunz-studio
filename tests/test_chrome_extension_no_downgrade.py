"""The desktop startup must not revert a hotfixed Chrome extension."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
import snapgen_chrome_relay as relay


def _mock_manifest(path, version, script):
    path.mkdir(parents=True, exist_ok=True)
    (path / "manifest.json").write_text(json.dumps({"version": version}), encoding="utf8")
    (path / "followup.js").write_text(script, encoding="utf8")


def test_startup_preserves_newer_installed_extension(monkeypatch, tmp_path):
    bundled = tmp_path / "bundled"
    installed = tmp_path / "extension"
    _mock_manifest(bundled, "1.0.53", "old-code")
    _mock_manifest(installed, "1.0.55", "hotfixed-code")
    monkeypatch.setattr(relay, "extension_dir", lambda: installed)
    relay._write_extension(bundled, "test-only-token", 8766)
    assert json.loads((installed / "manifest.json").read_text())["version"] == "1.0.55"
    assert (installed / "followup.js").read_text() == "hotfixed-code"
    assert "8766" in (installed / "config.js").read_text()


def test_startup_upgrades_when_bundled_extension_is_newer(monkeypatch, tmp_path):
    bundled, installed = tmp_path / "bundle", tmp_path / "extension"
    _mock_manifest(bundled, "1.0.56", "new-code")
    _mock_manifest(installed, "1.0.54", "outdated-code")
    monkeypatch.setattr(relay, "extension_dir", lambda: installed)
    relay._write_extension(bundled, "test-only-token", 8766)
    assert json.loads((installed / "manifest.json").read_text())["version"] == "1.0.56"
    assert (installed / "followup.js").read_text() == "new-code"


def test_same_version_updates_file_content(monkeypatch, tmp_path):
    bundled, installed = tmp_path / "bundle", tmp_path / "extension"
    _mock_manifest(bundled, "1.0.55", "patched")
    _mock_manifest(installed, "1.0.55", "stale")
    monkeypatch.setattr(relay, "extension_dir", lambda: installed)
    relay._write_extension(bundled, "test-only-token", 8766)
    assert (installed / "followup.js").read_text() == "patched"