# -*- coding: utf-8 -*-
"""Five same-story YouTube covers. No API calls happen in this module.

The Auto owner persists each cover's original picture and final text-overlay image.
Only Auto invokes the generator after the actual final video merge succeeds.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


COVER_COUNT = 5
COVER_CONCEPTS = (
    "cinematic dramatic wide establishing shot",
    "strong emotional confrontation with wide visual breathing room",
    "mysterious atmospheric key story event",
    "beautiful richly detailed environment and primary character",
    "high-tension theatrical movie-poster composition",
)


def story_title(project: dict, folder: Path | str = "") -> str:
    script = str(project.get("script") or "").strip()
    title = Path(script.replace("\\", "/")).stem if script else Path(folder).name
    title = re.sub(r"^(?:บท|เสียง|วิดีโอ)\s*[-–:]\s*", "", title, flags=re.I).strip()
    return title or "เรื่องใหม่"


def cover_reference_files(project: dict, project_folder: Path | str, maximum: int = 4) -> list[str]:
    """Use ONLY references already attached to this Auto project, never search other stories."""
    folder = Path(project_folder) / "refs"
    if not folder.is_dir():
        return []
    ledger = {}
    try:
        ledger = json.loads((folder / "_ref_done.json").read_text(encoding="utf-8")).get("items") or {}
    except (OSError, ValueError, AttributeError):
        pass
    appearances = Counter(
        str(name).strip() for shot in (project.get("scenes") or [])
        for name in (shot.get("characters") or [])
        if str(name).strip()
    )
    context_names = [
        str(c.get("name") or "").strip()
        for c in (project.get("context") or {}).get("characters") or []
        if isinstance(c, dict)
    ]
    names = sorted(context_names, key=lambda n: (-appearances[n], context_names.index(n)))
    found = []
    for name in names:
        path = Path(str(ledger.get("character:" + name) or ""))
        if not path.is_file() or path.parent.resolve() != folder.resolve():
            path = next((folder / (re.sub(r'[<>:"/\\|?*]', "_", name) + ext)
                         for ext in (".png", ".jpg", ".jpeg", ".webp")
                         if (folder / (re.sub(r'[<>:"/\\|?*]', "_", name) + ext)).is_file()), None)
        if path is not None and path.is_file() and str(path) not in found:
            found.append(str(path))
        if len(found) >= maximum:
            break
    return found


def cover_brief(project: dict, project_folder: Path | str, script_text: str = "") -> str:
    """Bound project-specific story context without requiring new global prompts."""
    context = project.get("context") or {}
    cast = [
        {k: c.get(k) for k in ("name", "visual_identity", "ใบหน้า", "ทรงผม", "เสื้อผ้า") if c.get(k)}
        for c in (context.get("characters") or []) if isinstance(c, dict)
    ][:24]
    scenes = project.get("scenes") or []
    excerpts = [
        {"shot": i + 1, "scene": str(sc.get("text") or sc.get("prompt") or "")[:340],
         "cast": (sc.get("characters") or [])[:5]}
        for i, sc in enumerate(scenes) if isinstance(sc, dict)
    ]
    if len(excerpts) > 24:
        picks = sorted(set(round(j * (len(excerpts) - 1) / 23) for j in range(24)))
        excerpts = [excerpts[i] for i in picks]
    return json.dumps({
        "title": story_title(project, project_folder),
        "story": context.get("story") or {},
        "visual_rules": context.get("visual_rules") or {},
        "characters": cast,
        "representative_shots": excerpts,
        "script_beginning": script_text[:9500],
        "script_ending": script_text[-3500:] if len(script_text) > 9500 else "",
    }, ensure_ascii=False, default=str)


def cover_design_request(brief: str) -> str:
    return (
        "คุณเป็นผู้กำกับศิลป์โปสเตอร์ภาพยนตร์และ YouTube thumbnail ระดับมืออาชีพ "
        "อ่านข้อมูลของเรื่องนี้จริง ๆ แล้วออกแบบแนวคิดภาพหน้าปก 16:9 จำนวน 5 แบบที่แตกต่างกันอย่างชัดเจน "
        "รักษาใบหน้า อายุ ทรงผม ชุด ยุค สถานที่ และสไตล์ตรงตามเรื่อง; อย่าเพิ่มตัวละครหรือเหตุการณ์ที่ไม่มีในเรื่อง "
        "ให้องค์ประกอบสมจริงแบบภาพยนตร์ รายละเอียดคมสวย ตัวละครกินพื้นที่ไม่เกินประมาณครึ่งเฟรม "
        "วางตัวละครและจุดสนใจหลักไว้ด้านขวา เว้นด้านซ้าย 45% สำหรับใส่ชื่อเรื่องด้วยโปรแกรมทีหลัง "
        "ไม่ให้ AI สร้างข้อความหรือโลโก้ลงภาพ เพราะโปรแกรมจะใส่ชื่อไทยให้ถูกต้องเอง "
        "ห้ามสร้างไฝ ฝี ขี้แมลงวัน หรือรอยตำหนิเพิ่มเองถ้าบท/เรฟไม่ระบุ "
        "ตอบ JSON object เท่านั้น {\"covers\":[{\"concept\":\"\",\"prompt\":\"\"}, ...]} "
        "จำนวน 5 รายการ แต่ละ prompt เป็นคำสั่งภาพถ่ายภาพยนตร์สมจริง 16:9 พร้อมองค์ประกอบชัดเจน.\n"
        + brief
    )


def validate_designs(reply: dict) -> list[str]:
    items = reply.get("covers") if isinstance(reply, dict) else None
    if not isinstance(items, list) or len(items) != COVER_COUNT:
        raise ValueError("GPT ต้องส่งแนวคิดหน้าปกครบ 5 แบบก่อนสร้างภาพ")
    result = []
    for i, item in enumerate(items):
        prompt = str(item.get("prompt") or "").strip() if isinstance(item, dict) else ""
        if len(prompt) < 45:
            raise ValueError(f"แนวคิดปกที่ {i + 1} สั้นเกินไปหรือไม่มีรายละเอียด")
        result.append(prompt[:2200])
    if len(set(result)) != COVER_COUNT:
        raise ValueError("GPT ออกแบบหน้าปกซ้ำกัน ต้องแก้ให้แตกต่างกันก่อนสร้างรูป")
    return result


def draw_title(source: str | Path, output: str | Path, title: str) -> Path:
    """Render Thai title locally and consistently, not via unreliable AI text."""
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    source, output = Path(source), Path(output)
    if not source.is_file() or source.stat().st_size <= 0:
        raise FileNotFoundError(str(source))
    output.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as original:
        image = ImageOps.fit(original.convert("RGB"), (1920, 1080),
                             method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    font_path = next((p for p in (
        Path("C:/Windows/Fonts/tahomabd.ttf"),
        Path("C:/Windows/Fonts/leelawdb.ttf"),
        Path("C:/Windows/Fonts/tahoma.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ) if p.is_file()), None)
    if font_path is None:
        raise RuntimeError("ไม่พบฟอนต์สำหรับพิมพ์ชื่อเรื่องบนปก")
    draw = ImageDraw.Draw(image, "RGBA")
    # Transparent fade prevents dark blocking rectangles from obscuring the film.
    for x in range(0, 1000, 5):
        alpha = round(190 * max(0, (1000 - x) / 1000) ** 1.4)
        draw.rectangle((x, 0, x + 4, 1080), fill=(0, 0, 0, alpha))
    text = " ".join(str(title or "").split()).strip()
    if not text:
        raise ValueError("ชื่อเรื่องสำหรับหน้าปกว่าง")
    size = 126
    rows = []
    while size >= 54:
        font = ImageFont.truetype(str(font_path), size=size)
        # Break Thai by render width, preserving grapheme clusters when practical.
        rows = []
        buffer = ""
        for ch in text:
            proposal = buffer + ch
            if buffer and draw.textbbox((0, 0), proposal, font=font, stroke_width=2)[2] > 780:
                rows.append(buffer)
                buffer = ch
            else:
                buffer = proposal
        if buffer:
            rows.append(buffer)
        if len(rows) <= 3:
            break
        size -= 8
    line_height = int(size * 1.42)
    y = max(140, round((1080 - line_height * len(rows)) / 2))
    for row in rows:
        draw.text((80, y), row, font=font, fill=(255, 255, 255, 255),
                  stroke_width=7, stroke_fill=(12, 17, 27, 255))
        y += line_height
    image.save(output, "JPEG", quality=94, subsampling=0, optimize=True)
    if not output.is_file() or output.stat().st_size < 20_000:
        raise RuntimeError("ไฟล์หน้าปกที่บันทึกมีขนาดผิดปกติ")
    return output
