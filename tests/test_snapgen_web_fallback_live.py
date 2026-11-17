"""Credit-safe SnapGen website extension fallback: never resubmit ambiguous paid jobs."""
import ast
import base64
import io
import json
from pathlib import Path
import sys

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "snapgen_modules"))


def _setup(monkeypatch, tmp_path):
    import snapgen_web_backend as backend

    ref = tmp_path / "ref.png"
    Image.new("RGB", (1280, 720), (80, 105, 120)).save(ref)
    return backend, [ref]


def test_extension_and_ui_provider_are_wired():
    root = ROOT / "snapgen_modules"
    manifest = json.loads((root / "chrome_ext" / "manifest.json").read_text("utf-8"))
    assert manifest["version"] == "1.0.56"
    assert "https://snapgen.ai/*" in manifest["host_permissions"]
    assert "https://accounts.google.com/*" in manifest["host_permissions"]
    background = (root / "chrome_ext" / "background.js").read_text("utf-8")
    assert 'importScripts("snapgen_web.js")' in background
    assert 'job.type === "snapgen_web_image"' in background
    assert 'job.type === "snapgen_web_inspect"' in background
    module = (root / "snapgen_page_narrate.py").read_text("utf-8")
    ast.parse(module)
    assert '"snapgen_web": SNAPGEN_WEB_LABEL' in module
    assert 'snapgen_web_backend.generate(prompt, refs, out_dir, name, aspect)' in module
    assert 'fallback_provider = "snapgen_web"' in module


def test_accepted_unknown_web_job_never_sent_twice(monkeypatch, tmp_path):
    backend, refs = _setup(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(backend.snapgen_chrome_relay.RELAY, "run", lambda job:
                        (calls.append(job), {"error": "output not ready", "send_state": "sent"})[1])
    with pytest.raises(RuntimeError):
        backend.generate("Thai live action scene", refs, tmp_path, "shot097", "16:9")
    with pytest.raises(RuntimeError, match="ตรวจ History"):
        backend.generate("Thai live action scene", refs, tmp_path, "shot097", "16:9")
    assert len(calls) == 1


def test_not_sent_failure_keeps_safe_retry_available(monkeypatch, tmp_path):
    backend, refs = _setup(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(backend.snapgen_chrome_relay.RELAY, "run", lambda job:
                        (calls.append(job), {"error": "login required", "send_state": "not_sent"})[1])
    with pytest.raises(RuntimeError):
        backend.generate("Thai cinema", refs, tmp_path, "shot102", "16:9")
    with pytest.raises(RuntimeError):
        backend.generate("Thai cinema", refs, tmp_path, "shot102", "16:9")
    assert len(calls) == 2


def test_success_receipt_reuses_existing_image_without_resend(monkeypatch, tmp_path):
    backend, refs = _setup(monkeypatch, tmp_path)
    im = Image.new("RGB", (1280, 720), (115, 115, 130))
    stream = io.BytesIO()
    im.save(stream, "PNG")
    calls = []
    monkeypatch.setattr(backend.snapgen_chrome_relay.RELAY, "run", lambda job:
                        (calls.append(job), {"images": ["data:image/png;base64," +
                        base64.b64encode(stream.getvalue()).decode()], "web_price": 2})[1])
    a = backend.generate("Temple scene", refs, tmp_path, "shot085", "16:9")
    b = backend.generate("Temple scene", refs, tmp_path, "shot085", "16:9")
    assert a == b and Path(a).is_file()
    assert len(calls) == 1
