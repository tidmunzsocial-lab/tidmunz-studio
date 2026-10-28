"""No paid requests: exercise production timeout recovery and explicit plan fallback."""
import base64
import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from test_video_auto_scene_provider import N, batch_scope, load


IMAGE = "data:image/png;base64," + base64.b64encode(b"generated-image").decode()


def test_524_survives_restart_and_never_silently_resubmits(tmp_path, monkeypatch):
    calls = []
    def timeout(request, **kwargs):
        calls.append(request.get_method())
        raise HTTPError(request.full_url, 524, "timeout", {}, io.BytesIO(b"cloudflare"))
    monkeypatch.setattr(N.urllib.request, "urlopen", timeout)
    def run(**kwargs):
        return N.snapgen_image("scene", [], str(tmp_path), "scene_001", "9:16", "test-key", **kwargs)
    with pytest.raises(RuntimeError, match="HTTP 524"):
        run()
    receipt = next(tmp_path.glob(".*.json"))
    assert json.loads(receipt.read_text()) == {"task_id": None}
    assert "test-key" not in receipt.read_text()
    with pytest.raises(RuntimeError, match="ยังไม่ส่ง API ซ้ำ"):
        run()
    with pytest.raises(RuntimeError):
        run(confirm_resubmit=lambda name: False)
    assert calls == ["POST"]
    monkeypatch.setattr(N.urllib.request, "urlopen", lambda request, **kwargs:
        (calls.append(request.get_method()) or io.BytesIO(json.dumps({
            "id": "recovered-job", "status": "succeeded", "charged_microusd": "8500",
            "result": {"urls": [IMAGE]}}).encode())))
    assert Path(run(confirm_resubmit=lambda name: name == "scene_001")).read_bytes() == b"generated-image"
    assert calls == ["POST", "POST"] and not receipt.exists()


def test_known_task_survives_poll_failure_and_resume_uses_only_get(tmp_path, monkeypatch):
    calls, records = [], []
    monkeypatch.setattr(N.time, "sleep", lambda seconds: None)
    def reply(request, **kwargs):
        calls.append(request.get_method())
        if request.get_method() == "POST":
            return io.BytesIO(b'{"id":"existing-job","status":"queued"}')
        raise HTTPError(request.full_url, 524, "timeout", {}, io.BytesIO(b"timeout"))
    monkeypatch.setattr(N.urllib.request, "urlopen", reply)
    def run():
        return N.snapgen_image("scene", [], str(tmp_path), "scene_001", "16:9", "key", on_credit=records.append)
    with pytest.raises(RuntimeError, match="existing-job"):
        run()
    assert calls == ["POST", "GET", "GET", "GET"]
    assert json.loads(next(tmp_path.glob(".*.json")).read_text())["task_id"] == "existing-job"
    monkeypatch.setattr(N.urllib.request, "urlopen", lambda request, **kwargs:
        (calls.append(request.get_method()) or io.BytesIO(json.dumps({
            "id": "existing-job", "status": "succeeded", "charged_microusd": "150000",
            "result": {"urls": [IMAGE]}}).encode())))
    assert Path(run()).read_bytes() == b"generated-image"
    assert calls[-1] == "GET" and calls.count("POST") == 1
    assert records == [{"task_id": "existing-job", "used_credit": 15}]


def test_known_async_task_recovers_without_another_post(tmp_path, monkeypatch):
    calls = []
    def reply(request, **kwargs):
        calls.append(request.get_method())
        payload = ({"id": "stream-job", "status": "queued"} if request.get_method() == "POST" else
                   {"id": "stream-job", "status": "succeeded", "charged_microusd": "8500",
                    "result": {"urls": [IMAGE]}})
        return io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(N.urllib.request, "urlopen", reply)
    result = N.snapgen_image("scene", [], str(tmp_path), "scene", "9:16", "key")
    assert Path(result).read_bytes() == b"generated-image" and calls == ["POST", "GET"]


def test_old_version_524_requires_history_confirmation_before_post(tmp_path):
    scope, _ = batch_scope(tmp_path, 1)
    scope["state"]["project"]["scenes"][0]["error"] = "SnapGen API: HTTP 524 timeout"
    asked, submitted = [], []
    scope["ask_on_ui"] = lambda *args: asked.append(args) or False
    scope["snapgen_image"] = lambda *args, **kwargs: submitted.append(args)
    generate = load(scope, "generate_via_snapgen")
    with pytest.raises(N.Stopped):
        generate("scene", [], tmp_path, "scene_001", "9:16", {"api_key": "key"})
    with pytest.raises(N.Stopped):
        generate("scene", [], tmp_path, "scene_001", "9:16", {"api_key": "key"})
    assert len(asked) == 1 and not submitted


def motion_scope(tmp_path, accept=True):
    image = tmp_path / "first.png"; image.write_bytes(b"first-frame")
    scenes = [{"image": str(image), "video_prompt": f"planned-{i}"} for i in range(3)]
    questions, calls, logs = [], [], []
    noop = lambda *args, **kwargs: None
    scope = dict(vars(N), state={"project": {"scenes": scenes, "duration": 60}}, video_mode=True,
                 file_digest=lambda path: "digest", check_stop=noop, ensure_story_in_history=noop,
                 ensure_continuity=noop, ensure_bodies=noop, assign_clips=noop, economy_on=lambda: False,
                 apply_selected_video_model=noop, set_progress=noop, motion_request=lambda *a: "request",
                 motion_items=lambda batch: batch, image_data_url=lambda path: "image",
                 save_project=noop, ui=lambda fn: fn(), refresh_table=noop, log=logs.append,
                 ask_on_ui=lambda *a: questions.append(a) or accept)
    def chat(content):
        calls.append(content)
        raise RuntimeError("Bridge HTTP 400: No assistant text came back")
    scope["chat"] = chat
    scope["with_retries"] = lambda label, fn: fn()
    load(scope, "use_planned_motion")
    load(scope, "stage_motion")
    load(scope, "review_clip_prompt")
    return scope, scenes, questions, calls


def test_motion_fallback_requires_consent_and_keeps_plan_and_images(tmp_path):
    scope, scenes, questions, calls = motion_scope(tmp_path)
    before = json.loads(json.dumps(scenes))
    scope["stage_motion"]()
    assert scenes == before and len(questions) == 1 and len(calls) == 2
    assert scope["state"]["motion_planned_only"]
    scope["stage_motion"]([1], force=True)
    scope["review_clip_prompt"](scenes[1], 1)
    assert len(questions) == 1 and len(calls) == 2
    assert not any("seen" in scene or "motion_image" in scene or "prompt_review" in scene for scene in scenes)
    scope["state"].pop("motion_planned_only")
    scope["state"].pop("motion_text_only")
    scope["stage_motion"]()
    assert len(questions) == 2  # A new round does not reuse old consent.


def test_refusing_motion_fallback_stops_without_modifying_plan(tmp_path):
    scope, scenes, questions, calls = motion_scope(tmp_path, accept=False)
    with pytest.raises(N.Stopped): scope["stage_motion"]()
    assert not scope["state"].get("motion_planned_only")
    assert [scene["video_prompt"] for scene in scenes] == ["planned-0", "planned-1", "planned-2"]


@pytest.mark.parametrize("error", ["safety policy refusal", "Bridge HTTP 401", "invalid JSON", "image rate limit"])
def test_unrelated_errors_never_offer_motion_bypass(tmp_path, error):
    scope, scenes, questions, calls = motion_scope(tmp_path)
    assert not scope["use_planned_motion"]([0, 1], RuntimeError(error))
    assert not questions


def test_missing_video_prompt_never_falls_back_to_image_prompt(tmp_path):
    scope, scenes, questions, calls = motion_scope(tmp_path)
    scenes[2].pop("video_prompt"); scenes[2]["prompt"] = "image description only"
    with pytest.raises(RuntimeError, match="No assistant text"):
        scope["stage_motion"]()
    assert not questions and not scope["state"].get("motion_planned_only")


def test_working_web_still_writes_and_checks_real_frames(tmp_path):
    scope, scenes, questions, calls = motion_scope(tmp_path)
    scope["chat"] = lambda content: json.dumps({"shots": [
        {"video_prompt": "new motion", "seen": "real frame"}]})
    scope["stage_motion"]()
    assert not questions and not scope["state"].get("motion_planned_only")
    assert all(scene["video_prompt"] == "new motion" and scene["seen"] == "real frame"
               and scene["motion_image"] == "digest" for scene in scenes)


def test_force_relook_failure_also_needs_current_run_consent(tmp_path):
    scope, scenes, questions, calls = motion_scope(tmp_path)
    scope["stage_motion"]([0], force=True)
    assert len(questions) == 1 and len(calls) == 1
    assert scenes[0]["video_prompt"] == "planned-0" and "motion_image" not in scenes[0]


def test_explicit_rejection_is_not_stored_as_ambiguous_timeout(tmp_path, monkeypatch):
    calls = []
    def reject(request, **kwargs):
        calls.append(request.get_method())
        raise HTTPError(request.full_url, 403, "forbidden", {}, io.BytesIO(b"blocked"))
    monkeypatch.setattr(N.urllib.request, "urlopen", reject)
    with pytest.raises(RuntimeError, match="403"):
        N.snapgen_image("scene", [], str(tmp_path), "scene", "9:16", "key")
    assert calls == ["POST"] and not list(tmp_path.glob(".*.json"))
