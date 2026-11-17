"""Progress for multiple simultaneous paid clips must be per UUID/shot, not global."""
import ast
import inspect
import math
import sys
from pathlib import Path
from threading import RLock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
import snapgen_page_narrate as N


def test_parallel_video_rows_show_independent_provider_percentages():
    state = {"lock": RLock(), "visible_jobs": {"videos": {}},
             "clip_generation_pct_by_scene": {}}
    for n in (41, 43, 44):
        N._track_visible_job(state, "videos", n, "active")
    state["clip_generation_pct_by_scene"].update({41: 35, 43: 72, 44: 1})
    rows = [N._video_job_progress_line(
        n, state["clip_generation_pct_by_scene"].get(n))
        for n in (41, 43, 44)]
    assert rows == [
        "วิดีโอ · ช็อต 41 · กำลังทำงาน · 35%",
        "วิดีโอ · ช็อต 43 · กำลังทำงาน · 72%",
        "วิดีโอ · ช็อต 44 · กำลังทำงาน · 1%",
    ]


@pytest.mark.parametrize("percent", [None, "unknown", "", float("nan"), -3, 122, True])
def test_unknown_or_invalid_provider_percent_is_never_invented(percent):
    assert N._video_job_progress_line(44, percent) == (
        "วิดีโอ · ช็อต 44 · กำลังทำงาน · รอเปอร์เซ็นต์จาก API"
    )


def test_provider_percent_zero_is_a_real_reported_value():
    assert N._video_job_progress_line(43, 0).endswith("0%")
    assert N._video_job_progress_line(43, 99.9).endswith("99%")


def test_reuse_same_shot_does_not_inherit_an_old_uuid_percentage():
    state = {"lock": RLock(), "visible_jobs": {"videos": {}},
             "clip_generation_pct_by_scene": {}}
    N._track_visible_job(state, "videos", 44, "active")
    state["clip_generation_pct_by_scene"][44] = 74
    N._track_visible_job(state, "videos", 44, None)
    assert 44 not in state["clip_generation_pct_by_scene"]
    N._track_visible_job(state, "videos", 44, "active")
    assert "รอเปอร์เซ็นต์จาก API" in N._video_job_progress_line(
        44, state["clip_generation_pct_by_scene"].get(44))


def test_actual_uuid_routing_never_changes_the_global_stage_banner():
    source = inspect.getsource(N._build)
    tree = ast.parse(source)
    method = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and
                  node.name == "show_auto_generation_progress")
    runtime = {"_auto_video_receipt_by_slot": {
        0: {"uuid": "uuid-41", "scene_number": 41},
        1: {"uuid": "uuid-43", "scene_number": 43},
        2: {"uuid": "uuid-44", "scene_number": 44},
    }}
    state = {"lock": RLock(), "visible_jobs": {"videos": {
        41: "active", 43: "active", 44: "active"
    }}, "clip_generation_pct_by_scene": {}, "detail": "สร้างคลิป 44/114 · 3 Slot"}
    scenes = [{} for _ in range(114)]
    namespace = {
        "runtime": runtime, "state": state, "scenes": scenes,
        "ui": lambda callback: callback(),
        "set_progress": lambda *args: pytest.fail("Never update global banner for one UUID"),
    }
    exec(compile(ast.fix_missing_locations(ast.Module(
        body=[method], type_ignores=[])), "<per_uuid_progress>", "exec"), namespace)
    on_percentage = namespace["show_auto_generation_progress"]
    on_percentage(0, "uuid-41", 38)
    on_percentage(1, "uuid-43", 90)
    on_percentage(2, "uuid-44", 1)
    on_percentage(1, "uuid-INVALID", 55)
    on_percentage(2, "uuid-44", 101)
    assert state["clip_generation_pct_by_scene"] == {41: 38, 43: 90, 44: 1}
    assert state["detail"] == "สร้างคลิป 44/114 · 3 Slot"
    # A new receipt for Slot 2 cannot be mistaken for the previous shot.
    runtime["_auto_video_receipt_by_slot"][2] = {
        "uuid": "uuid-45", "scene_number": 45
    }
    on_percentage(2, "uuid-44", 99)
    assert state["clip_generation_pct_by_scene"][44] == 1
    state["visible_jobs"]["videos"].pop(41)
    on_percentage(0, "uuid-41", 98)
    assert state["clip_generation_pct_by_scene"][41] == 38
    assert "_video_job_progress_line(n, provider_progress.get(n))" in source
