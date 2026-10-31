"""Planning, UI persistence, and clip routing must agree on the chosen model."""
import json
import threading

from test_auto_video_merge import Value
from test_video_auto_scene_provider import N, load


def test_planner_uses_selected_model_and_routes_only_confirmed_empty_views_to_muse():
    requests = []

    def ask(prompt):
        requests.append(prompt)
        if "คุณคือผู้กำกับ" in prompt:
            return {"sequences": [{"shots": [1, 2, 3]}]}
        return {"scenes": [
            {"shot": 1, "prompt": "king", "characters": ["king"], "shot_type": "character", "has_people": True},
            {"shot": 2, "prompt": "empty sea", "characters": [], "shot_type": "scenery", "has_people": False},
            {"shot": 3, "prompt": "city crowd", "characters": [], "shot_type": "scenery", "has_people": True},
        ]}

    segments = [{"start": i * 10, "end": (i + 1) * 10, "text": str(i)} for i in range(3)]
    scenes = N.plan_video(segments, 30, ["king"], "", ask, clip_choice=10, video_model=N.VIDEO_GROK_LITE_MODEL)
    assert [s["clip_model"] for s in scenes] == [N.VIDEO_GROK_LITE_MODEL, N.VIDEO_MUSE_MODEL, N.VIDEO_GROK_LITE_MODEL]
    assert all(s["clip_seconds"] == 10 and not s["clip_slow"] for s in scenes)
    assert any("Grok Lite" in request and "10" in request for request in requests)


def test_dialogue_unknown_people_and_completed_paid_clips_are_protected(tmp_path):
    clip = tmp_path / "paid.mp4"
    clip.write_bytes(b"paid video")
    scenes = [
        {"start": 0, "dialogue": "king", "slow": True, "shot_type": "scenery", "has_people": False},
        {"start": 10, "shot_type": "scenery"},
        {"start": 20, "shot_type": "scenery", "has_people": False, "characters": ["snake"]},
        {"start": 30, "clip": str(clip), "clip_model": "original", "clip_seconds": 15, "clip_slow": True},
    ]
    N.assign_clips(scenes, 40, True, 10, N.VIDEO_GROK_LITE_MODEL, scenery_muse=True)
    assert all(s["clip_model"] == N.VIDEO_GROK_LITE_MODEL for s in scenes[:3])
    assert scenes[0]["clip_seconds"] == 10 and scenes[0]["clip_slow"] is False
    assert (scenes[3]["clip_model"], scenes[3]["clip_seconds"], scenes[3]["clip_slow"]) == ("original", 15, True)
    long_line = [{"start": 0, "dialogue": "king", "slow": True}]
    N.assign_clips(long_line, 14, True, 10, N.VIDEO_GROK_LITE_MODEL, scenery_muse=True)
    assert long_line[0]["clip_seconds"] == 15 and not long_line[0]["clip_slow"]


def test_ui_model_duration_save_and_restart_reapply_the_same_policy(tmp_path):
    noop = lambda *args, **kwargs: None
    project = {"duration": 20, "video_model": N.VIDEO_GROK_LOWER_MODEL, "clip_choice": 6,
               "scenes": [{"start": 0}, {"start": 10, "shot_type": "scenery", "has_people": False}], "done": {"plan": True}}
    ns = dict(vars(N), state={"project": project, "folder": str(tmp_path), "lock": threading.RLock()},
              video_mode=True, page=None, toggle_settings=noop, refresh_table=noop, refresh_all=noop,
              refresh_clip_info=noop, refresh_snapgen_credit_warning=noop, update_price_line=noop,
              clip_labels={"map": dict(N.CLIP_CHOICE_LABELS)}, last_project_file=lambda: tmp_path / "last.txt",
              last_style=lambda: "ปกติ", prices={"data": {"stale": False, "rows": [
                  {"model_name": N.VIDEO_MUSE_MODEL, "video_duration": 10, "effective_price": 1}]}})
    for name in ("video_model_var", "clip_choice_var", "video_res_var", "economy_var", "image_provider_var",
                 "script_var", "audio_var", "aspect_var", "count_var", "subtitle_var", "film_var", "style_var"):
        ns[name] = Value()
    for name in ("project_path", "save_project", "apply_selected_video_model", "video_model_changed", "clip_choice_changed", "show_project"):
        load(ns, name)
    ns["video_model_var"].set(N.VIDEO_MODEL_LABELS[N.VIDEO_GROK_LITE_MODEL])
    ns["video_model_changed"]()
    ns["clip_choice_var"].set(N.CLIP_CHOICE_LABELS[10])
    ns["clip_choice_changed"]()
    saved = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    assert saved["video_model"] == N.VIDEO_GROK_LITE_MODEL and saved["clip_choice"] == 10
    assert [s["clip_model"] for s in saved["scenes"]] == [N.VIDEO_GROK_LITE_MODEL, N.VIDEO_MUSE_MODEL]
    # Reproduce an old saved plan mislabeled Lower while its owner setting is Lite.
    saved["scenes"][0]["clip_model"] = N.VIDEO_GROK_LOWER_MODEL
    ns["show_project"](tmp_path, saved)
    reloaded = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    assert reloaded["scenes"][0]["clip_model"] == N.VIDEO_GROK_LITE_MODEL
    assert ns["video_model_var"].get() == N.VIDEO_MODEL_LABELS[N.VIDEO_GROK_LITE_MODEL]
    assert reloaded["done"] == {"plan": True}
    # A later first-frame check detects people in a previously empty planned view.
    reloaded["scenes"][1]["has_people"] = True
    ns["apply_selected_video_model"](reloaded)
    assert reloaded["scenes"][1]["clip_model"] == N.VIDEO_GROK_LITE_MODEL


def test_scenery_muse_never_exceeds_accepted_live_price():
    import snapgen_muse_video as muse
    assert "ฟรี" not in muse.LABEL and "ฟรี" not in N.VIDEO_MUSE_LABEL
    row = {"model_name": N.VIDEO_MUSE_MODEL, "video_duration": 10, "effective_price": 1}
    assert N.muse_scenery_price_allowed({"rows": [row], "stale": False})
    assert not N.muse_scenery_price_allowed({"rows": [dict(row, effective_price=2)], "stale": False})
    assert not N.muse_scenery_price_allowed({"rows": [row], "stale": True})
    assert not N.muse_scenery_price_allowed(None)
