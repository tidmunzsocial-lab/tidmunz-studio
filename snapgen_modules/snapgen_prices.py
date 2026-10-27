"""Today's video prices in SnapGen credits, read from the public price list the website itself uses.

`https://api.snapgen.ai/api/service-prices` needs no login and already gives credits
(`currency: credit`), so the numbers match the Studio page ("This generation will cost: 7 Credits").
The last good answer is kept in a cache file: with no internet the program still shows the last prices and says so.
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

URL = "https://api.snapgen.ai/api/service-prices"

# (program model id) -> (label, price-list name, resolutions the program can ask for, durations)
MODELS = {
    "grok-1.5-lite": ("Grok Lite", "grok-1.5-lite", ("720p", "1080p", "480p"), (6, 10, 15)),
    "grok-lower": ("Grok Lower", "grok-lower", ("720p", "1080p", "480p"), (6, 10, 15)),
    "sd-2-lower": ("Seedance 2.0 Lower", "sd-2-lower_lower", ("720p",), (5, 10, 15)),
    "sd-2-5-lower": ("Seedance 2.5 Lower", "sd-2-5-lower_lower", ("720p",), (5, 10, 30)),
    "muse-ai-video": ("Muse AI", "muse-ai-video", (None,), (10,)),
}


def fetch(cache_path, timeout: float = 12.0) -> dict:
    """{"rows": [...], "at": epoch seconds, "stale": bool}. Falls back to the cache when the site is unreachable."""
    cache = Path(cache_path)
    try:
        request = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 TidmunzStudio"})
        rows = json.loads(urllib.request.urlopen(request, timeout=timeout).read().decode("utf-8"))
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty price list")
        data = {"rows": rows, "at": time.time(), "stale": False}
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"rows": rows, "at": data["at"]}), encoding="utf-8")
        except OSError:
            pass
        return data
    except Exception:
        try:
            saved = json.loads(cache.read_text(encoding="utf-8"))
            return {"rows": saved.get("rows") or [], "at": saved.get("at") or 0, "stale": True}
        except (OSError, ValueError):
            return {"rows": [], "at": 0, "stale": True}


def cost(rows: list, model: str, resolution: str | None, seconds: int) -> float | None:
    """Credits for one clip of `seconds` s, or None when the price list has no such entry."""
    label, name, _res, _dur = MODELS.get(model, (None, model, (), ()))
    best = None
    for row in rows:
        if row.get("model_name") != name:
            continue
        if resolution and row.get("resolution") not in (None, resolution):
            continue
        if row.get("video_duration") not in (None, seconds) and row.get("price_unit") != "second":
            continue
        price = row.get("effective_price")
        if price is None:
            continue
        price = float(price) * (seconds if row.get("price_unit") == "second" else 1)
        best = price if best is None else min(best, price)
    return best


def options(rows: list, model: str) -> tuple:
    """(resolutions, durations) the price list offers for a program model id, in order; () when it lists none."""
    _label, name, _res, fallback = MODELS.get(model, (None, model, (), ()))
    resolutions, durations = [], []
    for row in rows:
        if row.get("model_name") != name:
            continue
        resolution, duration = row.get("resolution"), row.get("video_duration")
        if resolution and resolution not in resolutions:
            resolutions.append(resolution)
        if duration and int(duration) not in durations:
            durations.append(int(duration))
    order = {"480p": 0, "720p": 1, "1080p": 2}
    resolutions.sort(key=lambda r: order.get(r, 9))
    return tuple(resolutions), tuple(sorted(durations)) or tuple(fallback)


def table(rows: list, seconds: int) -> list:
    """[(credits, label, model id, resolution)] for every model/resolution the program can use, cheapest first."""
    out = []
    for model, (label, _name, resolutions, durations) in MODELS.items():
        length = seconds if seconds in durations else min(durations, key=lambda d: abs(d - seconds))
        for resolution in resolutions:
            credits = cost(rows, model, resolution, length)
            if credits is None:
                continue
            name = label + (f" {resolution}" if resolution else "")
            if length != seconds:
                name += f" ({length} วิ)"
            out.append((credits, name, model, resolution))
    return sorted(out, key=lambda item: item[0])


def summary(rows: list, seconds: int, model: str, resolution: str | None, stale: bool = False, at: float = 0) -> str:
    """One line for the page: what today's cheapest are, and what the current choice costs."""
    options = table(rows, seconds)
    if not options:
        return "ราคาวันนี้: ดึงไม่ได้ (ตรวจอินเทอร์เน็ต) — ดูราคาจริงที่หน้า Studio ของ SnapGen"
    shown = [f"{name} = {credits:g}" for credits, name, _m, _r in options[:5]]
    mine = cost(rows, model, resolution, seconds)
    here = (f" · ที่เลือกอยู่ = {mine:g} เครดิต" + (" (ถูกสุดแล้ว)" if mine is not None and mine <= options[0][0] else "")
            if mine is not None else "")
    old = ""
    if stale:
        old = " · ราคาเก่า" + (time.strftime(" (%d/%m %H:%M)", time.localtime(at)) if at else "")
    return f"ราคาวันนี้ ต่อคลิป {seconds} วินาที (เครดิต): " + " · ".join(shown) + here + old
