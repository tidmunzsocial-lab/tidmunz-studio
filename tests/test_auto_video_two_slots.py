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


def test_scheduler_single_slot_legacy_is_retained():
    # Existing one-Slot behavior stays in place for test harnesses and older installations.
    source = Path(N.__file__).read_text(encoding="utf-8")
    assert "if slots_ready:" in source
    assert "return run_clips_dual(project, scenes, todo)" in source
    assert "return run_clips_lookahead(project, scenes, todo)" in source
