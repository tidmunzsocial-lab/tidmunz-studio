"""Auto keeps completed frames; only deterministic source/file failures can trigger bounded repair."""
import json
from pathlib import Path

import pytest
from PIL import Image

from test_video_auto_scene_provider import N, load


def frame(path, color, compress_level=6):
    Image.new("RGB", (160, 90), color).save(path, compress_level=compress_level)
    return str(path)


def verify_scope(tmp_path, scenes, regenerate):
    project = {"scenes": scenes, "aspect": "16:9"}
    saved = tmp_path / "project.json"

    def save():
        saved.write_text(json.dumps(project), encoding="utf-8")

    def forbidden(*_):
        pytest.fail("Auto must not regenerate from subjective GPT continuity criticism")

    scope = dict(vars(N), state={"project": project, "folder": tmp_path}, video_mode=True,
                 check_stop=lambda: None, set_progress=lambda *_: None,
                 gpt_image_problems=forbidden, stage_images=regenerate,
                 save_project=save, ui=lambda fn: fn(), refresh_table=lambda: None,
                 save_storyboard=lambda *_: None, log=lambda *_: None)
    return scope, project, load(scope, "verify_images", parent="_build")


def test_auto_valid_completed_frames_survive_subjective_old_warnings(tmp_path):
    scenes = [{"image": frame(tmp_path / "scene_001.png", "blue"), "bad": "outfit differs from earlier shot"}]
    original = Path(scenes[0]["image"]).read_bytes()
    scope, project, verify = verify_scope(tmp_path, scenes, lambda *_: pytest.fail("must not regenerate"))
    verify()
    assert project["images_verified"] is True and "bad" not in scenes[0]
    assert Path(scenes[0]["image"]).read_bytes() == original


def test_reencoded_board_is_rejected_by_pixels_not_subjective_content(tmp_path):
    board = frame(tmp_path / "board.png", "red", 0)
    scene = frame(tmp_path / "scene_001.png", "red", 9)
    assert Path(board).read_bytes() != Path(scene).read_bytes()
    problems = N.local_image_problems([{"image": scene, "board": board}], "16:9")
    assert 0 in problems and "สตอรี่บอร์ด" in problems[0]


def test_true_source_replay_gets_repaired_with_original_archived(tmp_path):
    board = frame(tmp_path / "board.png", "red")
    image = frame(tmp_path / "scene_001.png", "red")
    original = Path(image).read_bytes()
    scenes = [{"image": image, "board": board, "prompt": "scene"}]
    calls = []

    def regenerate(indices):
        calls.append(indices)
        assert Path(image).read_bytes() == original  # Still available until replacement succeeds.
        assert list((tmp_path / "_replaced").glob("*.png"))
        frame(Path(image), "blue")

    _, project, verify = verify_scope(tmp_path, scenes, regenerate)
    verify()
    assert calls == [[0]] and project["images_verified"] is True
    assert scenes[0]["auto_image_repair_count"] == 1
    assert next((tmp_path / "_replaced").glob("*.png")).read_bytes() == original


def test_failed_repairs_keep_files_and_budget_survives_project_reload(tmp_path):
    scenes = [{"image": frame(tmp_path / "scene_001.png", "blue"), "prompt": "first"},
              {"image": frame(tmp_path / "scene_002.png", "blue"), "prompt": "second"}]
    original = Path(scenes[1]["image"]).read_bytes()
    calls = []
    scope, project, verify = verify_scope(tmp_path, scenes, lambda indices: calls.append(indices))
    with pytest.raises(RuntimeError, match="3"):
        verify()
    assert calls == [[1]] * 3 and Path(scenes[1]["image"]).read_bytes() == original
    restored = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    scope["state"]["project"] = restored
    with pytest.raises(RuntimeError):
        verify()
    assert calls == [[1]] * 3 and restored["scenes"][1]["auto_image_repair_count"] == 3
    assert Path(scenes[1]["image"]).is_file()


def test_reference_matching_ignores_characters_mentioned_only_in_global_style(tmp_path):
    matched = []
    scope = dict(vars(N), runtime={"img_match_refs_for_text": lambda text: matched.append(text) or []},
                 scene_prompt=lambda scene: scene["prompt"] + " era: princesses and ทหาร",
                 attachment_folder=lambda: tmp_path)
    attachments = load(scope, "attachments_for", parent="_build")
    assert attachments({"prompt": "empty seaside", "characters": [], "location": "beach"}) == []
    assert len(matched) == 1 and "ทหาร" not in matched[0]
    assert "empty seaside" in matched[0] and "beach" in matched[0]
