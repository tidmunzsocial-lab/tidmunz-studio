"""Remote Narration page: controller actions and the mobile UI contract (no paid work)."""
from __future__ import annotations

import sys
from pathlib import Path
from html.parser import HTMLParser

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "snapgen_modules"))
from snapgen_mobile_controller import MobileController


class _HTMLIDs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.tabs = set()

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if "id" in data:
            self.ids.add(data["id"])
        if data.get("data-tab") is not None:
            self.tabs.add(data["data-tab"])


def _controller():
    target = object.__new__(MobileController)
    invoked = []
    target.g = {
        "mobile_image_actions": {},
        "mobile_narrate": {
            "snapshot": lambda: {
                "title": "เจอผีที่สุพรรณฯ",
                "busy": False, "stories": ["เจอผีที่สุพรรณฯ"],
                "log": "พร้อม", "video": "", "shots": [
                    {"n": 1, "image": "", "text": "ฉากแรก", "error": ""},
                ],
            },
            "open": lambda name: invoked.append(("open", name)) or "opened",
            "start": lambda confirmed=False: invoked.append(("start", confirmed)) or "started",
            "stop": lambda: invoked.append(("stop",)) or "stopped",
        },
    }
    target.register_media = lambda path: {"id": "media", "url": "/media/media"} if path else None
    return target, invoked


def test_narrate_actions_do_not_fall_into_auto():
    target, actions = _controller()
    assert target.execute({"action": "narrate_open", "data": {"name": "เจอผีที่สุพรรณฯ"}}) == "opened"
    assert target.execute({"action": "narrate_start", "data": {}}) == "started"
    assert target.execute({"action": "narrate_start", "data": {"confirm_paid": True}}) == "started"
    assert target.execute({"action": "narrate_stop", "data": {}}) == "stopped"
    assert actions == [
        ("open", "เจอผีที่สุพรรณฯ"), ("start", False), ("start", True), ("stop",)
    ]
    with pytest.raises(ValueError, match="เล่าภาพ"):
        target.execute({"action": "narrate_unknown", "data": {}})
    with pytest.raises(ValueError, match="ออโต้"):
        target.execute({"action": "auto_open", "data": {"name": "เจอผีที่สุพรรณฯ"}})


def test_narrate_snapshot_converts_media_and_keeps_mode_isolated():
    target, _ = _controller()
    data = target._narrate_snapshot()
    assert data["title"] == "เจอผีที่สุพรรณฯ"
    assert data["shots"][0]["n"] == 1
    assert data["video"] is None
    target.g["mobile_narrate"]["snapshot"] = lambda: {
        "log": "", "video": "existing.mp4", "shots": [{"image": "existing.png", "n": 1}],
    }
    data = target._narrate_snapshot()
    assert data["video"]["id"] == "media"
    assert data["shots"][0]["image"]["url"] == "/media/media"
    target.g.pop("mobile_narrate")
    assert target._narrate_snapshot() is None


def test_tab_and_controls_are_present_in_web_ui():
    parser = _HTMLIDs()
    parser.feed((ROOT / "snapgen_modules/mobile/index.html").read_text(encoding="utf-8"))
    assert "narrate" in parser.tabs
    assert {"narrate-page", "narrate-story", "narrate-stage", "narrate-log", "narrate-bar",
            "narrate-title", "narrate-detail", "narrate-shots", "narrate-video"} <= parser.ids
    js = (ROOT / "snapgen_modules/mobile/app.js").read_text(encoding="utf-8")
    for action in ("narrate_open", "narrate_start", "narrate_stop"):
        assert action in js
    assert "if(!window.confirm(" in js
    assert "renderNarrate()" in js


def test_tk_page_has_distinct_narrate_adapter_and_rejects_unconfirmed_work():
    source = (ROOT / "snapgen_modules/snapgen_page_narrate.py").read_text(encoding="utf-8")
    assert 'runtime["mobile_narrate"]' in source
    assert "if confirmed is not True:" in source
    assert 'state["auto_yes"] = True' in source
    assert 'def narrate_mobile_stop():' in source
    assert 'folder.parent != base' in source
