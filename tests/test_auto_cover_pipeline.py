# -*- coding: utf-8 -*-
"""Exercise the real Auto stage_covers function with five local mock pictures, no paid API."""
import ast
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "snapgen_modules"))
SOURCE = (ROOT / "snapgen_modules/snapgen_page_narrate.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def nested_stage(namespace):
    fn = next(n for n in ast.walk(TREE) if isinstance(n, ast.FunctionDef) and n.name == "stage_covers")
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "auto_covers", "exec"), namespace)
    return namespace["stage_covers"]


def make_project(tmp_path):
    refs = tmp_path / "refs"
    refs.mkdir()
    Image.new("RGB", (96, 96), (100, 70, 50)).save(refs / "มฆมานพ.png")
    # No completed video is necessary: the cover button must work standalone.
    return {"script": "บท - มฆมานพ.docx",
            "context": {"characters": [
                {"name": "มฆมานพ", "visual_identity": "human Thai villager, not a deity"}]},
            "scenes": [{"text": "มฆมานพในหมู่บ้าน", "characters": ["มฆมานพ"]}]}


def test_five_automated_covers_are_saved_in_project_then_resume_without_api(tmp_path):
    project = make_project(tmp_path)
    state = {"folder": str(tmp_path), "project": project}
    calls = {"gpt": 0, "images": 0, "log": []}
    def designs(_prompt):
        calls["gpt"] += 1
        return {"covers": [
            {"prompt": "Photorealistic cinematic Thai film. Historical human village "
                       f"key art concept {i}, expressive open eyes, full frame without words."}
            for i in range(5)
        ]}
    def image(prompt, refs, output_dir, name, aspect, **kwargs):
        calls["images"] += 1
        assert aspect == "16:9"
        assert refs and all(str(tmp_path / "refs") in p for p in refs)
        assert kwargs.get("fresh_chat") is True
        assert "BOTH EYES OPEN" in prompt
        assert "NO TEXT" in prompt
        assert "NEVER depict the ending" in prompt
        folder = Path(output_dir)
        assert folder.is_dir()
        file = folder / f"{name}.png"
        Image.new("RGB", (640, 360), (65 + calls["images"], 80, 95)).save(file)
        return str(file)
    def save():
        (tmp_path / "project.json").write_text(
            json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    ns = {"video_mode": True, "Path": Path, "state": state,
          "gpt_look": designs, "make_image": image,
          "story_script": lambda: "กาลครั้งหนึ่งมฆมานพยังเป็นมนุษย์",
          "log": calls["log"].append, "check_stop": lambda: None,
          "set_manual_progress": lambda *args: None, "save_project": save}
    stage = nested_stage(ns)
    stage()
    assert calls["gpt"] == 1
    assert calls["images"] == 5
    assert len(project["cover_images"]) == 5
    for idx in range(1, 6):
        out = Path(project["cover_images"][str(idx)])
        assert out.parent == tmp_path / "หน้าปก"
        assert out.is_file()
        with Image.open(out) as im:
            assert im.size == (1920, 1080)
    assert "active_image_stage" not in state
    saved = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    assert len(saved["cover_designs"]) == 5
    stage()
    assert calls["gpt"] == 1 and calls["images"] == 5, "must not spend for completed covers"
    Path(project["cover_images"]["3"]).unlink()
    stage()
    assert calls["gpt"] == 1 and calls["images"] == 5, "must reuse already-paid source image"
    assert Path(project["cover_images"]["3"]).is_file()


def test_no_reference_stops_before_gpt_generation(tmp_path):
    project = make_project(tmp_path)
    (tmp_path / "refs" / "มฆมานพ.png").unlink()
    ns = {"video_mode": True, "Path": Path,
          "state": {"folder": str(tmp_path), "project": project},
          "gpt_look": lambda _: pytest.fail("GPT call before refs"),
          "save_project": lambda: None}
    with pytest.raises(RuntimeError, match="เรฟ"):
        nested_stage(ns)()
