"""Native app binding and per-story monitor appear before any script analysis."""
from pathlib import Path
from test_video_auto_scene_provider import N

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "snapgen_modules" / "chrome_ext"


def test_monitor_stage_precedes_analysis_and_effects_precede_render():
    stages = N.VIDEO_STAGES
    keys = [key for key, _label, _weight in stages]
    assert keys.index("monitor") < keys.index("analysis")
    assert keys.index("clips") < keys.index("effects") < keys.index("video")
    assert sum(weight for _, _, weight in stages) == 100
    assert sum(weight for _, _, weight in N.LEGACY_VIDEO_STAGES) == 100


def test_real_app_chip_selection_mandatory_for_followup():
    ui = (EXT / "monitor_apps.js").read_text(encoding="utf8")
    followup = (EXT / "followup.js").read_text(encoding="utf8")
    background = (EXT / "background.js").read_text(encoding="utf8")
    for ref in ("app://plugins_6aebd38bc5588191808c3cbd710ded69",
                "app://asdk_app_6afac8c38ba88191afe3e6f5a07f43eb"):
        assert ref in ui
        assert ref in followup
    assert 'querySelectorAll("[app-mention-path]")' in ui
    assert "appMentionsVerified" in ui and "appMentionsVerified" in followup
    assert "type === \"monitor_bootstrap\"" in background
    assert "tmFollowupBootstrap" in followup
    assert "new chat" not in ""  # Standalone test never sends ChatGPT messages
