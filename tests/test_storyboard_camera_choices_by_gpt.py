"""Camera angles are chosen by GPT from the screenplay, never randomly assigned."""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "snapgen_modules"))
import snapgen_page_narrate as narrate


def test_dop_request_explicitly_delegates_to_gpt_and_allows_story_motivated_angles():
    request = narrate.cinematographer_request(
        [{"i": 1, "narration": "ชายคนหนึ่งสังเกตเหตุการณ์จากหน้าต่าง",
          "prompt": "บ้านยามเย็น", "characters": ["ชาย"], "location": "หน้าต่าง"}],
        "", "ปัจจุบัน", False)
    for word in ("GPT", "แอบถ่าย", "แคนดิด", "มุมสูง", "มุมด้านข้าง", "ไม่สุ่มมุม"):
        assert word in request
    assert "ไม่บังคับให้ใช้ครบ" in request or "ไม่บังคับให้ใช้ครบ" in narrate.GPT_STORYBOARD_CAMERA_CHOICE
    assert "หน้าตรง" in request


def test_storyboard_prompt_respects_per_shot_gpt_camera_direction():
    scene = {"prompt": "ภาพแคนดิด มุมสูงเฉียงลงมาจากหน้าต่าง เห็นผู้ชายก้มอ่านจดหมาย",
             "continuity": "ชายถือจดหมายอยู่ริมหน้าต่าง"}
    request = narrate.board_request([(1, scene)], "16:9", live_action=True)
    assert "ภาพแคนดิด มุมสูงเฉียงลงมาจากหน้าต่าง" in request
    assert "ช็อตที่ GPT กำหนดมุมไว้แล้ว" in request
    assert "ไม่สุ่มมุม" in request


def test_preview_storyboard_image_prompt_lets_gpt_choose_without_rotation():
    source = (ROOT / "snapgen_gui_v2.py").read_text(encoding="utf8")
    tree = ast.parse(source)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "_build_prompt_ref_storyboard_image_request")
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]),
                 "<isolated storyboard request>", "exec"), namespace)
    request = namespace[function.name]("ชายเดินเข้าตลาดแล้วสังเกตคนขายของ",
                                       {"time_of_day": "DAY"}, [])
    for word in ("GPT", "แอบถ่าย", "candid", "high angle", "มุมข้าง", "ไม่สุ่มมุม"):
        assert word in request
    assert "ไม่บังคับใช้ทุกมุม" in request
    # The shot prompt planning stage must use the same creative principle.
    assert "ให้ GPT ผู้กำกับภาพเลือกมุมกล้อง" in source


def test_no_round_robin_or_random_camera_assignment_and_image_copied_once():
    code = (ROOT / "snapgen_modules" / "snapgen_page_narrate.py").read_text(encoding="utf8")
    assert "CAMERA_ANGLES[" not in code
    assert "random.choice(CAMERA" not in code
    gui = (ROOT / "snapgen_gui_v2.py").read_text(encoding="utf8")
    assert 'board_folder = Path(EXPORT_IMAGE) / "storyboard"' in gui
    assert "shutil.copy2(output_path, destination)" in gui
    assert '"storyboard_copy_path": storyboard_copy' in gui
