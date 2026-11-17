"""Retrospective monitor bootstrap runs once without restarting existing films."""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
import snapgen_page_narrate as N

STAGES = ["monitor", "analysis", "context", "characters", "plan",
          "storyboard", "images", "motion", "clips", "effects", "video"]


def test_partially_produced_legacy_film_gets_monitor_first_once(tmp_path):
    clip = tmp_path / "scene_074.mp4"
    clip.write_bytes(b"existing paid clip")
    project = {"scenes": [{"clip": str(clip)}],
               "done": {"analysis": True, "context": True, "images": True}}
    original_done = dict(project["done"])
    keys = N.auto_resume_keys_with_monitor(project, STAGES)
    assert keys == STAGES
    assert N.auto_monitor_bootstrap_needed(project)
    # Preparing the next run neither invalidates past stages nor touches clips.
    assert project["done"] == original_done
    assert clip.read_bytes() == b"existing paid clip"


def test_completed_monitor_is_not_run_again_with_a_targeted_resume():
    project = {"done": {"monitor": True, "analysis": True, "images": True},
               "monitor_chat": {"url": "https://chatgpt.com/c/abc", "cid": "abc",
                                "host": "DESKTOP-EXAMPLE", "story": "Story",
                                "project_key": "key"}}
    assert not N.auto_monitor_bootstrap_needed(project)
    assert N.auto_resume_keys_with_monitor(project, ["clips"]) == ["clips"]
    assert N.auto_resume_keys_with_monitor(project, STAGES) == STAGES


def test_missing_monitor_in_specific_stage_is_prepended_not_rebuilt(tmp_path):
    project = {"done": {"analysis": True, "context": True, "images": True},
               "scenes": [{"clip": str(tmp_path / "existing.mp4")}]}
    assert N.auto_resume_keys_with_monitor(project, ["clips"]) == ["monitor", "clips"]
    assert N.auto_resume_keys_with_monitor(project, ["video"]) == ["monitor", "video"]
    assert N.auto_resume_keys_with_monitor(project, ["monitor"]) == ["monitor"]


def test_untrusted_done_flag_without_chat_binding_recovers_once():
    project = {"done": {"monitor": True, "analysis": True}, "monitor_chat": {}}
    assert N.auto_monitor_bootstrap_needed(project)
    assert N.auto_resume_keys_with_monitor(project, ["clips"]) == ["monitor", "clips"]
    project["monitor_chat"] = {"url": "https://chatgpt.com/c/abc", "cid": "abc",
                               "host": "DESKTOP-EXAMPLE", "story": "Story",
                               "project_key": "key"}
    assert not N.auto_monitor_bootstrap_needed(project)


def test_new_film_runs_monitor_before_any_processing():
    assert N.auto_resume_keys_with_monitor({"scenes": [], "done": {}}, ["analysis"]) == [
        "monitor", "analysis"]


def test_nonvideo_mode_is_not_changed():
    project = {"done": {}, "monitor_chat": {}}
    assert N.auto_resume_keys_with_monitor(project, ["clips"], video_mode=False) == ["clips"]
    assert not N.auto_monitor_bootstrap_needed(project, video_mode=False)


def test_resume_executes_only_new_monitor_and_skips_saved_stages():
    source = inspect.getsource(N._build)
    assert "keys = auto_resume_keys_with_monitor(project, keys, video_mode)" in source
    assert 'callable(STAGE_FUNCS.get("monitor"))' in source
    assert 'project.setdefault("done", {}).pop("monitor", None)' in source
    assert 'if project["done"].get(key) and key != "video":' in source
    assert "if key not in keys" not in source
    assert "keys = [key for key in keys if key != \"monitor\"]" not in source
    assert "stage_monitor_chat()" in source


def test_confirmed_bootstrap_arms_existing_extension_without_new_watcher():
    extension = (Path(__file__).resolve().parents[1] /
                 "snapgen_modules/chrome_ext/followup.js").read_text(encoding="utf-8")
    assert 'self.tmFollowupBootstrap=async function(job)' in extension
    assert 'await chrome.alarms.create(ALARM,{periodInMinutes:1})' in extension
    assert "c.enabled=true;c.stopRequested=false;" in extension