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
