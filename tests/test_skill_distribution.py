"""Skill distribution: Git source, in-app patch, and standalone ZIP stay in sync."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = Path(".agents/skills/tidmunz-remote-operator")
FILES = (
    SKILL_DIR / "SKILL.md",
    SKILL_DIR / "references/operations.md",
    SKILL_DIR / "references/distribution.md",
)


def test_install_and_patch_include_skill():
    for path in FILES:
        assert (ROOT / path).is_file(), path
    # In a real release, the workflow writes the version file before building.
    # Exercise the same builder in an isolated mini-repo without touching user data.
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp)
        (staged / "tools").mkdir()
        (staged / "snapgen_data/meta").mkdir(parents=True)
        shutil.copy2(ROOT / "tools/build_update_patch.py", staged / "tools/build_update_patch.py")
        shutil.copytree(ROOT / SKILL_DIR, staged / SKILL_DIR)
        (staged / "snapgen_data/meta/snapgen_version.json").write_text('{"version":"9.8.7"}')
        result = subprocess.run(
            [sys.executable, "-B", str(staged / "tools/build_update_patch.py")],
            cwd=staged, check=True, capture_output=True, text=True, timeout=45,
        )
        assert "version=9.8.7" in result.stdout
        with zipfile.ZipFile(staged / "tools/release/tidmun-studio-patch.zip") as archive:
            assert archive.testzip() is None
            manifest = json.loads(archive.read("manifest.json"))
            entries = {entry["path"]: entry for entry in manifest["files"]}
            for path in FILES:
                name = path.as_posix()
                assert name in archive.namelist() and name in entries
                contents = (ROOT / path).read_bytes()
                assert archive.read(name) == contents
                assert entries[name]["sha256"] == hashlib.sha256(contents).hexdigest()


def test_portable_zip_has_only_credential_free_skill_documents():
    with tempfile.TemporaryDirectory() as tmp:
        # Execute canonical builder without writing a release archive to the repo.
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "tidmunz_skill_packager", ROOT / "tools/build_operator_skill.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = module.build_skill_archive(Path(tmp) / "skill.zip")
        with zipfile.ZipFile(output) as archive:
            names = archive.namelist()
            assert archive.testzip() is None
            assert "tidmunz-remote-operator/SKILL.md" in names
            assert "tidmunz-remote-operator/references/operations.md" in names
            assert "tidmunz-remote-operator/references/distribution.md" in names
            assert all(name.endswith(".md") for name in names)
            for name in names:
                contents = archive.read(name).decode("utf-8")
                assert "access=mw" not in contents
                assert "C:\\Users\\Apinan" not in contents


def test_first_install_launcher_copies_skill(monkeypatch, tmp_path):
    import importlib.util
    import io
    spec = importlib.util.spec_from_file_location(
        "tidmunz_skills_launcher", ROOT / "tools/launcher/tidmunz_launcher.py"
    )
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    archive_buf = io.BytesIO()
    with zipfile.ZipFile(archive_buf, "w") as archive:
        archive.writestr("repo/setup_and_run.bat", "@echo off\r\n")
        for skill_path in FILES:
            archive.writestr("repo/" + skill_path.as_posix(), (ROOT / skill_path).read_bytes())

    class Response(io.BytesIO):
        headers = {}

    monkeypatch.setattr(
        launcher, "latest_release",
        lambda: {"owner": "test", "repository": "repo", "tag": "v9.8.7", "version": "9.8.7"},
    )
    monkeypatch.setattr(launcher, "_request", lambda *args, **kwargs: Response(archive_buf.getvalue()))
    launcher.install_program(tmp_path)
    for path in FILES:
        assert (tmp_path / path).read_bytes() == (ROOT / path).read_bytes()
