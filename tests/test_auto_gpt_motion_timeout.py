"""A timed-out GPT motion prompt falls back to saved prompts without resubmitting."""
import pytest


def test_auto_video_preview_never_renders_during_shot_edits():
    import ast
    import pathlib
    source = pathlib.Path(__file__).parents[1] / "snapgen_modules" / "snapgen_page_narrate.py"
    node = next(n for n in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
                if isinstance(n, ast.FunctionDef) and n.name == "update_preview")
    scope = {"video_mode": True}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), "preview", "exec"), scope)
    assert scope["update_preview"]() is None

from test_video_auto_scene_provider import N, load


def motion_scope(tmp_path):
    image = tmp_path / "first.png"
    image.write_bytes(b"first-frame")
    scenes = [{"image": str(image), "video_prompt": f"planned-{i}"} for i in range(3)]
    calls, logs, questions = [], [], []
    noop = lambda *args, **kwargs: None
    scope = dict(
        vars(N),
        state={"project": {"scenes": scenes, "duration": 60}, "lock": N.threading.RLock()},
        video_mode=True,
        file_digest=lambda _path: "current-image-digest",
        check_stop=noop,
        ensure_story_in_history=noop,
        ensure_continuity=noop,
        ensure_bodies=noop,
        assign_clips=noop,
        economy_on=lambda: False,
        apply_selected_video_model=noop,
        set_progress=noop,
        motion_request=lambda *args: "request",
        motion_items=lambda batch: batch,
        image_data_url=lambda _path: "image",
        save_project=noop,
        ui=lambda fn, *args: fn(*args),
        refresh_table=noop,
        log=logs.append,
        error_cause=lambda error: str(error),
        runtime={},
        g={},
        ask_on_ui=lambda *args: questions.append(args) or pytest.fail("timeout fallback should be automatic"),
        MOTION_BATCH=1,
    )

    def chat(content):
        calls.append(content)
        raise RuntimeError("Chrome did not finish the ChatGPT job in time (is Chrome open?)")

    scope["chat"] = chat
    load(scope, "with_retries", "_build")
    load(scope, "use_planned_motion", "_build")
    stage_motion = load(scope, "stage_motion", "_build")
    return scope, scenes, calls, logs, questions, stage_motion


def test_sent_gpt_timeout_is_terminal_and_not_retried(tmp_path):
    scope, _scenes, calls, _logs, _questions, _stage = motion_scope(tmp_path)

    with pytest.raises(RuntimeError, match="did not finish the ChatGPT job in time"):
        scope["with_retries"](
            "video prompt", lambda: scope["chat"]("same sent request"), attempts=3
        )

    assert calls == ["same sent request"]


def test_saved_motion_prompts_skip_gpt_without_fabricating_review(tmp_path):
    scope, scenes, calls, logs, questions, stage_motion = motion_scope(tmp_path)
    original_prompts = [scene["video_prompt"] for scene in scenes]

    stage_motion()

    assert not calls
    assert scope["state"]["motion_planned_only"] is True
    assert scope["state"]["motion_text_only"] is True
    assert [scene["video_prompt"] for scene in scenes] == original_prompts
    assert not any("motion_image" in scene or "seen" in scene for scene in scenes)
    assert not questions
    assert logs


def test_motion_timeout_without_saved_prompts_stops_without_text_only_resubmit(tmp_path):
    scope, scenes, calls, _logs, _questions, stage_motion = motion_scope(tmp_path)
    scenes[2].pop("video_prompt")

    with pytest.raises(RuntimeError, match="did not finish the ChatGPT job in time"):
        stage_motion()

    assert len(calls) == 1
    assert not scope["state"].get("motion_planned_only")
    assert not scope["state"].get("motion_text_only")
