"""Windows bootstrap regressions: real cmd.exe in scratch homes, no downloads/install."""
import ast
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("launcher", ROOT / "tools/launcher/tidmunz_launcher.py")
L = importlib.util.module_from_spec(spec); spec.loader.exec_module(L)
BATCH = (ROOT / "setup_and_run.bat").read_text(encoding="utf-8")


def cmd_section(home, section, env=None):
    home.mkdir(parents=True, exist_ok=True)
    script = home / "probe.bat"
    script.write_text("@echo off\nsetlocal EnableExtensions EnableDelayedExpansion\n" + section,
                      encoding="utf-8", newline="\r\n")
    return subprocess.run(["cmd.exe", "/d", "/c", "call", str(script)], cwd=home,
                          env=dict(os.environ, **(env or {})), stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, errors="replace", timeout=30)


@pytest.mark.skipif(os.name != "nt", reason="Windows batch parser")
def test_system_python312_discovery_handles_space_in_username(tmp_path):
    home = tmp_path / "Tui Tidmunz" / "Local" / "Tidmunz Studio"
    local = tmp_path / "Tui Tidmunz" / "Local"
    python = local / "Programs/Python/Python312/python.exe"
    python.parent.mkdir(parents=True); python.write_bytes(b"not executed")
    section = BATCH[BATCH.index("REM No working venv"):BATCH.index("REM Try py launcher")]
    result = cmd_section(home, 'set "PYEXE="\n' + section + '\necho FOUND=!PYEXE!\n',
                         {"LOCALAPPDATA": str(local)})
    assert result.returncode == 0 and f"FOUND={python}" in result.stdout, result.stdout + result.stderr


@pytest.mark.skipif(os.name != "nt", reason="Windows batch parser")
def test_uv_and_temp_paths_with_spaces_use_real_offline_discovery(tmp_path):
    uv = shutil.which("uv")
    if not uv: pytest.skip("uv unavailable")
    found = subprocess.run([uv, "python", "find", "3.12", "--offline"], capture_output=True, text=True)
    if found.returncode: pytest.skip("No local Python 3.12; never download in this check")
    actual = Path(found.stdout.strip())
    space = tmp_path / "Tui Tidmunz" / "bin"
    space.mkdir(parents=True)
    local_uv = space / "uv.exe"
    try: os.link(uv, local_uv)
    except OSError: shutil.copy2(uv, local_uv)
    temp = tmp_path / "Tui Tidmunz" / "Temp"; temp.mkdir()
    section = BATCH[BATCH.index("REM Try uv-managed"):BATCH.index("REM No Python - try winget")]
    result = cmd_section(tmp_path / "Tui Tidmunz/Studio", 'set "PYEXE="\nset "UVEXE="\n' + section +
                         '\necho FOUND=!PYEXE!\n',
                         {"TEMP": str(temp), "TMP": str(temp), "UV_OFFLINE": "1",
                          "UV_PYTHON_INSTALL_DIR": str(actual.parent.parent),
                          "PATH": str(space) + os.pathsep + os.environ["PATH"]})
    assert result.returncode == 0 and f"FOUND={actual}" in result.stdout, result.stdout + result.stderr


@pytest.mark.skipif(os.name != "nt", reason="Windows batch parser")
@pytest.mark.parametrize("existing", [False, True])
def test_fresh_config_is_created_without_copying_or_overwriting_credentials(tmp_path, existing):
    home = tmp_path / "Tui Tidmunz" / "Studio"
    config = home / "snapgen_data/snapgen_config.json"
    if existing:
        config.parent.mkdir(parents=True); config.write_text('{"keep":"user-data"}', encoding="utf-8")
    start = BATCH.index('if not exist "snapgen_data\\snapgen_config.json"')
    section = BATCH[start:BATCH.index('if not exist "snapgen_data\\prompt_bank.txt"', start)]
    result = cmd_section(home, section)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(config.read_text()) == ({"keep": "user-data"} if existing else {})


@pytest.mark.skipif(os.name != "nt", reason="Windows batch parser")
def test_real_hidden_run_setup_handles_spaced_install_home(tmp_path):
    home = tmp_path / "Tui Tidmunz" / "Tidmunz Studio"
    python = home / ".venv312/Scripts/python.exe"
    python.parent.mkdir(parents=True); python.write_bytes(b"test-only")
    (home / "setup_and_run.bat").write_text("@echo off\necho [1/7] Checking Python\necho [7/7] Ready\nexit /b 0\n",
                                            encoding="ascii", newline="\r\n")
    progress = []
    L.run_setup(home, lambda text, fraction: progress.append((text, fraction)))
    assert progress[-1] == ("[7/7] Ready", 1)


@pytest.mark.parametrize("ready", [0, 1, "timeout"])
def test_incomplete_venv_is_not_treated_as_working_install(tmp_path, monkeypatch, ready):
    folder = tmp_path / ".venv312/Scripts"; folder.mkdir(parents=True)
    for name in ("python.exe", "pythonw.exe"): (folder / name).write_bytes(b"test-only")
    calls = []
    def probe(command, **kwargs):
        assert command[0] == str(folder / "python.exe")
        assert "(3, 12)" in command[-1] and "qcloud_cos" in command[-1]
        if ready == "timeout": raise subprocess.TimeoutExpired(command, 30)
        return SimpleNamespace(returncode=ready)
    monkeypatch.setattr(L.subprocess, "run", probe)
    monkeypatch.setattr(L.subprocess, "Popen", lambda *a, **k: calls.append((a, k)))
    assert L.start_app(tmp_path) == (ready == 0)
    assert len(calls) == (1 if ready == 0 else 0)


def test_retry_after_partial_first_install_refreshes_stale_setup_before_running(tmp_path):
    (tmp_path / L.MAIN_SCRIPT).write_text("old main")
    events = []
    tree = ast.parse(Path(L.__file__).read_text(encoding="utf-8"))
    parent = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_setup_with_window")
    worker = next(n for n in ast.walk(parent) if isinstance(n, ast.FunctionDef) and n.name == "worker")
    def install(home, progress): events.append("download"); (home / "setup_and_run.bat").write_text("fresh setup")
    def setup(home, progress):
        assert (home / "setup_and_run.bat").read_text() == "fresh setup"
        events.append("setup")
    scope = dict(vars(L), home=tmp_path, result={}, report=lambda *a: None,
                 install_program=install, run_setup=setup,
                 root=SimpleNamespace(after=lambda delay, fn: fn(), destroy=lambda: events.append("done")))
    exec(compile(ast.Module(body=[worker], type_ignores=[]), L.__file__, "exec"), scope)
    scope["worker"]()
    assert events == ["download", "setup", "done"] and not scope["result"]


def test_download_preserves_data_and_normalizes_all_batch_lines(tmp_path, monkeypatch):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("repo/setup_and_run.bat", b"@echo off\r\necho ok\nexit /b 0\n")
        z.writestr("repo/snapgen_data/snapgen_config.json", b"never copy")
        z.writestr("repo/export/keep.png", b"never replace")
    config = tmp_path / "snapgen_data/snapgen_config.json"; config.parent.mkdir()
    config.write_bytes(b"existing settings")
    export = tmp_path / "export/keep.png"; export.parent.mkdir(); export.write_bytes(b"existing image")
    monkeypatch.setattr(L, "latest_release", lambda: dict(owner="owner", repository="repo", tag="v1.0.126", version="1.0.126"))
    class Response(io.BytesIO): headers = {}
    monkeypatch.setattr(L, "_request", lambda *a, **k: Response(buffer.getvalue()))
    L.install_program(tmp_path)
    assert config.read_bytes() == b"existing settings" and export.read_bytes() == b"existing image"
    data = (tmp_path / "setup_and_run.bat").read_bytes()
    assert data.count(b"\r\n") == data.count(b"\n") == 3


def test_source_batch_has_only_crlf_and_quotes_all_temp_file_loops():
    data = (ROOT / "setup_and_run.bat").read_bytes()
    assert data.count(b"\r\n") == data.count(b"\n")
    for line in BATCH.splitlines():
        if "for /f" in line and "%TEMP%" in line:
            assert '"usebackq delims="' in line and 'in ("%TEMP%\\' in line
        if "!UVEXE! python" in line: pytest.fail("Unquoted uv path")
