"""Regression checks for face-safe camera choices before AI image/video generation."""

import ast
import json
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
import snapgen_page_narrate as N


def test_shot_13_extreme_wide_from_dop_becomes_medium_without_losing_story():
    scene = {
        "characters": ["ท้าวพรหมเทพ", "ท้าวธันตะรด"],
        "has_people": True,
        "shot_type": "action",
        "prompt": (
            "ภาพยนตร์ไทยโบราณ Extreme Wide Establishing Shot เลนส์ 24mm "
            "ท้าวพรหมเทพอยู่ด้านซ้ายบนชายหาด พญานาคอยู่ในทะเลด้านขวาระยะไกล "
            "แสงแดดยามบ่าย รักษาหน้าตาเครื่องทรงจากภาพอ้างอิง"
        ),
        "video_prompt": "ท้าวพรหมเทพเดินแล้วหยุดมองพญานาคหนึ่งครั้ง",
    }
    prior = scene["prompt"]
    assert N.enforce_face_safe_framing(scene)
    assert "Medium Shot" in scene["prompt"]
    assert "Extreme Wide" not in scene["prompt"]
    assert "24mm" not in scene["prompt"]
    assert "50mm" in scene["prompt"]
    assert "ด้านซ้าย" in scene["prompt"] and "ด้านขวาระยะไกล" in scene["prompt"]
    assert "ท้าวพรหมเทพ" in scene["prompt"] and "พญานาค" in scene["prompt"]
    assert scene["prompt_before_face_framing"] == prior
    assert scene["video_prompt"] == "ท้าวพรหมเทพเดินแล้วหยุดมองพญานาคหนึ่งครั้ง"
    assert not N.enforce_face_safe_framing(scene)  # Repeated runs never stack edits.


def test_scenery_only_keeps_extreme_wide_and_24mm():
    scene = {"shot_type": "scenery", "has_people": False, "characters": [],
             "prompt": "Extreme Wide Establishing Shot เลนส์ 24mm เมืองโบราณกลางหุบเขา"}
    before = dict(scene)
    assert not N.enforce_face_safe_framing(scene)
    assert scene == before


@pytest.mark.parametrize("prompt", [
    "ช็อตกว้างมาก มุมระดับสายตา 28mm บุคคลอยู่ด้านซ้ายของภาพ",
    "Wide Shot, 24mm, actor smiles at camera",
    "Long Shot, 35mm, actor approaches from the forest",
    "Medium Wide Shot, 35mm, actors walking on a beach",
    "Extreme Wide Angle Shot, 24mm, royal costume in a temple",
    "ช็อตมุมกว้าง เลนส์ 24mm เห็นกษัตริย์ยืนอยู่ฝั่งซ้าย",
    "ภาพวิวกว้างมาก แต่ช็อตนี้มีตัวละครสำคัญในเฟรม",
])
def test_people_and_character_shots_cannot_remain_wide(prompt):
    scene = {"characters": ["พระเอก"], "has_people": True, "shot_type": "character", "prompt": prompt}
    assert N.enforce_face_safe_framing(scene)
    assert not N._UNSAFE_CAMERA_SIZE.search(scene["prompt"])
    assert N._SAFE_CAMERA_SIZE.search(scene["prompt"])
    assert "24mm" not in scene["prompt"] and "28mm" not in scene["prompt"]


def test_requests_no_longer_force_establishing_with_people():
    scene = {"start": 0.0, "end": 8.0, "text": "กษัตริย์พบพญานาค"}
    req = N.video_plan_request([(1, scene)], ["กษัตริย์"], "", "", direction="one sequence")
    dop = N.cinematographer_request([{"i": 1, "narration": scene["text"], "prompt": "เรื่อง", "characters": ["กษัตริย์"]}], "", "", False)
    director = N.director_request([scene], ["กษัตริย์"], "")
    for text in (req, dop, director):
        assert "FACE" not in text  # Plain Thai instructions are handed to the provider.
        assert "shot_type=scenery" in text
        assert "Medium Shot" in text
        assert "ไม่ต้องเปลี่ยนมุมภาพเพียงเพราะช็อตก่อนหน้า" in text


def test_video_planner_normalizes_gpt_wide_even_if_it_ignores_instructions():
    segs = [{"start": 0, "end": 8, "text": "กษัตริย์พบพญานาค"}]

    def ask(prompt):
        if "คุณคือผู้กำกับภาพยนตร์" in prompt:
            return {"sequences": [{"shots": [1, 1], "visual_plan": "มุมกว้าง"}]}
        return {"scenes": [{
            "shot": 1, "characters": ["กษัตริย์"], "shot_type": "action",
            "has_people": True, "prompt": "Extreme Wide Establishing Shot 24mm ชายหาด",
            "video_prompt": "กษัตริย์เดิน", "location": "ชายหาด",
        }]}

    scenes = N.plan_video(segs, 8, ["กษัตริย์"], "", ask, video_model=N.VIDEO_GROK_LITE_MODEL)
    assert len(scenes) == 1
    assert "Medium Shot" in scenes[0]["prompt"]
    assert "Extreme Wide" not in scenes[0]["prompt"]
    assert scenes[0]["video_prompt"] == "กษัตริย์เดิน"
    assert scenes[0]["prompt_before_face_framing"].startswith("Extreme Wide")


def _dop_worker_with_gpt_return(reply):
    """Exercise the production cinematographer_pass function without external API calls."""
    tree = ast.parse(Path(N.__file__).read_text(encoding="utf-8-sig"))
    worker_node = next(n for n in ast.walk(tree)
                       if isinstance(n, ast.FunctionDef) and n.name == "cinematographer_pass")
    scene = {"prompt": "ช็อตกลาง Medium Shot เลนส์ 50mm กษัตริย์ด้านซ้าย",
             "characters": ["กษัตริย์"], "has_people": True,
             "shot_type": "action", "text": "กษัตริย์เห็นพญานาค",
             "video_prompt": "พระองค์ตกใจ", "location": "ชายหาด"}
    project = {"scenes": [scene], "context": {}, "style_mode": "ปกติ"}
    events = []
    def provider(_request):
        if isinstance(reply, Exception):
            raise reply
        return json.dumps(reply, ensure_ascii=False)

    scope = dict(vars(N),
                 state={"project": project}, ensure_scene_text=lambda: None,
                 check_stop=lambda: None, gpt_text=provider,
                 parse_json_reply=lambda msg: json.loads(msg),
                 set_progress=lambda *args: None, save_project=lambda: events.append("saved"),
                 ui=lambda cb: cb(), refresh_table=lambda: None,
                 log=events.append, error_cause=str)
    exec(compile(ast.Module(body=[worker_node], type_ignores=[]), N.__file__, "exec"), scope)
    scope["cinematographer_pass"]()
    return project, scene, events


def test_dop_rewrite_cannot_reintroduce_extreme_wide():
    project, scene, events = _dop_worker_with_gpt_return({
        "scenes": [{"i": 1, "prompt": "Extreme Wide Establishing Shot เลนส์ 24mm กษัตริย์ด้านซ้ายกับพญานาคด้านขวา"}]
    })
    assert project["dop_done"] is True and "saved" in events
    assert "Medium Shot" in scene["prompt"]
    assert "24mm" not in scene["prompt"]
    assert "Extreme Wide" not in scene["prompt"]
    assert scene["prompt_before_dop"].startswith("ช็อตกลาง")
    assert scene["prompt_before_face_framing"].startswith("Extreme Wide")
    assert scene["video_prompt"] == "พระองค์ตกใจ"


def test_dop_timeout_still_guards_initial_wide_plan():
    project, scene, events = _dop_worker_with_gpt_return(RuntimeError("GPT timeout"))
    assert project["dop_done"] is True and "saved" in events
    assert "Medium Shot" in scene["prompt"]
