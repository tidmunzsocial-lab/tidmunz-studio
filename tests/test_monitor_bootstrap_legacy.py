"""Legacy in-progress films must not be blocked by new chat-app bootstrap."""
import ast
import os
from pathlib import Path

SOURCE = Path(__file__).parents[1] / "snapgen_modules" / "snapgen_page_narrate.py"


def _legacy_guard():
    tree = ast.parse(SOURCE.read_text(encoding="utf8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = ast.unparse(node.test)
        if ("project.get('done', {}).get('monitor')" in test
                and "project.get('done', {}).get('images')" in test
                and "sc.get('clip')" in test):
            if node.body and isinstance(node.body[0], ast.Assign):
                target = node.body[0].targets[0]
                if isinstance(target, ast.Name) and target.id == "keys":
                    found.append(node)
    assert len(found) == 1, "Exactly one existing-project monitor exception expected"
    guard = ast.fix_missing_locations(ast.Module(body=[found[0]], type_ignores=[]))
    return compile(guard, "legacy-monitor-guard", "exec")


def _apply_guard(project, *, video_mode=True, only=None):
    ns = {"video_mode": video_mode, "only": only, "project": project,
          "keys": ["monitor", "analysis", "images", "motion", "clips", "video"],
          "os": os, "log": lambda *args: None}
    exec(_legacy_guard(), ns)
    return ns["keys"]


def test_in_progress_film_skips_new_monitor_stage_without_false_binding(tmp_path):
    clip = tmp_path / "existing-clip.mp4"
    clip.write_bytes(b"clip already delivered")
    project = {"scenes": [{"clip": str(clip)}],
               "done": {"analysis": True, "images": True}}
    keys = _apply_guard(project)
    assert "monitor" not in keys
    assert "clips" in keys and "video" in keys
    assert "monitor" not in project["done"]
    assert "monitor_chat" not in project


def test_new_film_still_requires_real_app_bootstrap():
    assert "monitor" in _apply_guard({"scenes": [], "done": {}})


def test_unfinished_without_saved_clip_still_requires_monitor(tmp_path):
    project = {"scenes": [{"clip": str(tmp_path / "missing.mp4")}],
               "done": {"analysis": True, "images": True}}
    assert "monitor" in _apply_guard(project)


def test_nonvideo_or_other_stage_does_not_bypass_monitor(tmp_path):
    clip = tmp_path / "ready.mp4"
    clip.write_bytes(b"ready")
    project = {"scenes": [{"clip": str(clip)}], "done": {"analysis": True, "images": True}}
    assert "monitor" in _apply_guard(project, video_mode=False)
    assert "monitor" in _apply_guard(project, only="clips")
