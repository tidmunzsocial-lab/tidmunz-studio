# -*- coding: utf-8 -*-
"""Zero-credit regression checks for optional plain-cover art and story isolation."""
import json
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from snapgen_modules.snapgen_auto_covers import (
    COVER_COUNT, story_title, cover_reference_files, cover_brief,
    cover_design_request, validate_designs, save_cover_only,
)


class AutoCoverTests(unittest.TestCase):
    def test_title_and_five_distinct_prompts(self):
        p = {"script": r"G:\\Story\\บท - มฆมานพ.docx", "context": {
            "story": {"era": "human period"},
            "characters": [{"name": "มฆมานพ", "visual_identity": "มนุษย์ชายหน้ารูปไข่"}]
        }, "scenes": [{"text": "ชายเดินในหมู่บ้าน", "characters": ["มฆมานพ"]}]}
        self.assertEqual(story_title(p), "มฆมานพ")
        brief = cover_brief(p, "project", "ตอนเริ่มต้นเป็นมนุษย์")
        self.assertIn("มฆมานพ", brief)
        self.assertIn("มนุษย์ชาย", brief)
        self.assertIn("ตอนเริ่มต้น", brief)
        self.assertIn("ไม่เว้นที่ว่าง", cover_design_request(brief))
        designs = [{"prompt": f"Photorealistic historical Thai film thumbnail concept {i}. "
                               "Cast in the right half of the frame, historical clothing, cinematic."}
                   for i in range(COVER_COUNT)]
        prompts = validate_designs({"covers": designs})
        self.assertEqual(len(prompts), 5)
        with self.assertRaisesRegex(ValueError, "5 แบบ"):
            validate_designs({"covers": designs[:4]})
        with self.assertRaisesRegex(ValueError, "ซ้ำกัน"):
            validate_designs({"covers": [designs[0]] * 5})

    def test_refs_restricted_to_selected_auto_project(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            own = root / "auto" / "refs"
            other = root / "other_story" / "refs"
            own.mkdir(parents=True)
            other.mkdir(parents=True)
            (own / "มฆมานพ.png").write_bytes(b"own-ref")
            (other / "ท้าวสักกะ.png").write_bytes(b"other-story")
            (own / "_ref_done.json").write_text(json.dumps({"items": {
                "character:มฆมานพ": str(own / "มฆมานพ.png"),
                "character:ท้าวสักกะ": str(other / "ท้าวสักกะ.png"),
            }}, ensure_ascii=False), encoding="utf-8")
            project = {"context": {"characters": [
                {"name": "มฆมานพ"}, {"name": "ท้าวสักกะ"}
            ]}, "scenes": [{"characters": ["มฆมานพ"]}]}
            self.assertEqual(cover_reference_files(project, root / "auto"), [str(own / "มฆมานพ.png")])
            self.assertEqual(cover_reference_files(project, root / "other_empty"), [])

    def test_render_plain_cover_16x9_with_no_paid_api(self):
        with tempfile.TemporaryDirectory() as t:
            src = Path(t) / "source.png"
            dst = Path(t) / "final.jpg"
            Image.new("RGB", (1024, 576), (72, 83, 95)).save(src)
            save_cover_only(src, dst)
            self.assertGreater(dst.stat().st_size, 20_000)
            with Image.open(dst) as im:
                self.assertEqual(im.size, (1920, 1080))
                self.assertEqual(im.format, "JPEG")
                # Plain solid-color source cannot gain text or an overlay.
                for pt in ((50, 50), (960, 540), (1870, 1030)):
                    self.assertLess(max(abs(a-b) for a,b in zip(im.getpixel(pt), (72,83,95))), 5)


if __name__ == "__main__":
    unittest.main()
