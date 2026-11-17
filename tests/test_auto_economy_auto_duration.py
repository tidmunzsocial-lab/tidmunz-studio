"""Economy must never silently become fixed 10 seconds or spend twice."""
import inspect
import json
from pathlib import Path

from test_video_auto_scene_provider import N


def test_fresh_economy_is_an_automatic_duration_plan():
    assert N.economy_auto_clip_choice({"economy": True, "clip_choice": 10}) == 0
    assert N.economy_auto_clip_choice({"clip_choice": 10}) == 0
    assert N.economy_auto_clip_choice({"economy": False, "clip_choice": 10}) == 10
    assert N.economy_auto_clip_choice({"economy": False, "clip_choice": 0}) == 0


def test_legacy_unselected_10s_default_is_migrated_without_touching_plan():
    p = {"clip_choice": 10, "planned_clip_choice": 10, "done": {"plan": True},
         "scenes": [{"start": 0, "image": "already-created.jpg"}]}
    original_plan = p["planned_clip_choice"]
    assert N.migrate_legacy_economy_default(p)
    assert p["clip_choice"] == 0
    assert p["planned_clip_choice"] == original_plan
    assert p["done"] == {"plan": True}
    assert p["scenes"][0]["image"] == "already-created.jpg"
    assert not N.migrate_legacy_economy_default(p)


def test_manual_fixed_10s_is_not_silently_migrated():
    p = {"clip_choice": 10, "clip_choice_explicit": True,
         "economy": False, "planned_clip_choice": 10}
    assert not N.migrate_legacy_economy_default(p)
    assert N.economy_auto_clip_choice(p) == 10


def test_paid_72_clips_remain_identical_and_missing_clips_switch_to_economy(tmp_path):
    scenes = []
    for i in range(114):
        sc = {"start": i * 8.0, "clip_model": N.VIDEO_GROK_LITE_MODEL,
              "clip_seconds": 10, "clip_slow": False, "slow": False}
        if i < 72:
            file = tmp_path / f"clip_{i + 1:03d}.mp4"
            file.write_bytes(f"paid-asset-{i}".encode())
            sc["clip"] = str(file)
        elif i == 72:
            sc["dialogue"] = "spoken dialogue must remain normal speed"
        scenes.append(sc)
    original_files = [(sc["clip"], Path(sc["clip"]).read_bytes()) for sc in scenes[:72]]
    project = {"economy": True, "clip_choice": 10, "scenes": scenes,
               "done": {"plan": True, "images": True}, "planned_clip_choice": 10}
    assert N.migrate_legacy_economy_default(project)
    N.assign_clips(project["scenes"], 114 * 8, True,
                   N.economy_auto_clip_choice(project), N.VIDEO_GROK_LITE_MODEL)
    assert all(s["clip_seconds"] == 10 and s["clip_slow"] is False for s in scenes[:72])
    assert [(sc["clip"], Path(sc["clip"]).read_bytes()) for sc in scenes[:72]] == original_files
    assert scenes[72]["clip_slow"] is False
    assert scenes[72]["clip_seconds"] == 10
    assert all(sc["clip_seconds"] == 6 and sc["clip_slow"] is True for sc in scenes[73:])
    assert project["done"] == {"plan": True, "images": True}


def test_new_project_ui_uses_auto_and_existing_plan_does_not_force_replan():
    source = inspect.getsource(N._build)
    assert "tk.StringVar(value=CLIP_CHOICE_LABELS[0])" in source
    assert 'project["clip_choice"] = 0' in source
    assert 'clip_choice=economy_auto_clip_choice(project)' in source
    assert "not economy_on() and economy_auto_clip_choice(project)" in source
    assert 'if migrate_legacy_economy_default(project):' in source
    assert 'project["economy"] = False' in source

def test_6s_and_10s_provider_clips_are_slowed_when_economy_is_enabled():
    # A six-second shot never buys a full-speed 10-second clip.
    assert N.pick_clip(5.5, True, False) == (N.VIDEO_AUTO_MODEL, 6, True)
    # 6 seconds of provider credit covers narration up to about 12 seconds.
    assert N.pick_clip(11, True, False) == (N.VIDEO_AUTO_MODEL, 6, True)
    # Longer narration requires 10 seconds of paid video -> about 20 seconds played.
    assert N.pick_clip(18, True, False) == (N.VIDEO_AUTO_MODEL, 10, True)
    # Dialogue: never slow; its paid duration follows the spoken line.
    assert N.pick_clip(5.5, False, False) == (N.VIDEO_AUTO_MODEL, 6, False)
    assert N.pick_clip(9.5, False, False) == (N.VIDEO_AUTO_MODEL, 10, False)


def test_model_locked_to_grok_lite_still_uses_slow_two_x_except_dialogue():
    shots = [
        {"start": 0, "slow": False, "dialogue": ""},
        {"start": 12, "slow": False, "dialogue": ""},
        {"start": 29, "slow": True, "dialogue": "spoken text"},
    ]
    N.assign_clips(shots, 35, True, N.economy_auto_clip_choice(
        {"economy": True, "clip_choice": 10}), N.VIDEO_GROK_LITE_MODEL)
    assert [(x["clip_seconds"], x["clip_slow"]) for x in shots] == [
        (6, True), (10, True), (6, False)]
    assert all(x["slow"] for x in shots[:2])
    assert not shots[2]["clip_slow"]


def test_pending_paid_uuid_is_never_replanned_into_a_second_provider_duration():
    scenes = [
        {"start": 0, "clip_uuid": "already-accepted-paid-job",
         "clip_model": N.VIDEO_GROK_LITE_MODEL, "clip_seconds": 10,
         "clip_slow": False, "slow": False},
        {"start": 10, "clip_model": N.VIDEO_GROK_LITE_MODEL, "clip_seconds": 10,
         "clip_slow": False},
    ]
    N.assign_clips(scenes, 20, True, 0, N.VIDEO_GROK_LITE_MODEL)
    assert scenes[0]["clip_uuid"] == "already-accepted-paid-job"
    assert scenes[0]["clip_seconds"] == 10 and scenes[0]["clip_slow"] is False
    assert scenes[1]["clip_seconds"] == 6 and scenes[1]["clip_slow"] is True