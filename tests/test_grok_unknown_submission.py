"""No paid network calls: uncertain POST survives restart and blocks duplicates."""
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
import snapgen_grok_lower as G


@pytest.mark.parametrize("kind", ["curl", "process", "malformed"])
def test_uncertain_submission_blocks_retry_after_reload(tmp_path, monkeypatch, kind):
    image = tmp_path / "scene.png"
    image.write_bytes(b"reference")
    calls = []

    def run(*args, **kwargs):
        calls.append(1)
        if kind == "process":
            raise G.subprocess.TimeoutExpired("curl", 60)
        return SimpleNamespace(stdout="", stderr="timeout" if kind == "curl" else "", returncode=28 if kind == "curl" else 0)

    monkeypatch.setattr(G.subprocess, "run", run)
    args = ("test-key", "prompt", image, "1080p", "10", "landscape", "custom")
    with pytest.raises(RuntimeError, match="ไม่ส่งซ้ำ"):
        G.request(*args, model=G.GROK_LITE_MODEL)
    importlib.reload(G)
    with pytest.raises(RuntimeError, match="ไม่ส่งสร้างซ้ำ"):
        G.request(*args, model=G.GROK_LITE_MODEL)
    assert len(calls) == 1
    journal = next((tmp_path / ".snapgen-video-submissions").glob("*.json"))
    assert "test-key" not in journal.read_text()


def test_uuid_in_timeout_response_still_recovered(tmp_path, monkeypatch):
    image = tmp_path / "scene.png"
    image.write_bytes(b"reference")
    monkeypatch.setattr(G.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stdout='data: {"uuid":"paid-job"}', stderr="timeout", returncode=28))
    assert G.request("key", "prompt", image, "1080p", "10", "landscape", "custom")["uuid"] == "paid-job"


def test_process_not_started_can_retry(tmp_path, monkeypatch):
    image = tmp_path / "scene.png"
    image.write_bytes(b"reference")

    def missing(*a, **k):
        raise FileNotFoundError("curl")

    monkeypatch.setattr(G.subprocess, "run", missing)
    for _ in range(2):
        with pytest.raises(FileNotFoundError):
            G.request("key", "prompt", image, "1080p", "10", "landscape", "custom")
