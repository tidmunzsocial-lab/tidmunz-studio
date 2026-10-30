"""Per-story Ref storage, legacy resume, and restart behavior without generation."""
import ast
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
from snapgen_page_ref import ref_story_folder
import snapgen_page_narrate as narrate


TREE = ast.parse((Path(__file__).resolve().parents[1] / "snapgen_modules/snapgen_page_ref.py").read_text(encoding="utf-8-sig"))


def load(ns, name):
    node = next(n for n in ast.walk(TREE) if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), "ref", "exec"), ns)


def scope(tmp_path, title="เจ้าสาวนาคา"):
    ns = dict(Path=Path, json=json, os=os, re=re, shutil=shutil, time=time,
              ref_story_folder=ref_story_folder, g={"EXPORT_REF": tmp_path / "ref"},
              export_ref_dir=tmp_path / "ref", ref_done_path=tmp_path / "meta/ref_done.json",
              ref_gallery_paths=[], _prompt_ref_story_title=lambda: title)
    ns["g"]["get_ref_story_title"] = lambda: title
    for name in ("_ref_done_story", "_ref_output_folder", "_ref_plain_file", "_ref_done_load",
                 "_ref_already_done", "_ref_mark_done", "_ref_image_request"):
        load(ns, name)
    return ns


def test_plain_names_are_separated_by_story_and_old_images_preserved(tmp_path):
    first, second = scope(tmp_path), scope(tmp_path, "หงส์ทอง")
    for ns, content in ((first, b"first"), (second, b"second"), (first, b"revised")):
        source = tmp_path / "download.png"
        source.write_bytes(content)
        output = ns["_ref_plain_file"](source, "ทหาร")
        assert Path(output) == ns["_ref_output_folder"]() / "ทหาร.png"
        assert Path(output).read_bytes() == content
    assert (second["_ref_output_folder"]() / "ทหาร.png").read_bytes() == b"second"
    assert next((first["_ref_output_folder"]() / "_เก่า").glob("*.png")).read_bytes() == b"first"
    # Editing a gallery image from another story keeps its original owner folder.
    source = tmp_path / "edit.png"
    source.write_bytes(b"edited second")
    edited = first["_ref_plain_file"](source, "ทหาร", output_dir=second["_ref_output_folder"]())
    assert Path(edited).parent == second["_ref_output_folder"]()


def test_resume_survives_story_switch_restart_and_reads_matching_legacy_state(tmp_path):
    first = scope(tmp_path)
    legacy_image = tmp_path / "legacy.png"
    legacy_image.write_bytes(b"paid image")
    legacy = first["ref_done_path"]
    legacy.parent.mkdir()
    legacy.write_text(json.dumps({"story": "เจ้าสาวนาคา", "items": {"character:ทหาร": str(legacy_image)}}, ensure_ascii=False), encoding="utf-8")
    assert first["_ref_already_done"]("character", "ทหาร")
    first["_ref_mark_done"]("location", "วัง", legacy_image)
    second = scope(tmp_path, "หงส์ทอง")
    assert second["_ref_done_load"]() == {}
    second["_ref_mark_done"]("character", "หงส์ทอง", legacy_image)
    restarted = scope(tmp_path)
    assert restarted["_ref_already_done"]("character", "ทหาร")
    assert restarted["_ref_already_done"]("location", "วัง")
    assert "character:หงส์ทอง" not in restarted["_ref_done_load"]()


def test_web_generation_receives_story_directory_and_safe_paths(tmp_path):
    ns = scope(tmp_path)
    calls = []
    ns["g"]["_do_image_request"] = lambda *args, **kwargs: calls.append(kwargs) or "result.png"
    assert ns["_ref_image_request"]({"provider": "gpt_web"}, "prompt", "ทหาร", [], {}) == "result.png"
    assert Path(calls[0]["output_dir"]) == tmp_path / "ref/เจ้าสาวนาคา"
    assert Path(calls[0]["output_dir"]).is_dir()
    assert ref_story_folder(tmp_path, "CON").name == "_CON"
    assert ref_story_folder(tmp_path, "../../เรื่อง:ใหม่").parent == tmp_path
    assert ref_story_folder(tmp_path, "") == tmp_path


def test_api_generation_saves_inside_story_folder_and_keeps_reference_matching(tmp_path, monkeypatch):
    ns = scope(tmp_path)
    calls = []

    def generate(prompt, refs, output_dir, name, aspect, key, **kwargs):
        calls.append((refs, output_dir))
        scratch = Path(output_dir)
        scratch.mkdir(parents=True)
        image = scratch / "ref.png"
        image.write_bytes(b"api image")
        return str(image)

    monkeypatch.setattr(narrate, "snapgen_image", generate)
    ns.update(ref_billing={}, _ref_log=lambda *args: None)
    out = ns["_ref_image_request"]({"provider": "snapgen", "acceptance": None, "api_key": "test"},
                                    "prompt", "ทหาร", [], {})
    assert Path(out).parent == ns["_ref_output_folder"]()
    final = ns["_ref_plain_file"](out, "ทหาร")
    assert narrate.character_ref_files(Path(final).parent, ["ทหาร"]) == [("ทหาร", final)]
    assert len(calls) == 1


def test_shared_open_folder_button_follows_ref_story_directory(tmp_path):
    ns = scope(tmp_path)
    tree = ast.parse((Path(__file__).resolve().parents[1] / "snapgen_gui_v2.py").read_text(encoding="utf-8-sig"))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_snapgen_current_export_folder")
    ns["g"].update(current_mode="ref", ref_folder=ns["_ref_output_folder"])
    ns.update({key: tmp_path for key in ("EXPORT_VIDEO", "EXPORT_IMAGE", "EXPORT_REF", "EXPORT_PROP",
                                        "EXPORT_STORY_FACE", "EXPORT_KARAOKE", "EXPORT_AUDIO", "EXPORT_ROOT")})
    exec(compile(ast.Module(body=[node], type_ignores=[]), "gui", "exec"), ns)
    assert ns["_snapgen_current_export_folder"]() == tmp_path / "ref/เจ้าสาวนาคา"
