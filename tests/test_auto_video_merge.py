"""Exercise the merge button with existing paid assets and no generation services."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_video_auto_scene_provider import N, load


class Value:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def config(self, **kwargs):
        pass

    configure = config


class InlineThread:
    def __init__(self, target, **kwargs):
        self.target = target

    def start(self):
        self.target()


def merge_scope(tmp_path):
    images, clips = tmp_path / "images", tmp_path / "clips"
    images.mkdir()
    clips.mkdir()
    scenes = []
    for i in range(2):
        image, clip = images / f"scene_{i + 1:03d}.png", clips / f"clip_{i + 1:03d}.mp4"
        image.write_bytes(b"completed picture")
        clip.write_bytes(b"completed clip")
        scenes.append(dict(start=i * 2, prompt="approved prompt", image=str(image), clip=str(clip),
                           bad="old image review", dialogue="spoken line" if i else "", clip_slow=not i))
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"narration")
    project = dict(scenes=scenes, script="story.txt", audio=str(audio), aspect="9:16", duration=4,
                   style_mode="approved style", image_count=2, images_verified=False,
                   done={k: True for k in ("context", "transcribe", "plan", "images", "motion", "clips")})
    state = dict(project=project, folder=str(tmp_path), busy=False, stop=False)
    logs, commands = [], []

    def forbidden(*args, **kwargs):
        pytest.fail("Merge reached image review, generation, account, or planning setup")

    def run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"merged output")
        return SimpleNamespace(returncode=0, stderr="")

    def save():
        (tmp_path / "project.json").write_text(json.dumps(state["project"]), encoding="utf-8")

    noop = lambda *args, **kwargs: None
    scope = dict(vars(N), state=state, video_mode=True, work_dir_name="วิดีโอออโต้",
                 threading=SimpleNamespace(Thread=InlineThread),
                 subprocess=SimpleNamespace(run=run), save_project=save,
                 ffmpeg_path=lambda: "ffmpeg", video_encoder=lambda _: ("test", ["-c:v", "libx264"]),
                 fitted_clip=lambda scene, length, width, height: (scene["clip"], "scale=90:160"),
                 SIZES={"9:16": (90, 160), "16:9": (160, 90)},
                 log=logs.append, check_stop=noop, set_progress=noop,
                 ui=lambda fn, *args: fn(*args), refresh_table=noop, refresh_all=noop,
                 subtitle_var=Value(False), start_btn=Value(), bar=Value(), stage_var=Value(), detail_var=Value(),
                 page=None, messagebox=SimpleNamespace(askyesno=forbidden, showinfo=forbidden),
                 ask_on_ui=lambda *args: True, verify_images=forbidden,
                 relink_scene_images=forbidden, desired_aspect=forbidden,
                 attachment_folder=forbidden, follow_active_account=forbidden,
                 stage_images=forbidden, stage_clips=forbidden, image_provider_for=forbidden)
    for name in ("relink_or_report_missing_clips", "stage_video", "render_video_selected", "start_pipeline"):
        load(scope, name)
    return scope, logs, commands


def test_merge_uses_existing_clips_without_image_review_even_after_reload(tmp_path):
    scope, logs, commands = merge_scope(tmp_path)
    project = scope["state"]["project"]
    # A missing source picture does not invalidate its already-completed video clip.
    Path(project["scenes"][1]["image"]).unlink()
    original = copy.deepcopy(project["scenes"])
    for _ in range(2):
        scope["start_pipeline"](only="video")
        saved = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
        assert saved["scenes"] == original
        assert saved["aspect"] == "9:16" and saved["style_mode"] == "approved style"
        assert saved["images_verified"] is False
        assert all(saved["done"][k] for k in ("images", "clips", "plan", "video"))
        assert Path(saved["last_video"]).read_bytes() == b"merged output"
        scope["state"]["project"] = saved
    inputs = [command[i + 1] for command in commands for i, arg in enumerate(command[:-1]) if arg == "-i"]
    assert all(scene["clip"] in inputs for scene in original)
    assert all(scene["image"] not in inputs for scene in original)
    assert Path(original[0]["image"]).read_bytes() == b"completed picture"
    assert all(Path(scene["clip"]).read_bytes() == b"completed clip" for scene in original)


def test_missing_clip_reports_shot_and_preserves_images_and_scene_links(tmp_path):
    scope, logs, commands = merge_scope(tmp_path)
    project = scope["state"]["project"]
    Path(project["scenes"][1]["clip"]).unlink()
    original = copy.deepcopy(project["scenes"])
    scope["start_pipeline"](only="video")
    assert "ยังไม่มีคลิปช็อต 2" in scope["detail_var"].get()
    assert not commands
    assert project["scenes"] == original
    assert project["done"]["images"] and project["done"]["clips"]
    assert all(Path(scene["image"]).read_bytes() == b"completed picture" for scene in original)


def test_merge_reuses_unlinked_existing_clip_after_confirmation(tmp_path):
    scope, logs, commands = merge_scope(tmp_path)
    project = scope["state"]["project"]
    clip = project["scenes"][1].pop("clip")
    scope["start_pipeline"](only="video")
    assert project["scenes"][1]["clip"] == clip
    assert project["done"]["video"] and commands


def test_render_failure_keeps_paid_assets_and_previous_output(tmp_path):
    scope, logs, commands = merge_scope(tmp_path)
    project = scope["state"]["project"]
    previous = tmp_path / "previous.mp4"
    previous.write_bytes(b"previous output")
    project["last_video"] = str(previous)
    original = copy.deepcopy(project["scenes"])
    scope["subprocess"].run = lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="encoder failed")
    scope["start_pipeline"](only="video")
    assert "encoder failed" in scope["detail_var"].get()
    assert project["scenes"] == original and project["last_video"] == str(previous)
    assert previous.read_bytes() == b"previous output"
    assert all(Path(scene["image"]).read_bytes() == b"completed picture" for scene in original)
    assert all(Path(scene["clip"]).read_bytes() == b"completed clip" for scene in original)


def test_narration_render_still_uses_its_existing_cache_renderer(tmp_path):
    scope, logs, commands = merge_scope(tmp_path)
    scope["video_mode"] = False
    called = []
    scope["render_narrate_cached"] = lambda *args, **kwargs: called.append(kwargs)
    scope["stage_video"](force=True)
    assert called[0]["force"] is True and not commands
