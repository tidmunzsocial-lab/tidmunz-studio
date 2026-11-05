"""Zero-credit dry-run: check parallel scheduler, persistence, and stop-drain semantics."""
import ast
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "snapgen_modules" / "snapgen_page_narrate.py"
GUI = ROOT / "snapgen_gui_v2.py"
NODES = ast.parse(SOURCE.read_text(encoding="utf-8"))
FN = next(n for n in ast.walk(NODES) if isinstance(n, ast.FunctionDef) and n.name == "run_clips_dual")


class StopRequested(Exception):
    pass


def check_case(stop_early=False):
    with TemporaryDirectory() as tmp:
        folder = Path(tmp)
        scenes = []
        for i in range(3):
            img = folder / f"image_{i}.png"
            img.write_bytes(b"image")
            scenes.append({"image": str(img), "seen": "ok", "video_prompt": f"motion-{i}"})
        project = {"scenes": scenes, "duration": 30}
        state = {"project": project, "folder": tmp, "lock": threading.RLock(),
                 "auto_video_postprocess_pending": []}
        calls, errors = [], []
        accepted_both = threading.Event()
        release = threading.Event()
        lock = threading.Lock()
        stop_flag = threading.Event()

        def cloud(work, i, *, prepared, on_submitted, slot_override):
            assert prepared and work is not scenes[i]
            with lock:
                calls.append((i, slot_override))
                if len(calls) == 2:
                    accepted_both.set()
            on_submitted()
            if i < 2:
                assert release.wait(5), "two jobs must overlap"
            output = folder / f"shot_{i}_slot_{slot_override}.mp4"
            output.write_bytes(f"{i}/{slot_override}".encode())
            return str(output)

        def save_project():
            with state["lock"]:
                (folder / "project.json").write_text(json.dumps(project), encoding="utf-8")

        def check_stop():
            if stop_flag.is_set():
                raise StopRequested("pause after in-flight jobs")

        scope = {
            "ThreadPoolExecutor": ThreadPoolExecutor,
            "threading": threading, "os": os,
            "state": state, "slot_index": 1,
            "ensure_story_in_history": lambda: None,
            "ensure_continuity": lambda: None, "ensure_bodies": lambda: None,
            "stage_motion": lambda *a, **kw: None,
            "apply_selected_video_model": lambda p: None,
            "operator_visual_review_valid": lambda s: True,
            "with_video_audio": lambda p, s: p,
            "review_clip_prompt": lambda s, i: None,
            "save_project": save_project,
            "check_stop": check_stop,
            "clip_label": lambda s: "test",
            "set_progress": lambda *a: None,
            "ui": lambda fn, *a: fn(*a),
            "refresh_table": lambda: None, "follow_shot": lambda i: None,
            "update_preview": lambda: None,
            "make_scene_clip": cloud,
            "review_clip": lambda scene, i: None,
            "finalize_auto_video_postprocesses": lambda: None,
            "log": lambda msg: None,
        }
        exec(compile(ast.Module(body=[FN], type_ignores=[]), str(SOURCE), "exec"), scope)
        def run():
            try:
                scope["run_clips_dual"](project, scenes, [0, 1, 2])
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=run)
        thread.start()
        assert accepted_both.wait(5), f"never submitted two slots: {calls}"
        assert len(calls) == 2, calls
        assert {slot for _, slot in calls} == {0, 1}, calls
        if stop_early:
            stop_flag.set()
        release.set()
        thread.join(7)
        assert not thread.is_alive(), "scheduler hung"
        if stop_early:
            assert len(calls) == 2 and errors and isinstance(errors[0], StopRequested), (calls, errors)
        else:
            assert not errors and calls == [(0, 1), (1, 0), (2, 1)], (calls, errors)
        assert all(Path(sc["clip"]).is_file() for sc in scenes[:2])
        saved = json.loads((folder / "project.json").read_text(encoding="utf-8"))
        assert all(Path(sc["clip"]).is_file() for sc in saved["scenes"][:2])
        if stop_early:
            assert not scenes[2].get("clip")
        else:
            assert Path(scenes[2]["clip"]).read_bytes() == b"2/1"
        print("PASS", "stop-drain" if stop_early else "dual-slots", "cloud jobs", len(calls))


if __name__ == "__main__":
    compile(SOURCE.read_text(encoding="utf-8"), str(SOURCE), "exec")
    compile(GUI.read_text(encoding="utf-8"), str(GUI), "exec")
    assert "_video_uuid_slots[str(uuid)] = i" in GUI.read_text(encoding="utf-8")
    assert "_video_uuid_slots.get(str(uuid)" in GUI.read_text(encoding="utf-8")
    check_case(False)
    check_case(True)
    print("PASS syntax, UUID->slot binding, two concurrent in-flight, stop without re-submit")
