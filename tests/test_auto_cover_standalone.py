# -*- coding: utf-8 -*-
"""Standalone cover art: input windows, no titles, safe resume and red UI contract."""
import importlib.util
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "snapgen_modules" / "snapgen_page_narrate.py"
HELPER = ROOT / "snapgen_modules" / "snapgen_auto_covers.py"
SPEC = importlib.util.spec_from_file_location("snapgen_auto_covers", HELPER)
COVERS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COVERS)


def project():
    return {
        "script": "บท - ปมลับ.txt",
        "context": {
            "story": {"ending": "FINAL_SPOILER_SECRET"},
            "characters": [{"name": "Hero", "visual_identity": "Hero face"},
                           {"name": "EndingOnly", "visual_identity": "Secret person"}],
        },
        "scenes": [
            {"text": f"Beginning {i}", "characters": ["Hero"]} for i in range(70)
        ] + [
            {"text": f"FINAL_SPOILER_SCENE_{i}", "characters": ["EndingOnly"]}
            for i in range(30)
        ],
    }


def test_brief_never_supplies_ending_or_ending_only_characters():
    p = project()
    script = "An exciting early story. " * 400 + "FINAL_SPOILER_SCRIPT_END"
    brief = COVERS.cover_brief(p, "project", script)
    details = json.loads(brief)
    assert len(details["early_middle_shots"]) <= 24
    assert all(s["shot"] <= 62 for s in details["early_middle_shots"])
    assert "FINAL_SPOILER" not in brief
    assert "EndingOnly" not in brief
    assert "Hero" in brief


def test_references_only_from_early_middle_project_cast(tmp_path):
    p = project()
    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "Hero.png").write_bytes(b"a")
    (refs / "EndingOnly.png").write_bytes(b"b")
    selected = COVERS.cover_reference_files(p, tmp_path)
    assert selected == [str(refs / "Hero.png")]


def test_design_policy_requires_open_eyes_compelling_images_and_no_spoilers():
    request = COVERS.cover_design_request(COVERS.cover_brief(project(), "story"))
    for rule in ("ลืมตา", "ไม่มีชื่อเรื่อง", "ไม่จืดชืด", "ไม่เว้นที่ว่าง", "ฉากจบ"):
        assert rule in request
    assert "FINAL_SPOILER" not in request


def test_plain_export_has_no_text_overlay(tmp_path):
    source = tmp_path / "image.png"
    output = tmp_path / "cover.jpg"
    Image.new("RGB", (1280, 720), (195, 77, 46)).save(source)
    assert COVERS.save_cover_only(source, output) == output
    with Image.open(output) as actual:
        assert actual.size == (1920, 1080)
        for x, y in ((50, 50), (600, 500), (1850, 950)):
            pixel = actual.getpixel((x, y))
            assert max(abs(a - b) for a, b in zip(pixel, (195, 77, 46))) <= 4


def test_video_pipeline_ends_without_cover_and_cover_has_manual_red_button():
    text = SOURCE.read_text(encoding="utf-8")
    assert '("covers", "สร้างหน้าปก YouTube", 5)' not in text
    assert text.count('("สร้างหน้าปก", lambda: start_covers_only()') == 1
    assert 'bg="#DC2626" if is_cover' in text
    merge = text[text.index("    def render_video_selected("):text.index("    def stage_covers(")]
    assert "stage_covers()" not in merge
    assert "draw_title" not in text


def test_versioned_cover_receipts_protect_old_text_baked_images():
    text = SOURCE.read_text(encoding="utf-8")
    assert 'cover_image_versions' in text
    assert "COVER_RULES_VERSION" in text
    assert "save_cover_only(src, picture)" in text
    assert "cover_{i:02d}_plain_v2" in text
