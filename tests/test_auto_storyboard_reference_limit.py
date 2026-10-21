"""Exercise the actual storyboard stage without Tk, paid APIs, or recovered code."""
import ast
import os
from pathlib import Path

import pytest


@pytest.mark.parametrize("provider,ref_count,expected", [
    ("maxplus", 13, 9), ("maxplus", 2, 4), ("gpt_web", 13, 6),
])
def test_storyboard_continues_with_provider_limit(tmp_path, provider, ref_count, expected):
    source = Path(__file__).resolve().parents[1] / "snapgen_modules/snapgen_page_narrate.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    stage = next(n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == "stage_storyboard")
    scenes = [{} for _ in range(9)]
    refs = [f"character_{i}.png" for i in range(ref_count)]
    sent, saved, logs = [], [], []

    def make_image(prompt, attachments, folder, name, aspect, **kwargs):
        sent.append(list(attachments))
        return str(folder / (name + ".png"))

    noop = lambda *args, **kwargs: None
    scope = {
        "Path": Path, "os": os, "video_mode": True,
        "state": {"project": {"scenes": scenes, "aspect": "9:16"}, "folder": str(tmp_path)},
        "board_groups": lambda *args, **kwargs: [list(range(9))],
        "ensure_board_template": lambda *args: "grid.png",
        "previous_board_sheet": lambda *args: "previous.png",
        "attachments_for": lambda scene: refs,
        "image_provider_for": lambda stage: provider,
        "is_video_auto_maxplus_provider": lambda value: value == "maxplus",
        "VIDEO_AUTO_MAXPLUS_MODELS": {"maxplus": {"max_references": 9, "label": "MaxPlus"}},
        "with_retries": lambda label, action: action(),
        "make_image": make_image, "board_request": lambda *args, **kwargs: "nine shots",
        "style_text": lambda: "realistic", "crop_board": noop,
        "save_project": lambda: saved.append(True), "log": logs.append,
    }
    for name in ("check_script_matches_audio", "ensure_story_in_history", "ensure_continuity",
                 "ensure_bodies", "check_stop", "set_progress"):
        scope[name] = noop
    for name in ("Stopped", "HistoryLost", "RateLimited", "ImageProviderError"):
        scope[name] = type(name, (Exception,), {})
    exec(compile(ast.Module(body=[stage], type_ignores=[]), str(source), "exec"), scope)
    scope["stage_storyboard"]()

    assert len(sent) == 1
    assert sent[0] == (["grid.png", "previous.png"] + refs)[:expected]
    assert len(sent[0]) == expected
    assert len(saved) == 1
    assert all(scene["board"].endswith(f"panel_{i + 1:03d}.png")
               for i, scene in enumerate(scenes))
    if ref_count + 2 > expected:
        assert any("ไม่แนบเรฟเพิ่ม" in message for message in logs)
