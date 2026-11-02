"""No paid requests: exercise production timeout recovery and explicit plan fallback."""
import base64
import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from test_video_auto_scene_provider import N, batch_scope, load
import snapgen_chrome_api as C


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
    assert json.loads(receipt.read_text()) == {"submitted": True}
    assert "test-key" not in receipt.read_text()
    with pytest.raises(RuntimeError, match="ยังไม่ส่ง API ซ้ำ"):
        run()
    with pytest.raises(RuntimeError):
        run(confirm_resubmit=lambda name: False)
    assert calls == ["POST"]
    monkeypatch.setattr(N.urllib.request, "urlopen", lambda request, **kwargs:
        (calls.append(request.get_method()) or io.BytesIO(json.dumps({
            "uuid": "recovered-job", "status": 2, "used_credit": 1,
            "generated_image": [{"image_url": IMAGE}]}).encode())))
    assert Path(run(confirm_resubmit=lambda name: name == "scene_001")).read_bytes() == b"generated-image"
    assert calls == ["POST", "POST"] and not receipt.exists()


def test_known_task_survives_poll_failure_and_resume_uses_only_get(tmp_path, monkeypatch):
    calls, records = [], []
    monkeypatch.setattr(N.time, "sleep", lambda seconds: None)
    def reply(request, **kwargs):
        calls.append(request.get_method())
        if request.get_method() == "POST":
            return io.BytesIO(b'{"uuid":"existing-job","status":1}')
        raise HTTPError(request.full_url, 524, "timeout", {}, io.BytesIO(b"timeout"))
    monkeypatch.setattr(N.urllib.request, "urlopen", reply)
    def run():
        return N.snapgen_image("scene", [], str(tmp_path), "scene_001", "16:9", "key", on_credit=records.append)
    with pytest.raises(RuntimeError, match="existing-job"):
        run()
    assert calls == ["POST", "GET", "GET", "GET"]
    assert json.loads(next(tmp_path.glob(".*.json")).read_text())["uuid"] == "existing-job"
    monkeypatch.setattr(N.urllib.request, "urlopen", lambda request, **kwargs:
        (calls.append(request.get_method()) or io.BytesIO(json.dumps({
            "uuid": "existing-job", "status": 2, "used_credit": 15,
            "generated_image": [{"image_url": IMAGE}]}).encode())))
    assert Path(run()).read_bytes() == b"generated-image"
    assert calls[-1] == "GET" and calls.count("POST") == 1
    assert records == [{"task_id": "existing-job", "used_credit": 15.0}]


def test_known_async_task_recovers_without_another_post(tmp_path, monkeypatch):
    calls = []
    def reply(request, **kwargs):
        calls.append(request.get_method())
        payload = ({"uuid": "stream-job", "status": 1} if request.get_method() == "POST" else
                   {"uuid": "stream-job", "status": 2, "used_credit": 1,
                    "generated_image": [{"image_url": IMAGE}]})
        return io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(N.urllib.request, "urlopen", reply)
    result = N.snapgen_image("scene", [], str(tmp_path), "scene", "9:16", "key")
    assert Path(result).read_bytes() == b"generated-image" and calls == ["POST", "GET"]


def test_502_is_ambiguous_and_never_resubmits_without_confirmation(tmp_path, monkeypatch):
    requests = []
    def reply(request, **kwargs):
        requests.append(request)
        if len(requests) == 1:
            raise HTTPError(request.full_url, 502, "Bad Gateway", {}, io.BytesIO(b"<html>Cloudflare</html>"))
        return io.BytesIO(json.dumps({
            "uuid": "retry-job", "status": 2, "used_credit": 1,
            "generated_image": [{"image_url": IMAGE}],
        }).encode())
    monkeypatch.setattr(N.urllib.request, "urlopen", reply)

    with pytest.raises(RuntimeError, match="HTTP 502"):
        N.snapgen_image("scene", [], str(tmp_path), "scene_001", "9:16", "key")
    with pytest.raises(RuntimeError, match="ยังไม่ส่ง API ซ้ำ"):
        N.snapgen_image("scene", [], str(tmp_path), "scene_001", "9:16", "key")
    result = N.snapgen_image("scene", [], str(tmp_path), "scene_001", "9:16", "key",
                             confirm_resubmit=lambda _name: True)

    assert Path(result).read_bytes() == b"generated-image"
    assert [request.get_method() for request in requests] == ["POST", "POST"]
    assert requests[0].get_header("Idempotency-key") is None
    assert not list(tmp_path.glob(".*_snapgen_lower_*.json"))


def test_503_requires_confirmation_before_any_resubmit(tmp_path, monkeypatch):
    post_requests = []
    def unavailable(request, **kwargs):
        post_requests.append(request)
        raise HTTPError(request.full_url, 503, "Service Unavailable", {}, io.BytesIO(b"<html>Cloudflare</html>"))
    monkeypatch.setattr(N.urllib.request, "urlopen", unavailable)

    with pytest.raises(RuntimeError, match="HTTP 503"):
        N.snapgen_image("scene", [], str(tmp_path), "scene_001", "9:16", "key")
    receipt = next(tmp_path.glob(".*_snapgen_lower_*.json"))
    assert json.loads(receipt.read_text()) == {"submitted": True}
    assert len(post_requests) == 1
    with pytest.raises(RuntimeError, match="ยังไม่ส่ง API ซ้ำ"):
        N.snapgen_image("scene", [], str(tmp_path), "scene_001", "9:16", "key")

    def recovered(request, **kwargs):
        post_requests.append(request)
        return io.BytesIO(json.dumps({
            "uuid": "resumed-job", "status": 2, "used_credit": 1,
            "generated_image": [{"image_url": IMAGE}],
        }).encode())
    monkeypatch.setattr(N.urllib.request, "urlopen", recovered)
    result = N.snapgen_image("scene", [], str(tmp_path), "scene_001", "9:16", "key",
                             confirm_resubmit=lambda _name: True)

    assert Path(result).read_bytes() == b"generated-image"
    assert [request.get_method() for request in post_requests] == ["POST", "POST"]
    assert not receipt.exists()


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
    scope = dict(vars(N), state={"project": {"scenes": scenes, "duration": 60}, "lock": N.threading.RLock()}, video_mode=True,
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


def test_chrome_conversation_429_remains_rate_limited():
    status, payload = C.error_reply({
        "error": "ChatGPT conversation read failed: HTTP 429 — message not sent",
        "provider_status": 429,
        "send_state": "not_sent", "retry_after": 75,
    })
    assert status == 429
    assert payload["error"]["code"] == "rate_limited"
    assert payload["error"]["provider_status"] == 429
    assert payload["error"]["send_state"] == "not_sent"
    assert payload["error"]["retry_after"] == 75


def test_auto_recovers_pre_send_429_with_backoff_and_same_request():
    calls, waits, notices = [], [], []
    error = N.bridge_rate_limit(429, json.dumps({"error": {
        "message": "blocked before send", "send_state": "not_sent", "retry_after": 75}}))

    def send():
        calls.append("same-request")
        if len(calls) < 3:
            raise error
        return "answer"

    assert N.run_bridge_with_cooldown(send, lambda: None, waits.append,
                                     lambda delay, attempt: notices.append((delay, attempt))) == "answer"
    assert calls == ["same-request"] * 3
    assert notices == [(75, 1), (75, 2)] and sum(waits) == 150


def test_auto_cooldown_stop_never_resubmits():
    calls, waits = [], []
    error = N.bridge_rate_limit(429, json.dumps({"error": {"send_state": "not_sent"}}))

    def check_stop():
        if waits:
            raise N.Stopped()

    def send():
        calls.append(1)
        raise error

    with pytest.raises(N.Stopped):
        N.run_bridge_with_cooldown(send, check_stop, waits.append, lambda *_: None)
    assert calls == [1] and waits == [1]


@pytest.mark.parametrize("send_state", ["sent", "unknown"])
def test_auto_never_replays_an_accepted_or_unknown_request(send_state):
    error = N.bridge_rate_limit(429, json.dumps({"error": {"send_state": send_state}}))
    calls = []

    def send():
        calls.append(1)
        raise error

    with pytest.raises(N.RateLimited):
        N.run_bridge_with_cooldown(send, lambda: None, lambda _: pytest.fail("must not wait/replay"), lambda *_: None)
    assert calls == [1]


def test_narrate_chat_429_is_non_image_rate_limit_and_not_retried(monkeypatch):
    calls = []

    def blocked(request, **kwargs):
        calls.append(request.get_method())
        payload = json.dumps({"error": {"code": "rate_limited", "message": "HTTP 429"}}).encode()
        raise HTTPError(request.full_url, 429, "Too Many Requests", {}, io.BytesIO(payload))

    monkeypatch.setattr(N.urllib.request, "urlopen", blocked)
    scope = dict(vars(N), state={"project": {"conversation": {}}},
                 g={"_chatgpt_api_base": lambda: "http://bridge.test"},
                 queued_bridge=lambda send: send(), check_stop=lambda: None, log=lambda *_: None)
    chat = load(scope, "chat", parent="_build")
    with_retries = load(scope, "with_retries", parent="_build")
    with pytest.raises(N.RateLimited, match="HTTP 429") as caught:
        with_retries("พรอมต์วิดีโอ", lambda: chat("video prompt"))
    assert caught.value.image_generation is False
    assert calls == ["POST"]


def test_motion_rate_limit_does_not_fallback_to_text_only(tmp_path):
    scope, scenes, questions, calls = motion_scope(tmp_path)
    before = json.loads(json.dumps(scenes))

    def blocked(content):
        calls.append(content)
        limited = N.RateLimited("ChatGPT rate limit (HTTP 429)")
        limited.image_generation = False
        raise limited

    scope["chat"] = blocked
    with pytest.raises(N.RateLimited, match="HTTP 429"):
        scope["stage_motion"]()
    assert len(calls) == 1
    assert not questions and not scope["state"].get("motion_text_only")
    assert scenes == before


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
    assert all(scene["video_prompt"].startswith("new motion\n") and N.VIDEO_AUDIO_RULE in scene["video_prompt"]
               and scene["seen"] == "real frame"
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
