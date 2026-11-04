"""One-click GPT scene repair must preserve the film's style and continuity."""

import ast
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
import snapgen_page_narrate as N


def load_inner(name, additions):
    tree = ast.parse(Path(N.__file__).read_text(encoding="utf-8-sig"))
    node = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = dict(vars(N))
    scope.update(additions)
    exec(compile(ast.Module(body=[node], type_ignores=[]), N.__file__, "exec"), scope)
    return scope[name]


def make_scope(scene, message, saves):
    project = {
        "scenes": [scene],
        "style_mode": "ภาพยนตร์สมจริง",
        "style_chosen": "Photorealistic Live-Action Thai historical epic",
        "context": {
            "visual_rules": {"color": "gold and teal", "texture": "realistic film"},
            "locks": {"actors": "same faces and costumes"},
        },
    }
    seen = []
    def fake_gpt(prompt, image_path=None):
        seen.append((prompt, image_path))
        return json.dumps(message, ensure_ascii=False)
    scope = dict(state={"project": project}, story_anchor=lambda i: (
        "ช็อต 1: กษัตริย์เดินชายหาด; ฉากก่อนหน้าท้าวพรหมเทพเดินมาจากฝั่งซ้าย; "
        "ฉากถัดไปนาคโผล่ขึ้นจากทะเล"),
        gpt_text=fake_gpt, parse_json_reply=json.loads,
        ensure_bodies=lambda: None, save_project=lambda: saves.append(deepcopy(project)),
        log=lambda msg: None)
    return load_inner("refine_scene_prompt", scope), project, seen


def test_camera_refinement_keeps_style_actor_story_and_existing_media(tmp_path):
    image = tmp_path / "original_scene.png"
    image.write_bytes(b"preserved")
    old = (
        "Photorealistic Live-Action Film Still, gold and teal color grade, "
        "Extreme Wide Establishing Shot เลนส์ 24mm "
        "ท้าวพรหมเทพในชุดทองอยู่ชายหาดด้านซ้าย พญานาคด้านขวา "
        "แสงบ่าย มุมทะเลเดิม ไม่เปลี่ยนชุดหรือหน้า"
    )
    scene = {
        "image": str(image), "clip": str(tmp_path / "paid_clip.mp4"),
        "shot_type": "action", "has_people": True,
        "characters": ["ท้าวพรหมเทพ"], "location": "ชายหาด",
        "video_prompt": "พระองค์เดินเข้าใกล้ทะเล", "prompt": old,
    }
    prior = deepcopy(scene)
    saves = []
    refine, project, seen = make_scope(
        scene, {"camera": "medium_close", "reason": "ใบหน้าอยู่ไกลเกินไป",
                "prompt": "ANIME CARTOON CHARACTER REPLACEMENT"}, saves)
    result = refine(0)
    assert "Medium Close-Up" in result
    assert "Extreme Wide" not in result and "24mm" not in result
    for phrase in ("Photorealistic Live-Action", "gold and teal", "ท้าวพรหมเทพ",
                   "ชุดทอง", "ชายหาดด้านซ้าย", "พญานาคด้านขวา", "แสงบ่าย"):
        assert phrase in result
    assert "ANIME" not in result
    assert scene["prompt_before_refine"] == old
    assert scene["clip"] == prior["clip"]
    assert scene["video_prompt"] == prior["video_prompt"]
    assert image.read_bytes() == b"preserved"
    assert len(saves) == 1
    assert seen[0][1] == str(image)
    assert "same faces and costumes" in seen[0][0]
    assert "ฉากถัดไป" in seen[0][0]


def test_gpt_keep_camera_is_noop_without_credit_or_unwanted_scene_change(tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"unchanged")
    scene = {"image": str(image), "characters": ["กษัตริย์"], "has_people": True,
             "shot_type": "character", "prompt": "Medium Shot เลนส์ 50mm กษัตริย์ในชุดเดิม"}
    before = deepcopy(scene)
    saves = []
    refine, _, _ = make_scope(scene, {"camera": "keep", "reason": "เห็นหน้าชัด"}, saves)
    assert refine(0) == before["prompt"]
    assert scene == before and saves == []


def test_gpt_cannot_force_scenery_reframe(tmp_path):
    image = tmp_path / "scenery.jpg"
    image.write_bytes(b"unchanged")
    scene = {"image": str(image), "characters": [], "has_people": False,
             "shot_type": "scenery", "prompt": "Extreme Wide Shot 24mm เมืองโบราณไม่มีคน"}
    before = deepcopy(scene)
    saves = []
    refine, _, _ = make_scope(scene, {"camera": "medium", "reason": "keep angle"}, saves)
    assert refine(0) == before["prompt"]
    assert scene == before and saves == []


@pytest.mark.parametrize("camera", ["cartoon", "wide", "", None])
def test_unknown_camera_decision_does_not_save_or_replace_scene(tmp_path, camera):
    image = tmp_path / "scene.jpg"
    image.write_bytes(b"unchanged")
    scene = {"image": str(image), "characters": ["กษัตริย์"], "has_people": True,
             "prompt": "Wide Shot 24mm กษัตริย์กลางสนาม"}
    before = deepcopy(scene)
    saves = []
    refine, _, _ = make_scope(scene, {"camera": camera, "prompt": "different story"}, saves)
    with pytest.raises(RuntimeError, match="มุมกล้อง"):
        refine(0)
    assert scene == before and saves == []


def test_unrendered_image_refuses_gpt_rewrite_removing_character():
    original = "กษัตริย์ท้าวพรหมเทพในชุดทองยืนชายหาด สไตล์ภาพยนตร์สมจริง"
    scene = {"image": "", "characters": ["ท้าวพรหมเทพ"], "location": "ชายหาด",
             "has_people": True, "prompt": original}
    saves = []
    refine, _, seen = make_scope(scene, {"prompt": "นางฟ้าการ์ตูนในป่า"}, saves)
    with pytest.raises(RuntimeError, match="ตัวละครหรือสถานที่"):
        refine(0)
    assert scene["prompt"] == original and saves == []
    assert seen[0][1] is None
    assert "gold and teal" in seen[0][0]
    assert "สไตล์" in seen[0][0]


def test_gpt_text_sends_one_existing_image_and_keeps_text_only_call_compatible():
    sent = []
    def open_bridge(request):
        sent.append(json.loads(request.data.decode("utf-8")))
        return {"choices": [{"message": {"content": '{"camera":"keep"}'}}]}
    scope = dict(g={"_chatgpt_api_base": lambda: "http://127.0.0.1:8766"},
                 queued_bridge=lambda fn: fn(), open_bridge=open_bridge,
                 image_data_url=lambda p, max_side=768: "data:image/png;base64,abcd",
                 os=type("Os", (), {"path": type("Path", (), {"isfile": lambda p: True})})())
    client = load_inner("gpt_text", scope)
    assert client("inspect", image_path="scene.png") == '{"camera":"keep"}'
    assert isinstance(sent[-1]["messages"][0]["content"], list)
    assert len(sent[-1]["messages"][0]["content"]) == 2
    client("ordinary prompt")
    assert sent[-1]["messages"][0]["content"] == "ordinary prompt"


@pytest.mark.parametrize("camera", ["medium", "medium_two", "medium_close", "close"])
def test_bounded_camera_choices_preserve_rest_of_story(camera):
    scene = {"prompt": "Medium Shot 50mm Photorealistic Thai Epic กษัตริย์ด้านซ้าย พญานาคด้านขวา",
             "has_people": True, "characters": ["กษัตริย์"]}
    old = scene["prompt"]
    N.apply_camera_only_refinement(scene, camera)
    assert scene.get("prompt_before_refine", old) == old
    for phrase in ("Photorealistic Thai Epic", "กษัตริย์ด้านซ้าย", "พญานาคด้านขวา"):
        assert phrase in scene["prompt"]
    assert not N._UNSAFE_CAMERA_SIZE.search(scene["prompt"])


def test_paid_redraw_backs_up_existing_image_before_generating(tmp_path):
    original = tmp_path / "scene_013.png"
    original.write_bytes(b"valuable original image")
    scene = {
        "image": str(original), "clip": str(tmp_path / "clip_013_4k.mp4"),
        "prompt": "Medium Shot สไตล์ภาพยนตร์สมจริง",
        "prompt_before_refine": "Wide Shot สไตล์ภาพยนตร์สมจริง",
    }
    prior = deepcopy(scene)
    backup = Path(N.backup_image_before_gpt_refine_redraw(scene, tmp_path, 12))
    assert backup != original
    assert backup.is_file() and backup.read_bytes() == original.read_bytes()
    assert scene["image"] == prior["image"] and scene["clip"] == prior["clip"]
    assert scene["image_history"][-1]["image"] == str(backup)
    assert scene["image_history"][-1]["clip"] == prior["clip"]
    assert scene["image_history"][-1]["prompt"] == prior["prompt_before_refine"]
    assert original.read_bytes() == b"valuable original image"


def test_missing_image_does_not_create_spurious_history(tmp_path):
    scene = {"image": str(tmp_path / "missing.png"), "prompt": "ยังไม่มีรูป"}
    assert N.backup_image_before_gpt_refine_redraw(scene, tmp_path, 0) == ""
    assert "image_history" not in scene


def test_two_shot_can_be_replaced_without_conflicting_camera_directives():
    scene = {"prompt": "Medium Two-Shot เลนส์ 50mm คนสองคนอยู่ริมฝั่งทะเล",
             "has_people": True, "characters": ["กษัตริย์", "ราชินี"]}
    assert N.apply_camera_only_refinement(scene, "medium_close")
    assert scene["prompt"].startswith("Medium Close-Up")
    assert "Medium Two-Shot" not in scene["prompt"]
