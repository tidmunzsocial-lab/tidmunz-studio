import sys
from pathlib import Path

MODULES = Path(__file__).resolve().parents[1] / "snapgen_modules"
if str(MODULES) not in sys.path:
    sys.path.insert(0, str(MODULES))

from snapgen_page_ref import _character_context_prompt_details, _ref_auto_history_payload


def test_character_context_uses_canonical_face_and_hair_fields():
    details = _character_context_prompt_details({
        "visual_identity": "หญิงชาวบ้านผู้กล้าหาญ",
        "appearance": {
            "age": "ประมาณ 30 ปี",
            "face": "ใบหน้ารูปหัวใจ กรามแคบ มีไฝข้างแก้มซ้าย",
            "hair": "ผมดำยาวถักเปียต่ำ",
        },
    })
    assert "โครงหน้าและลักษณะใบหน้า: ใบหน้ารูปหัวใจ" in details
    assert "ทรงผมและเส้นผม: ผมดำยาวถักเปียต่ำ" in details
    assert "ภาพจำ/เอกลักษณ์: หญิงชาวบ้านผู้กล้าหาญ" in details


def test_character_context_falls_back_to_legacy_fields():
    details = _character_context_prompt_details({
        "visual_identity": "ทหารผ่านศึก",
        "ทรงผม": "ผมสั้นหยักศก",
        "ใบหน้า": "กรามกว้าง คิ้วหนา",
    })
    assert "โครงหน้าและลักษณะใบหน้า: กรามกว้าง คิ้วหนา" in details
    assert "ทรงผมและเส้นผม: ผมสั้นหยักศก" in details


def test_auto_character_gpt_history_is_isolated_and_other_ref_keeps_history():
    assert _ref_auto_history_payload(True, "character") == {"_temporary_chat": True}
    assert _ref_auto_history_payload(True, "location") == {"_use_ref_story_history": True}
    assert _ref_auto_history_payload(False, "character") == {"_use_ref_story_history": True}
