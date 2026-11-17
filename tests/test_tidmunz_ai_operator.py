"""AI operator can inspect and classify local jobs without duplicating paid requests."""
import importlib.util
import sys
from pathlib import Path

import pytest

FILE = Path(__file__).resolve().parents[1] / "snapgen_modules" / "snapgen_ai_operator.py"
SPEC = importlib.util.spec_from_file_location("tidmunz_ai_operator", FILE)
O = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(O)


def test_summary_preserves_existing_media_and_first_missing(tmp_path, monkeypatch):
    project_dir = tmp_path / "วิดีโอออโต้"
    story = project_dir / "บท - เจ้าสาวนาคา"
    story.mkdir(parents=True)
    img = story / "shot.png"
    img.write_bytes(b"image")
    clip = story / "clip.mp4"
    clip.write_bytes(b"movie" * 1600)
    scenes = [
        {"image": str(img), "clip": str(clip)},
        {"image": str(img), "clip": "",
         "clip_error": "The server currently is experiencing high traffic"}
    ]
    import json
    (story / "project.json").write_text(
        json.dumps({"scenes": scenes, "done": {"video": False}}, ensure_ascii=False),
        encoding="utf-8")
    monkeypatch.setattr(O, "STORIES", project_dir)
    status = {"ready": True, "auto": {
        "title": story.name, "busy": False, "shots": [{"n": 1}, {"n": 2}],
        "stage": "หยุดอยู่", "detail": "", "percent": 70},
        "slots": [{"status": "Idle"}, {"status": "Idle"}]}
    state = O.summarize(status)
    assert state["images"] == 2
    assert state["clips"] == 1 and state["total"] == 2
    assert state["next_missing_shot"] == 2
    assert state["final_ready"] is False
    assert O.diagnose(state)["diagnosis"] == "provider_capacity"


def test_ambiguous_provider_is_not_retried():
    status = {"app_ready": True, "auto_busy": False, "final_ready": False,
              "next_shot_has_provider_receipt": False,
              "next_shot_error": "HTTP 504 timeout",
              "total": 115, "clips": 93}
    assert O.diagnose(status)["diagnosis"] == "ambiguous_cloud_result"
    status["next_shot_has_provider_receipt"] = True
    assert O.diagnose(status)["diagnosis"] == "provider_task_may_be_pending"


def test_paid_work_requires_explicit_approval(monkeypatch):
    monkeypatch.setattr(O, "request", lambda path, data=None:
                        {"ready": True, "auto": {"title": "", "busy": False, "shots": []},
                         "slots": [{"status": "Idle"}]})
    class Args:
        command = "resume"
        authorize_paid = False
    with pytest.raises(O.OperatorError, match="explicit user authorization"):
        O.handle(Args())


def test_running_auto_does_not_send_second_stop_command(monkeypatch):
    called = []
    monkeypatch.setattr(O, "request", lambda path, data=None:
                        {"ready": True, "auto": {"title": "", "busy": False, "shots": []}})
    monkeypatch.setattr(O, "execute", lambda action, data=None: called.append(action))
    class Args:
        command = "stop"
    assert "Already idle" in O.handle(Args())["note"]
    assert not called


def test_project_path_traversal_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "STORIES", tmp_path)
    assert O.project_for("../secrets") is None
    assert O.project_for("anything/name") is None



def _capacity_fixture(tmp_path, monkeypatch, *, credit=0, status="3"):
    import io
    import json
    import os
    import time

    stories = tmp_path / "stories"
    story = stories / "บท - ตัวอย่าง"
    story.mkdir(parents=True)
    good = story / "good.mp4"
    good.write_bytes(b"a" * 5000)
    scenes = [
        {"clip": str(good)},
        {"clip_uuid": "a" * 32, "clip_error": "High traffic. Please come back in 30 minutes."},
    ]
    file = story / "project.json"
    file.write_text(json.dumps({"scenes": scenes, "done": {"images": True}}, ensure_ascii=False), encoding="utf8")
    old = time.time() - 1900
    os.utime(file, (old, old))
    data = tmp_path / "data"
    data.mkdir()
    (data / "snapgen_config.json").write_text(json.dumps({"api_key": "an-example-local-key"}))
    monkeypatch.setattr(O, "STORIES", stories)
    monkeypatch.setattr(O, "DATA", data)
    current = {"ready": True, "auto": {"title": story.name, "busy": False, "shots": []},
               "slots": [{"status": "Video failed", "busy": False},
                         {"status": "Background upscale (finished)", "busy": False}]}
    monkeypatch.setattr(O, "request", lambda *args, **kwargs: current)
    class Response(io.BytesIO):
        def __enter__(self):return self
        def __exit__(self, *args):self.close()
    def history(_request, timeout):
        return Response(json.dumps({
            "status": status, "used_credit": credit,
            "error_message": "The server currently is experiencing high traffic."
        }).encode("utf8"))
    monkeypatch.setattr(O.urllib.request, "urlopen", history)
    actions = []
    monkeypatch.setattr(O, "execute", lambda name, data=None:
                        (actions.append(name) or {"accepted": True}))
    return file, actions


def test_capacity_recovery_uses_terminal_zero_credit_receipt_and_reload(tmp_path, monkeypatch):
    import json
    file, actions = _capacity_fixture(tmp_path, monkeypatch)
    result = O.recover_capacity_after_receipt()
    scenes = json.loads(file.read_text(encoding="utf8"))["scenes"]
    assert result["recovered_scene"] == 2
    assert actions == ["auto_open", "auto_start"]
    assert scenes[0]["clip"]
    assert not scenes[1].get("clip_uuid")
    assert scenes[1]["clip_failed_jobs"][0]["uuid"] == "a" * 32


@pytest.mark.parametrize("credit,status", [(20, "3"), (0, "1"), (0, "2")])
def test_capacity_recovery_refuses_billed_or_pending_receipt(tmp_path, monkeypatch, credit, status):
    import json
    file, actions = _capacity_fixture(tmp_path, monkeypatch, credit=credit, status=status)
    with pytest.raises(O.OperatorError, match="zero-credit terminal"):
        O.recover_capacity_after_receipt()
    assert not actions
    assert json.loads(file.read_text(encoding="utf8"))["scenes"][1]["clip_uuid"] == "a" * 32


def test_capacity_recovery_refuses_live_slot(tmp_path, monkeypatch):
    file, actions = _capacity_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(O, "request", lambda *args, **kwargs: {
        "ready": True, "auto": {"title": "บท - ตัวอย่าง", "busy": False, "shots": []},
        "slots": [{"status": "Video failed", "busy": True}]})
    with pytest.raises(O.OperatorError, match="slot is busy"):
        O.recover_capacity_after_receipt()
    assert not actions
