# -*- coding: utf-8 -*-
"""Optional same-story image-only covers, with no text and no end-of-story spoilers."""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path


COVER_COUNT = 5
COVER_RULES_VERSION = "plain_no_text_eyes_open_no_spoilers_v2"
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


def early_middle_scenes(project: dict, fraction: float = 0.62) -> list[dict]:
    """Never use the final 38% of the scene list for cover imagery."""
    scenes = [x for x in (project.get("scenes") or []) if isinstance(x, dict)]
    return scenes[:math.ceil(len(scenes) * fraction)]


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
        str(name).strip() for shot in early_middle_scenes(project)
        for name in (shot.get("characters") or [])
        if str(name).strip()
    )
    context_names = [
        str(c.get("name") or "").strip()
        for c in (project.get("context") or {}).get("characters") or []
        if isinstance(c, dict)
    ]
    names = sorted((n for n in context_names if appearances[n] > 0),
                   key=lambda n: (-appearances[n], context_names.index(n)))
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
    """Show GPT only early-middle events, never the ending or final synopsis."""
    context = project.get("context") or {}
    scenes = early_middle_scenes(project)
    names = {str(n).strip() for shot in scenes for n in shot.get("characters") or []}
    cast = [
        {k: c.get(k) for k in ("name", "visual_identity", "ใบหน้า", "ทรงผม", "เสื้อผ้า") if c.get(k)}
        for c in (context.get("characters") or [])
        if isinstance(c, dict) and str(c.get("name") or "").strip() in names
    ][:24]
    excerpts = [
        {"shot": i + 1, "scene": str(sc.get("text") or sc.get("prompt") or "")[:340],
         "cast": (sc.get("characters") or [])[:5]}
        for i, sc in enumerate(scenes)
    ]
    if len(excerpts) > 24:
        picks = sorted(set(round(j * (len(excerpts) - 1) / 23) for j in range(24)))
        excerpts = [excerpts[i] for i in picks]
    safe_script = script_text[:min(9500, math.ceil(len(script_text) * 0.62))]
    return json.dumps({
        "title": story_title(project, project_folder),
        "visual_rules": context.get("visual_rules") or {},
        "characters": cast,
        "early_middle_shots": excerpts,
        "early_middle_script": safe_script,
        "no_ending_or_spoilers": True,
    }, ensure_ascii=False, default=str)


def cover_design_request(brief: str) -> str:
    return (
        "ออกแบบภาพหน้าปกเปล่าสมจริงระดับโปสเตอร์ภาพยนตร์ 16:9 จำนวน 5 แบบที่แตกต่างกัน "
        "เลือกเฉพาะเหตุการณ์ช่วงต้นหรือกลางเรื่องจากข้อมูลที่ให้มา อย่าสร้างเหตุการณ์ใหม่ "
        "ห้ามฉากจบ ฉากเฉลย ผลลัพธ์สุดท้าย ชะตากรรมสุดท้าย และภาพท้ายเรื่องทุกชนิด "
        "ตัวละครทุกคนต้องลืมตาทั้งสองข้าง มองเห็นดวงตาและอารมณ์บนใบหน้าชัดเจน "
        "ห้ามหลับตา กะพริบตา หรือมีอะไรมาบังตา "
        "เน้นภาพสวยตื่นตา กระตุ้นความอยากรู้ สี แสง เงา อารมณ์แรงมีมิติแบบหนัง "
        "องค์ประกอบเต็มเฟรม ไม่จืดชืด ไม่เว้นที่ว่างให้ตัวหนังสือ "
        "ไม่มีชื่อเรื่อง ข้อความ ตัวอักษร โลโก้ ลายน้ำ ป้าย หรือคำโปรยใดๆ "
        "คงหน้าตา ชุด และยุคให้ตรงภาพเรฟและเรื่อง ไม่แต่งตัวละครหรือรายละเอียดเพิ่ม "
        "ห้ามไฝ ฝี รอยตำหนิใหม่ถ้าเรฟไม่มี "
        "ตอบ JSON เท่านั้น {\"covers\":[{\"concept\":\"\",\"prompt\":\"\"}, ...]} "
        "จำนวน 5 รายการ พร้อมพรอมป์แต่ละภาพและมุมกล้อง\n"
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


def save_cover_only(source: str | Path, output: str | Path) -> Path:
    """Create the plain 1920x1080 image; never draw text or overlays."""
    from PIL import Image, ImageOps

    source, output = Path(source), Path(output)
    if not source.is_file() or source.stat().st_size <= 0:
        raise FileNotFoundError(str(source))
    output.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as original:
        oriented = ImageOps.exif_transpose(original)
        image = ImageOps.fit(oriented.convert("RGB"), (1920, 1080),
                             method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        image.save(output, "JPEG", quality=94, subsampling=0, optimize=True)
    if not output.is_file() or output.stat().st_size < 20_000:
        raise RuntimeError("ไฟล์หน้าปกมีขนาดผิดปกติ")
    return output
