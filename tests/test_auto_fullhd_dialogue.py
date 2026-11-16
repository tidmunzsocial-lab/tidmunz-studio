"""Lock Auto's 1080p default and block storyboard dialogue omissions before paid video."""
import inspect
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
import snapgen_page_narrate as N


def test_full_hd_is_the_first_choice_and_default_when_starting_auto():
    source = inspect.getsource(N._build)
    assert N.VIDEO_RESOLUTIONS[0] == "1080p"
    assert 'video_res_var = tk.StringVar(value="1080p")' in source
    assert 'project["video_model"], project["video_resolution"] = VIDEO_GROK_LITE_MODEL, "1080p"' in source
    assert 'video_res_var.set(project.get("video_resolution") or "1080p")' in source
    assert 'resolution = (project.get("video_resolution") or "1080p")' in source


def test_exact_scripted_dialogue_speaker_is_required():
    original = N.script_dialogues
    try:
        N.script_dialogues = lambda _: [("มฆมานพ", "เราต้องช่วยชาวบ้าน"), ("เพื่อน", "ข้าจะไปด้วย")]
        right = [
            {"dialogue": "มฆมานพ", "line": "เราต้องช่วยชาวบ้าน", "speech_seconds": 3.0},
            {"dialogue": "เพื่อน", "line": "ข้าจะไปด้วย", "speech_seconds": 2.0},
        ]
        result = N.verify_script_dialogue_coverage("บท", right)
        assert result == {"expected": 2, "matched": 2, "missing": []}
        changed = [right[0], {"dialogue": "มฆมานพ", "line": "ข้าจะไปด้วย"}]
        result = N.verify_script_dialogue_coverage("บท", changed)
        assert result["matched"] == 1
        assert result["missing"][0]["speaker"] == "เพื่อน"
    finally:
        N.script_dialogues = original
