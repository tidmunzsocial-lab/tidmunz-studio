"""Run production worker/provider functions without opening the user's app or paid APIs."""
import ast
import base64
import io
import json
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
import snapgen_page_narrate as N

TREE = ast.parse(Path(N.__file__).read_text(encoding="utf-8-sig"))


def load(scope, name, parent=None):
    tree = TREE if parent is None else next(n for n in ast.walk(TREE)
                                           if isinstance(n, ast.FunctionDef) and n.name == parent)
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), N.__file__, "exec"), scope)
    return scope[name]


def test_storyboard_provider_menu_offers_snapgen_api():
    assert N.VIDEO_AUTO_IMAGE_PROVIDER_LABELS == {
        "gpt_web": N.GPT_WEB_LABEL,
        "snapgen": "SnapGen API · GPT Image 2.5 · 1K",
    }
    assert N.VIDEO_AUTO_IMAGE_PROVIDER_MENU_LABELS == N.VIDEO_AUTO_IMAGE_PROVIDER_LABELS
    assert N.normalize_video_auto_storyboard_provider("gpt_web") == "gpt_web"
    assert N.normalize_video_auto_storyboard_provider("retired-provider") == "snapgen"


class Widget:
    def __init__(self, *args, **kwargs):
        self.value = None
    def set(self, value): self.value = value
    def get(self): return self.value
    def pack(self, **kwargs): pass
    def config(self, **kwargs): pass
    def configure(self, **kwargs): pass


def chooser_scope(tmp_path, answers):
    dialogs, logs = [], []
    class Window(Widget):
        def __init__(self, *args):
            self.buttons = {}
            dialogs.append(self)
        def title(self, *args): pass
        def transient(self, *args): pass
        def resizable(self, *args): pass
        def bind(self, name, callback): self.closed = callback
        def destroy(self): self.closed(SimpleNamespace(widget=self))
        def grab_set(self):
            answer = answers.pop(0)
            if answer is None:
                self.destroy()
            else:
                self.buttons[N.VIDEO_AUTO_SCENE_PROVIDER_LABELS[answer]]()
    class Button(Widget):
        def __init__(self, win, text, command, **kwargs): win.buttons[text] = command
    state = {"project": {"done": {}, "storyboard_provider": "snapgen",
                         "scenes": [{"image": "keep-existing.png"}]}, "busy": True}
    scope = dict(vars(N), state=state, video_mode=True, page=None,
                 refresh_snapgen_credit_warning=lambda: None,
                 tk=SimpleNamespace(Toplevel=Window, Label=Widget, Button=Button),
                 root=SimpleNamespace(after=lambda delay, fn: fn()), log=logs.append)
    scope["save_project"] = lambda: (tmp_path / "project.json").write_text(
        json.dumps(state["project"]), encoding="utf-8")
    load(scope, "image_provider_for")
    load(scope, "confirm_snapgen_credit_warning")
    return scope, dialogs, logs


def test_stop_resume_and_restart_ask_once_per_run_and_keep_storyboard(tmp_path):
    scope, dialogs, logs = chooser_scope(tmp_path, ["snapgen", "gpt_web"])
    seen = []
    def images():
        seen.extend(scope["image_provider_for"]("images") for _ in range(8))
        raise N.Stopped()
    scope.update(project=scope["state"]["project"], only=None, character_limit=None,
                 stages=[("images", "รูปฉาก", 1)], STAGE_FUNCS={"images": images},
                 confirm_credits=lambda **kw: True, refresh_stages=lambda *a: None,
                 refresh_all=lambda: None, ui=lambda fn, *a: fn(*a), g={},
                 stage_var=Widget(), detail_var=Widget(), bar=Widget(), start_btn=Widget())
    worker = load(scope, "worker", "start_pipeline")
    scope["state"]["snapgen_credit_acceptance"] = {"ceiling": 999}
    for key in ("motion_planned_only", "motion_text_only", "snapgen_resubmit_confirmed"):
        scope["state"][key] = True
    assert scope["image_provider_for"]("storyboard") == "snapgen"
    worker()
    assert "snapgen_credit_acceptance" not in scope["state"]
    assert not any(key in scope["state"] for key in (
        "motion_planned_only", "motion_text_only", "snapgen_resubmit_confirmed"))
    assert seen == ["snapgen"] * 8 and len(dialogs) == 1
    restored = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    assert restored["image_stage_providers"]["images"] == "snapgen"
    scope["project"] = scope["state"]["project"] = restored
    worker()
    assert seen == ["snapgen"] * 8 + ["gpt_web"] * 8 and len(dialogs) == 2
    assert restored["scenes"][0]["image"] == "keep-existing.png"
    assert scope["image_provider_for"]("storyboard") == "snapgen"
    assert not any(message.startswith("❌") for message in logs)


def test_cancel_submits_nothing_and_narrate_keeps_its_provider(tmp_path):
    scope, dialogs, logs = chooser_scope(tmp_path, [None])
    with pytest.raises(N.Stopped): scope["image_provider_for"]("images")
    assert "images" not in scope["state"]["project"]["image_stage_providers"]
    scope["video_mode"] = False
    scope["state"]["project"]["image_provider"] = "snapgen"
    assert scope["image_provider_for"]("images") == "snapgen"
    assert len(dialogs) == 1


def batch_scope(tmp_path, count=12):
    paths = []
    for name in ("actor.png", "location.png", "panel.png"):
        path = tmp_path / name; path.write_bytes(b"reference"); paths.append(str(path))
    scenes = [{"prompt": f"shot-{i}", "board": paths[2]} for i in range(count)]
    project = {"scenes": scenes, "aspect": "9:16"}
    state = {"project": project, "folder": str(tmp_path), "lock": threading.RLock()}
    noop = lambda *args, **kwargs: None
    scope = dict(vars(N), state=state, video_mode=True, runtime={},
                 g={"snapgen_image_api_key_var": SimpleNamespace(get=lambda: "test-key")},
                 attachments_for=lambda scene, limit=None: paths[:2],
                 scene_prompt=lambda scene: scene["prompt"], check_stop=noop,
                 save_project=lambda: (tmp_path / "project.json").write_text(json.dumps(project)),
                 looks_like_reference_sheet=lambda image: False, set_progress=noop, log=noop,
                 ui=lambda fn, *args: fn(*args), refresh_table=noop, follow_shot=noop,
                 image_provider_for=lambda stage: "snapgen", verify_images=noop,
                 refresh_snapgen_credit_warning=noop)
    for name in ("check_script_matches_audio", "ensure_story_in_history", "ensure_continuity",
                 "ensure_bodies", "research_ghosts"):
        scope[name] = noop
    scope["character_refs"] = lambda: pytest.fail("Video Auto must use its own matched attachments")
    load(scope, "run_snapgen_scenes")
    load(scope, "stage_images")
    return scope, paths


def test_video_auto_uses_five_api_workers_and_only_unfinished_scenes(tmp_path):
    scope, paths = batch_scope(tmp_path)
    scenes = scope["state"]["project"]["scenes"]
    for i in range(2):
        old = tmp_path / f"existing-{i}.png"; old.write_bytes(b"existing"); scenes[i]["image"] = str(old)
    calls, active, peak = [], 0, 0
    lock, first_five = threading.Lock(), threading.Event()
    def make_image(prompt, refs, folder, name, aspect, board=None, api_context=None):
        nonlocal active, peak
        with lock:
            active += 1; peak = max(peak, active); calls.append(name)
            if len(calls) >= 5: first_five.set()
        assert first_five.wait(5)
        assert refs == paths[:2] and board == paths[2] and aspect == "9:16"
        assert api_context == {"api_key": "test-key"}
        target = folder / (name + ".png"); target.write_bytes(b"generated")
        with lock: active -= 1
        return str(target)
    scope["make_image"] = make_image
    scope["stage_images"]()
    assert peak == 5
    assert sorted(calls) == [f"scene_{i + 1:03d}" for i in range(2, 12)]
    assert all(Path(scene["image"]).is_file() for scene in scenes)
    assert (tmp_path / "existing-0.png").read_bytes() == b"existing"
    saved = json.loads((tmp_path / "project.json").read_text())
    assert all(scene.get("image") for scene in saved["scenes"])


@pytest.mark.parametrize("provider", ["snapgen", "gpt-web"])
def test_selected_redraw_uses_original_prompt_and_scene_guides_without_old_frame(tmp_path, provider):
    scope, paths = batch_scope(tmp_path, 1)
    scope["image_provider_for"] = lambda _stage: provider
    scene = scope["state"]["project"]["scenes"][0]
    old = tmp_path / "old-frame.png"; old.write_bytes(b"old-frame")
    scene.update(image=str(old), characters=["ทหาร"], prompt="rewritten prompt",
                 prompt_before_visual_redraw="original shot prompt")
    generated = []

    def make_image(prompt, refs, folder, name, aspect, board=None, api_context=None, **kwargs):
        generated.append((prompt, refs, board, api_context, kwargs))
        target = folder / (name + ".png"); target.write_bytes(b"new-frame")
        return str(target)

    scope.update(with_retries=lambda _name, call: call(),
                 gpt_look=lambda *_args, **_kwargs: pytest.fail("selected redraw must not analyze the old frame"),
                 make_image=make_image,
                 credit_consent_required=lambda *_args: False)
    scope["stage_images"]([0], selected_redraw=True)

    assert len(generated) == 1
    prompt, refs, board, api_context, options = generated[0]
    assert prompt == "original shot prompt"
    assert refs == paths[:2] and board is None
    assert options["fresh_chat"] is True
    assert api_context == ({"api_key": "test-key"} if provider == "snapgen" else None)
    assert scene["prompt"] == "original shot prompt"
    assert "prompt_before_visual_redraw" not in scene
    assert old.read_bytes() == b"old-frame"


def test_api_reference_overflow_fails_before_any_submission(tmp_path):
    scope, paths = batch_scope(tmp_path, 1)
    scope["attachments_for"] = lambda scene, limit=None: paths[:1] * 10
    scope["make_image"] = lambda *args, **kw: pytest.fail("must validate before a paid request")
    with pytest.raises(N.ImageProviderError, match="10 รูป"):
        scope["stage_images"]()


def test_video_auto_sends_snapgen_1k_request_with_panel_first(tmp_path, monkeypatch):
    scope, paths = batch_scope(tmp_path, 1)
    # Image requests use their own live key; the legacy video credential must not win.
    scope["runtime"]["snapgen_image_api_key_var"] = SimpleNamespace(get=lambda: "stale-invalid-key")
    scope["runtime"]["api_key_var"] = SimpleNamespace(get=lambda: "legacy-video-key")
    scope["IMAGES_PER_CHAT"] = 12
    load(scope, "generate_via_snapgen")
    load(scope, "make_image")
    buffer = io.BytesIO()
    Image.new("RGB", (48, 64), "blue").save(buffer, "PNG")
    generated = buffer.getvalue()
    for path in paths:
        Path(path).write_bytes(generated)
    requests = []
    def reply(request, **kwargs):
        requests.append(request)
        payload = ({"id": "job-1", "status": "queued"} if request.get_method() == "POST" else
                   {"id": "job-1", "status": "succeeded", "charged_microusd": "8500",
                    "result": {"urls": ["data:image/png;base64," +
                                           base64.b64encode(generated).decode("ascii")]}})
        return io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(N.urllib.request, "urlopen", reply)
    scope["stage_images"]()
    assert [request.get_method() for request in requests] == ["POST", "GET"]
    request = requests[0]
    assert request.full_url == N.SNAPGEN_IMAGE_URL
    assert request.get_header("Authorization") == "Bearer test-key"
    assert request.get_header("Prefer") == "respond-async"
    fields = json.loads(request.data)
    assert fields["model"] == "gpt-image-2.5-ext" and fields["resolution"] == "1K"
    assert fields["size"] == "9:16" and "shot-0" in fields["prompt"]
    assert "STORYBOARD PANEL" in fields["prompt"]
    assert [base64.b64decode(ref.split(",", 1)[1]) for ref in fields["image_urls"]] == [generated] * 3
    assert Path(scope["state"]["project"]["scenes"][0]["image"]).read_bytes() == generated


def test_video_auto_requires_image_gateway_key_before_request(tmp_path):
    scope, _paths = batch_scope(tmp_path, 1)
    scope["g"]["snapgen_image_api_key_var"] = SimpleNamespace(get=lambda: "")
    scope["runtime"]["api_key_var"] = SimpleNamespace(get=lambda: "valid-legacy-video-key")
    scope["snapgen_image"] = lambda *args, **kwargs: pytest.fail("must stop before API request")
    with pytest.raises(N.ImageProviderError, match="SnapGen.org Image API key"):
        scope["stage_images"]()


def test_stop_drains_five_submitted_jobs_and_saves_all_results():
    started, release, stop = threading.Event(), threading.Event(), threading.Event()
    calls, saved, errors = [], [], []
    lock = threading.Lock()
    def work(index):
        with lock:
            calls.append(index)
            if len(calls) == 5: started.set()
        assert release.wait(5)
        return index
    def check():
        if stop.is_set(): raise N.Stopped()
    def run():
        try:
            N._run_image_jobs(range(12), work, lambda i, result, err: saved.append(result), check)
        except N.Stopped: errors.append("stopped")
    worker = threading.Thread(target=run); worker.start()
    try:
        assert started.wait(5)
        stop.set(); release.set(); worker.join(5)
        assert not worker.is_alive()
        assert sorted(calls) == sorted(saved) == list(range(5))
        assert errors == ["stopped"]
    finally:
        release.set(); worker.join(5)
