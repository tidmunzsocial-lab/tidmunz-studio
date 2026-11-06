"""One-page Auto workflow must bind Context and Ref sources before rendering."""

from test_video_auto_scene_provider import N


def test_one_page_auto_exposes_context_and_character_stages_before_audio():
    keys = [key for key, _title, _weight in N.VIDEO_STAGES]
    assert keys[:4] == ["analysis", "context", "ref_characters", "transcribe"]
    assert keys.index("ref_characters") < keys.index("images")
    assert sum(weight for _key, _title, weight in N.VIDEO_STAGES) == 100


def test_story_reference_filter_discards_manual_refs_from_other_story(tmp_path):
    selected = tmp_path / "selected"
    old = tmp_path / "previous"
    selected.mkdir()
    old.mkdir()
    portrait = selected / "hero.png"
    stale = old / "other.png"
    portrait.write_bytes(b"image")
    stale.write_bytes(b"image")
    candidates = [("hero", str(portrait)), ("other", str(stale))]
    assert N.references_from_story_folder(candidates, selected) == [("hero", str(portrait))]
    assert N.references_from_story_folder(candidates, None) == []


def test_legacy_project_progress_stays_on_original_scale(tmp_path):
    project = {"done": {"context": True}, "scenes": []}
    assert N.auto_saved_percent(project, N.VIDEO_STAGES) == 4
    project["auto_progress_version"] = "one_page"
    assert N.auto_saved_percent(project, N.VIDEO_STAGES) == 5
