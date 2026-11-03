"""Changed input must not inherit another story's Context/chat or adopt old scene files."""
import json
import zipfile
from pathlib import Path

import pytest
from test_video_auto_scene_provider import N, load
import snapgen_shared_context as shared


def test_word_blank_paragraphs_match_prompt_ref_hash_without_accepting_other_story(tmp_path):
    story = tmp_path / "story.docx"
    xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           '<w:body><w:p><w:r><w:t>นาคา</w:t></w:r></w:p><w:p/>'
           '<w:p><w:r><w:t>ช่วยชาวบ้าน</w:t></w:r></w:p></w:body></w:document>')
    with zipfile.ZipFile(story, 'w') as archive:
        archive.writestr('word/document.xml', xml)
    data = {'path': str(tmp_path / 'story.tidmunz-context.json'), 'source_name': story.name,
            'story_sha256': shared.story_hash('นาคา\n\nช่วยชาวบ้าน')}
    assert N.context_matches_script(data, story, N.read_script(story))
    assert not N.context_matches_script(data, story, 'อีกเรื่องหนึ่ง')
    data['story_sha256'] = shared.story_hash('บทอื่น')
    assert not N.context_matches_script(data, story, N.read_script(story))


def payload(folder, name, text, title, characters=None, saved="2026-11-02 12:00:00"):
    source = folder / (name + ".txt")
    source.write_text(text, encoding="utf-8")
    data = {"format": shared.FORMAT, "version": 1, "source_name": source.name,
            "story_sha256": shared.story_hash(text), "saved_at": saved,
            "context": {"story": {"title": title}, "characters": characters or [{"name": title}], "locations": []}}
    path = shared.sidecar_path(source)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return source, shared.load(source)


def test_identity_repair_offers_project_characters_when_shot_has_only_a_location():
    context = {"characters": [{"name": "พระราชา"}, {"name": "มเหสี"}]}
    contexts, names, matched = N.identity_repair_context_options(
        {"characters": ["ท้องพระโรง"]}, context)
    assert names == ["พระราชา", "มเหสี"] and not matched
    assert contexts["พระราชา"] == {"name": "พระราชา"}
    assert N.identity_repair_context_options({"characters": ["มเหสี"]}, context)[1:] == (["มเหสี"], True)


def test_selected_story_sidecar_wins_without_searching_for_old_copies(tmp_path, monkeypatch):
    story, expected = payload(tmp_path, "selected", "นาคาพบชาวบ้าน", "นาคา")
    monkeypatch.setattr(shared.Path, "home", lambda: pytest.fail("must not replace the selected sidecar with a global copy"))
    assert shared.find(story) == expected
    assert shared.find(story, story_text="คนละเรื่อง") is None


def test_fallback_uses_newest_matching_copy_not_oldest(tmp_path, monkeypatch):
    home = tmp_path / "home"
    for name in ["Downloads", "Desktop", "Documents"]:
        (home / name).mkdir(parents=True)
    _, old = payload(home / "Downloads", "selected", "นาคา", "นาคา", saved="2026-01-01")
    _, new = payload(home / "Desktop", "selected", "นาคา", "นาคา", saved="2026-11-02")
    payload(home / "Documents", "selected", "หงส์ทอง", "หงส์ทอง", saved="2026-12-01")
    monkeypatch.setattr(shared.Path, "home", lambda: home)
    exists = Path.exists
    monkeypatch.setattr(shared.Path, "exists", lambda p: False if str(p).rstrip('\\/').upper() in [d+":" for d in "DEFGH"] else exists(p))
    assert shared.find(tmp_path / "selected.txt", story_text="นาคา")["path"] == new["path"]


def test_other_story_and_overwritten_same_filename_are_rejected(tmp_path):
    story, old = payload(tmp_path, "story", "หงส์ทองเดินป่า", "หงส์ทอง")
    story.write_text("นาคาช่วยชาวบ้าน", encoding="utf-8")
    assert not N.context_matches_script(old, story, story.read_text(encoding="utf-8"))


def test_part_can_use_verified_full_story_context(tmp_path):
    source, data = payload(tmp_path, "full", "นาคาพบชาวบ้าน แล้วกลับลงทะเล", "นาคา")
    part = tmp_path / "part.txt"
    part.write_text("แล้วกลับลงทะเล", encoding="utf-8")
    assert N.context_matches_script(data, part, part.read_text(encoding="utf-8"))
    assert not N.context_matches_script(data, part, "หงส์ทองเข้าวัง")


def test_attachment_context_skips_first_wrong_story(tmp_path):
    refs = tmp_path / "refs"
    refs.mkdir()
    payload(refs, "a_old", "หงส์ทองเข้าวัง", "หงส์ทอง")
    story, expected = payload(refs, "z_current", "นาคาช่วยชาวบ้าน", "นาคา")
    scope = dict(vars(N), state={"project": {"script": str(story)}}, attachment_folder=lambda: refs)
    resolve = load(scope, "context_beside_attachments", parent="_build")
    assert resolve()["path"] == expected["path"]


def test_new_context_rebinds_before_cached_done_and_survives_restart_without_media_loss(tmp_path):
    story, data = payload(tmp_path, "story", "นาคาช่วยชาวบ้าน", "นาคา")
    image = tmp_path / "finished.png"
    image.write_bytes(b"keep existing frame")
    project = {"script": str(story), "context": {"story": {"title": "หงส์ทอง"}},
               "done": {"context": True, "plan": True, "images": True, "clips": True, "motion": True},
               "conversation": {"conversation_id": "old-story"}, "image_chat": {"conversation_id": "old-images"},
               "history_seeded": True, "bodies": {"หงส์ทอง": {}},
               "scenes": [{"image": str(image), "prompt": "นาคาช่วยชาวบ้าน", "characters": ["หงส์ทอง"], "motion_image": "old"}]}
    scope = dict(vars(N), state={"project": project}, current_team_context=lambda: data,
                 attachment_folder=lambda: tmp_path, save_project=lambda: None, log=lambda *_: None)
    load(scope, "sync_auto_context", parent="_build")()
    assert project["context"] == data["context"] and project["conversation"] == {}
    assert project["image_chat"] == {} and not project["history_seeded"] and "bodies" not in project
    assert project["done"]["images"] and project["done"]["clips"] and project["done"]["plan"]
    assert "context" not in project["done"] and "motion" not in project["done"]
    assert project["scenes"][0]["characters"] == ["นาคา"]
    assert image.read_bytes() == b"keep existing frame"
    # After the Context stage seeds the new chat, reopening the same source keeps that chat.
    project["done"]["context"] = True
    project["conversation"] = {"conversation_id": "current-story"}
    saved = tmp_path / "project.json"
    saved.write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
    restored = json.loads(saved.read_text(encoding="utf-8"))
    assert not N.bind_auto_context(restored, data, N.read_script(story), str(tmp_path))
    assert restored["conversation"]["conversation_id"] == "current-story" and restored["done"]["context"]


def test_new_plan_does_not_relink_old_frames_merely_by_number(tmp_path):
    from PIL import Image
    images = tmp_path / "images"
    images.mkdir()
    old = images / "scene_001.png"
    Image.new("RGB", (160, 90), "blue").save(old)
    project = {"scenes": [{"prompt": "new plan"}], "relink_unassigned_images": False}
    assert N.relink_scene_images(project, tmp_path) == []
    assert not project["scenes"][0].get("image") and old.is_file()


def test_changed_audio_invalidates_all_timing_derived_stages_but_keeps_files(tmp_path):
    image = tmp_path / "finished.png"
    image.write_bytes(b"keep")
    keys = ["context", "transcribe", "plan", "storyboard", "images", "motion", "clips", "video"]
    project = {"audio": "previous.wav", "done": dict.fromkeys(keys, True), "scenes": [{"image": str(image)}]}
    class Value:
        def set(self, value): pass
    scope = dict(vars(N), state={"project": project, "busy": False}, page=None,
                 media_duration=lambda _: 10, save_project=lambda: None, audio_var=Value(), video_mode=True,
                 refresh_clip_info=lambda: None, desired_count=lambda: 2, slot_settings=lambda: ("model", 10, "16:9"),
                 log=lambda *_: None)
    load(scope, "choose_audio", parent="_build")(str(tmp_path / "new.wav"))
    assert project["done"] == {"context": True} and project["scenes"] == []
    assert project["relink_unassigned_images"] is False and image.read_bytes() == b"keep"
