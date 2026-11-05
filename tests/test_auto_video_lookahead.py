"""Run the real scheduler with controlled cloud acceptance and local upscale futures."""
from concurrent.futures import Future
import hashlib
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from test_video_auto_scene_provider import N, load, Widget


def pipeline_scope(tmp_path, monkeypatch, prompt_error=None):
    scenes = []
    for i in range(3):
        image = tmp_path / f"image{i}.png"
        image.write_bytes(b"preserved image")
        scenes.append({"image": str(image), "seen": "actual frame", "video_prompt": "planned"})
    project = {"scenes": scenes, "done": {}, "duration": 18}
    state = {"project": project, "folder": str(tmp_path), "lock": threading.RLock(),
             "stop": False, "auto_video_postprocess_pending": []}
    events, futures, prepared, errors = [], {}, set(), []
    ready = threading.Event()
    scope = dict(vars(N), state=state, runtime={}, slot_index=0,
                 ensure_story_in_history=lambda: None, ensure_continuity=lambda: None,
                 ensure_bodies=lambda: None, apply_selected_video_model=lambda _: None,
                 review_clip_prompt=lambda *_: None, review_clip=lambda *_: None,
                 clip_label=lambda _: "test cloud", set_progress=lambda *_: None,
                 ui=lambda fn, *args: fn(*args), refresh_table=lambda: None,
                 follow_shot=lambda _: None, update_preview=lambda: None,
                 log=lambda text: events.append(("log", text)))
    load(scope, "project_path")
    load(scope, "save_project")
    load(scope, "finalize_auto_video_postprocesses")

    def check_stop():
        if state["stop"]:
            raise N.Stopped()

    def motion(indices, **kwargs):
        i = indices[0]
        if i in prepared:
            return
        events.append(("prompt", i))
        if i == 2:
            assert scenes[0].get("clip_upscale_status") == "complete"
            assert ("cloud", 1) in events
        if i == 1 and prompt_error:
            ready.set()
            raise prompt_error
        with state["lock"]:
            scenes[i]["motion_image"] = "current-image"
        prepared.add(i)
        scope["save_project"]()
        if i == 1:
            ready.set()

    def cloud(work, i, *, prepared, on_submitted):
        assert prepared and work is not scenes[i]
        if i:
            assert scenes[i - 1]["clip_upscale_status"] == "complete"
            assert Path(scenes[i - 1]["clip"]).read_bytes() == b"finished upscale"
        events.append(("cloud", i))
        raw, output = tmp_path / f"raw{i}.mp4", tmp_path / f"upscaled{i}.mp4"
        raw.write_bytes(b"downloaded clip")
        output.write_bytes(b"finished upscale")
        future = Future()
        futures[i] = (future, output)
        work.update(clip_upscale_status="queued", clip_postprocess_source=str(raw))
        state["auto_video_postprocess_pending"].append(
            {"scene": work, "index": i, "target": str(raw), "source": str(raw), "job": {"future": future}})
        on_submitted()
        if i:
            future.set_result({"path": str(output), "backend": "test upscale"})
        return str(raw)

    scope.update(check_stop=check_stop, stage_motion=motion, make_scene_clip=cloud)
    monkeypatch.setitem(sys.modules, "ai_slow2x", SimpleNamespace(
        ensure_ffmpeg_tool=lambda **_: "test-ffmpeg", _video_dimensions=lambda *_: (3840, 2160)))
    run = load(scope, "run_clips_lookahead")

    def target():
        try:
            run(project, scenes, [0, 1, 2])
        except BaseException as exc:
            errors.append(exc)

    return scope, events, futures, ready, errors, threading.Thread(target=target)


def test_only_one_prompt_ahead_and_upscale_is_a_barrier(tmp_path, monkeypatch):
    scope, events, futures, ready, errors, thread = pipeline_scope(tmp_path, monkeypatch)
    thread.start()
    try:
        assert ready.wait(3), events
        assert events.index(("cloud", 0)) < events.index(("prompt", 1))
        assert ("prompt", 2) not in events and ("cloud", 1) not in events
        # The current cloud result is durable while local upscale is still pending.
        for _ in range(100):
            if (tmp_path / "project.json").exists():
                saved = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
                if saved["scenes"][0].get("clip"):
                    break
            threading.Event().wait(0.01)
        assert saved["scenes"][0]["clip_upscale_status"] == "queued"
        assert saved["scenes"][1]["motion_image"] == "current-image"
    finally:
        future, output = futures[0]
        if not future.done():
            future.set_result({"path": str(output), "backend": "test upscale"})
        thread.join(5)
    assert not thread.is_alive() and not errors
    assert [i for kind, i in events if kind == "cloud"] == [0, 1, 2]
    assert [i for kind, i in events if kind == "prompt"] == [0, 1, 2]
    saved = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    assert all(s["clip_upscale_status"] == "complete" for s in saved["scenes"])
    assert all(Path(s["image"]).read_bytes() == b"preserved image" for s in saved["scenes"])
    assert not scope["state"]["auto_video_postprocess_pending"]


def test_real_slot_adapter_download_and_postprocess_flow_is_bounded(tmp_path, monkeypatch):
    scope, events, futures, ready, errors, thread = pipeline_scope(tmp_path, monkeypatch)
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    downloaded = threading.Event()
    requests = []

    class Box:
        text = ""
        def delete(self, *args): self.text = ""
        def insert(self, _at, text): self.text = text

    box, busy = Box(), [False]
    runtime = scope["runtime"]
    runtime.update(slot_busy=busy, slot_cfg_vars=[{}], slot_images=[Widget()], slot_prompts=[box])

    def submit(slot):
        i = runtime["_auto_video_scene_number_by_slot"][slot] - 1
        if i:
            assert scope["state"]["project"]["scenes"][i - 1]["clip_upscale_status"] == "complete"
        events.append(("cloud", i))
        requests.append(box.text)
        busy[slot] = True

        def finish_download():
            time.sleep(0.02)
            raw, output = downloads / f"raw{i}.mp4", downloads / f"upscaled{i}.mp4"
            raw.write_bytes(b"downloaded clip")
            output.write_bytes(b"finished upscale")
            future = Future()
            futures[i] = (future, output)
            runtime.setdefault("_auto_video_postprocess_jobs", {})[str(raw.resolve())] = {
                "future": future, "slow": False, "target_4k": True, "upscale_enabled": True, "mute": False}
            runtime.setdefault("_auto_video_downloaded_by_slot", {})[slot] = str(raw)
            if i:
                future.set_result({"path": str(output), "backend": "test upscale"})
            busy[slot] = False
            downloaded.set()

        threading.Thread(target=finish_download).start()

    runtime["on_generate_slot"] = submit
    scope.update(video_output_dir=lambda: downloads, run_on_ui=lambda fn: fn(),
                 set_slot_config=lambda *_: None, clip_prompt=lambda _: "approved action",
                 with_retries=lambda _label, fn, **kwargs: fn(),
                 wait_until_video_decodable=lambda _: None,  # fake fixture is not a real MP4
                 assert_video_first_frame_not_other_scene=lambda *_: None,
                 time=SimpleNamespace(time=time.time, strftime=time.strftime, sleep=lambda _: time.sleep(0.02)))
    load(scope, "make_clip")
    load(scope, "make_scene_clip")
    thread.start()
    try:
        assert ready.wait(3) and downloaded.wait(3)
        assert ("cloud", 1) not in events and ("prompt", 2) not in events
    finally:
        future, output = futures[0]
        future.set_result({"path": str(output), "backend": "test upscale"})
        thread.join(5)
    assert not thread.is_alive() and not errors
    assert len(requests) == 3 and all(N.VIDEO_AUDIO_RULE in text for text in requests)
    saved = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    assert all(s["clip_upscale_status"] == "complete" for s in saved["scenes"])
    assert all(Path(s["clip"]).read_bytes() == b"finished upscale" for s in saved["scenes"])


@pytest.mark.parametrize("prompt_error", [N.Stopped(), RuntimeError("next prompt failed")])
def test_next_prompt_failure_drains_and_saves_current_clip(tmp_path, monkeypatch, prompt_error):
    scope, events, futures, ready, errors, thread = pipeline_scope(tmp_path, monkeypatch, prompt_error)
    thread.start()
    try:
        assert ready.wait(3)
        assert thread.is_alive() and ("cloud", 1) not in events
    finally:
        future, output = futures[0]
        future.set_result({"path": str(output), "backend": "test upscale"})
        thread.join(5)
    assert errors == [prompt_error]
    saved = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    assert saved["scenes"][0]["clip_upscale_status"] == "complete"
    assert Path(saved["scenes"][0]["clip"]).read_bytes() == b"finished upscale"
    assert ("cloud", 1) not in events and ("prompt", 2) not in events


def test_upscale_failure_retains_receipt_and_restart_only_retries_local_work(tmp_path, monkeypatch):
    scope, events, futures, ready, errors, thread = pipeline_scope(tmp_path, monkeypatch)
    thread.start()
    assert ready.wait(3)
    futures[0][0].set_exception(RuntimeError("local upscale failed"))
    thread.join(5)
    assert len(errors) == 1 and "อัปสเกลไม่ผ่าน" in str(errors[0])
    saved = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    assert saved["scenes"][0]["clip_upscale_status"] == "failed"
    assert saved["scenes"][0]["clip_postprocess_source"]
    assert ("cloud", 1) not in events and ("prompt", 2) not in events
    scope["state"].update(project=saved, auto_video_postprocess_pending=[])
    local_calls = []

    def queue_local(source, *args, **kwargs):
        local_calls.append(source)
        future = Future()
        future.set_result({"path": str(futures[0][1]), "backend": "local retry"})
        scope["runtime"].setdefault("_auto_video_postprocess_jobs", {})[str(Path(source).resolve())] = {"future": future}

    scope["runtime"]["_queue_auto_video_postprocess"] = queue_local
    scope["finalize_auto_video_postprocesses"]()
    assert len(local_calls) == 1 and saved["scenes"][0]["clip_upscale_status"] == "complete"
    assert [i for kind, i in events if kind == "cloud"] == [0]


@pytest.mark.parametrize("only", [None, "motion"])
def test_full_auto_combines_motion_and_clips_but_prompt_only_stays_prompt_only(only):
    project = {"done": {}}
    events = []
    scope = dict(vars(N), project=project, state={"project": project, "stop": False},
                 video_mode=True, only=only, character_limit=None,
                 stages=[("motion", "prompts", 1), ("clips", "clips", 1)],
                 STAGE_FUNCS={"motion": lambda: events.append("prompts"), "clips": lambda: events.append("combined")},
                 ui=lambda fn, *args: fn(*args), log=lambda *_: None, g={},
                 refresh_snapgen_credit_warning=lambda: None, refresh_stages=lambda *_: None,
                 refresh_all=lambda: None, stage_var=Widget(), detail_var=Widget(), bar=Widget(), start_btn=Widget(),
                 save_project=lambda: None, review_var=SimpleNamespace(get=lambda: False))
    load(scope, "worker", "start_pipeline")()
    assert events == (["combined"] if only is None else ["prompts"])
    assert project["done"]["motion"] and bool(project["done"].get("clips")) == (only is None)


def test_audio_policy_in_writer_and_outgoing_english_slot(tmp_path):
    request = N.motion_request([{"shot": 1, "line": "waves on the beach"}], "period")
    assert N.VIDEO_AUDIO_RULE in request and '"sound_effects"' in request
    assert "ห้ามมีเสียงเพลงหรือดนตรีประกอบเด็ดขาด" in request
    assert "ไม่คัดลอกแม่แบบ" in request
    assert "รายละเอียดพอให้สร้างตรงภาพ" in request
    sample = "[เปิดภาพ] wide coast\n[กล้อง] ดอลลี่ถอยช้าๆ เพื่อเผยทางเดิน\n[จังหวะ] คนคงที่"
    motion = N.motion_only_prompt(sample)
    assert "ดอลลี่ถอยช้าๆ" in motion and "เผยทางเดิน" in motion
    assert "ขนาดภาพ มุมกล้อง เลนส์" not in motion
    scene = {"image": "frame.png", "clip_model": "test-model", "clip_seconds": 6,
             "sound_effects": "soft waves and sea wind"}
    prompt = N.with_video_audio("original request", scene)
    assert N.with_video_audio(prompt, scene) == prompt
    assert "soft waves" in prompt and N.VIDEO_AUDIO_RULE in prompt
    scene["prompt_review"] = {"key": hashlib.md5(b"original requestframe.png").hexdigest(),
                              "english": "translated action without an audio section"}

    class Box:
        text = ""
        def delete(self, *args): self.text = ""
        def insert(self, _at, text): self.text = text

    class Captured(Exception):
        pass

    box = Box()
    def submit(_slot):
        raise Captured()

    runtime = {"slot_busy": [False], "slot_cfg_vars": [{}], "slot_images": [Widget()],
               "slot_prompts": [box], "on_generate_slot": submit}
    scope = dict(vars(N), runtime=runtime, state={"project": {"aspect": "16:9"}}, slot_index=0,
                 video_output_dir=lambda: tmp_path, run_on_ui=lambda fn: fn(), set_slot_config=lambda *_: None,
                 clip_prompt=lambda _: "original request", check_stop=lambda: None, log=lambda *_: None)
    with pytest.raises(Captured):
        load(scope, "make_clip")(scene, 0, prepared=True)
    assert box.text.startswith("translated action")
    assert N.VIDEO_AUDIO_RULE in box.text and "soft waves" in box.text
