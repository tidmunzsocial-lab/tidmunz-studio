"""No-credit concurrency regression: Auto must use two distinct Slots and preserve each clip."""
import json
import threading
from pathlib import Path

from test_video_auto_scene_provider import N, load


def test_two_cloud_jobs_overlap_without_shot_mixup(tmp_path):
    scenes = []
    for i in range(3):
        photo = tmp_path / f"image_{i}.png"
        photo.write_bytes(b"test still")
        scenes.append({"image": str(photo), "seen": "reviewed",
                       "video_prompt": f"motion-{i}"})
    project = {"scenes": scenes, "done": {}, "duration": 30}
    state = {"project": project, "folder": str(tmp_path),
             "lock": threading.RLock(), "stop": False}
    calls, accepted = [], threading.Event()
    queue_lock = threading.Lock()
    scope = dict(vars(N), state=state, runtime={"slot_busy": [False, False],
                                               "slot_cfg_vars": [{}, {}]},
                 slot_index=1, ensure_story_in_history=lambda: None,
                 ensure_continuity=lambda: None, ensure_bodies=lambda: None,
                 apply_selected_video_model=lambda project: None,
                 operator_visual_review_valid=lambda scene: True,
                 review_clip_prompt=lambda *args: None,
                 review_clip=lambda *args: None,
                 stage_motion=lambda *args, **kwargs: None,
                 clip_label=lambda scene: "Grok test",
                 with_video_audio=lambda prompt, scene: prompt,
                 set_progress=lambda *args: None,
                 ui=lambda fn, *args: fn(*args),
                 refresh_table=lambda: None, follow_shot=lambda *args: None,
                 update_preview=lambda: None,
                 log=lambda *args: None,
                 finalize_auto_video_postprocesses=lambda: None,
                 check_stop=lambda: None)
    load(scope, "project_path")
    load(scope, "save_project")

    def submit(work, index, *, prepared, on_submitted, slot_override):
        assert prepared is True
        assert work is not scenes[index]
        with queue_lock:
            calls.append((index, slot_override))
            if len(calls) == 2:
                accepted.set()
        on_submitted()
        if index < 2:
            assert accepted.wait(3), "The first paid job did not overlap the second"
        clip = tmp_path / f"slot_{slot_override}_shot_{index}.mp4"
        clip.write_bytes(f"shot:{index}/slot:{slot_override}".encode())
        return str(clip)

    scope["make_scene_clip"] = submit
    load(scope, "run_clips_dual")(project, scenes, [0, 1, 2])
    assert calls == [(0, 1), (1, 0), (2, 1)]
    assert len({sc["clip"] for sc in scenes}) == 3
    assert Path(scenes[0]["clip"]).read_bytes() == b"shot:0/slot:1"
    assert Path(scenes[1]["clip"]).read_bytes() == b"shot:1/slot:0"
    assert Path(scenes[2]["clip"]).read_bytes() == b"shot:2/slot:1"
    saved = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    assert all(Path(s["clip"]).is_file() for s in saved["scenes"])


def test_paid_provider_receipt_precedes_second_slot_and_survives_missing_download(tmp_path):
    """No real API: a paid UUID is saved before the next generation is allowed."""
    import time
    from types import SimpleNamespace
    import pytest

    image = tmp_path / "frame.png"
    image.write_bytes(b"still")
    scene = {"image": str(image), "clip_model": N.VIDEO_GROK_LITE_MODEL,
             "clip_seconds": 10, "video_prompt": "steady camera",
             "seen": "reviewed"}
    project = {"scenes": [scene], "aspect": "16:9"}
    state = {"project": project, "folder": str(tmp_path), "lock": threading.RLock()}
    busy = [False]
    class Box:
        def delete(self, *_): pass
        def insert(self, *_): pass
    class Var:
        def set(self, *_): pass
    runtime = {
        "slot_busy": busy, "slot_cfg_vars": [{}],
        "slot_images": [Var()], "slot_prompts": [Box()],
        "_auto_video_receipt_protocol": True,
    }
    def save():
        (tmp_path / "project.json").write_text(json.dumps(project), encoding="utf-8")

    submit_event = threading.Event()
    def provider(slot):
        busy[slot] = True
        def background():
            time.sleep(0.05)
            runtime.setdefault("_auto_video_receipt_by_slot", {})[slot] = {
                "uuid": "paid-uuid-001", "scene_number": 1, "model": N.VIDEO_GROK_LITE_MODEL}
            runtime["_auto_video_accepted_callbacks_by_slot"][slot]()
            busy[slot] = False   # provider accepted, but download never completed
        threading.Thread(target=background, daemon=True).start()
        return True

    runtime["on_generate_slot"] = provider
    scope = dict(vars(N), state=state, runtime=runtime, slot_index=0,
                 video_output_dir=lambda: tmp_path,
                 run_on_ui=lambda fn: fn(),
                 set_slot_config=lambda *_: None,
                 clip_prompt=lambda scene: scene["video_prompt"],
                 with_video_audio=lambda prompt, _scene: prompt,
                 save_project=save, log=lambda *_: None,
                 wait_until_video_decodable=lambda *_: None,
                 assert_video_first_frame_not_other_scene=lambda *_: None)
    generate = load(scope, "make_clip")
    with pytest.raises(RuntimeError, match="paid-uuid-001"):
        generate(scene, 0, prepared=True, on_submitted=submit_event.set)
    assert submit_event.is_set()
    assert project["scenes"][0]["clip_uuid"] == "paid-uuid-001"
    saved = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    assert saved["scenes"][0]["clip_uuid"] == "paid-uuid-001"
    assert not saved["scenes"][0].get("clip")


def test_scheduler_single_slot_legacy_is_retained():
    # Existing one-Slot behavior stays in place for test harnesses and older installations.
    source = Path(N.__file__).read_text(encoding="utf-8")
    assert "if slots_ready:" in source
    assert "return run_clips_dual(project, scenes, todo)" in source
    assert "return run_clips_lookahead(project, scenes, todo)" in source


def test_grok_poller_returns_exact_uuid_download():
    import ast
    from types import SimpleNamespace
    from snapgen_vela_video import find_video_url

    source = Path(__file__).parents[1] / "snapgen_gui_v2.py"
    node = next(n for n in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
                if isinstance(n, ast.FunctionDef) and n.name == "_poll_vela_video")
    calls = []
    def legacy(*args):
        raise AssertionError("Grok must not use legacy poller")
    scope = dict(
        VELA_VIDEO_MODEL="vela", MUSE_VIDEO_MODEL="muse", MUSE_VIDEO_LABEL="Muse",
        GROK_LOWER_MODEL="grok-lower", GROK_LITE_MODEL="grok-1.5-lite", SEEDANCE_MODELS={},
        _original_poll_and_download=legacy, _find_vela_video_url=find_video_url,
        root=SimpleNamespace(after=lambda *args: None),
        g={"run_json": lambda *a, **k: {"generated_video": [{"video_url": "https://example.test/clip.mp4"}]},
           "api_key_var": SimpleNamespace(get=lambda: "test-key"),
           "download_video": lambda url, uid: calls.append((url, uid)) or "exact.mp4"})
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), "poller", "exec"), scope)
    for model in ("grok-lower", "grok-1.5-lite"):
        assert scope["_poll_vela_video"](1, "paid-uuid", model) == "exact.mp4"
    assert calls == [("https://example.test/clip.mp4", "paid-uuid")] * 2
