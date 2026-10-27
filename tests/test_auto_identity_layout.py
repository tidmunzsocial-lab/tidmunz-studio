import ast
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_video_auto_scene_provider import N, TREE, Widget, batch_scope, load


def test_selected_master_and_project_context_are_sent_after_conflicting_prompt(tmp_path):
    scope, paths = batch_scope(tmp_path, 1)
    current, ref = tmp_path / "old.png", tmp_path / "master.png"
    current.write_bytes(b"wrong hair"); ref.write_bytes(b"correct hair")
    scope["state"]["project"]["scenes"][0]["image"] = str(current)
    sent = []
    def generate(prompt, refs, folder, name, aspect, api_context=None):
        sent.append((prompt, refs))
        output = folder / "api-result.png"; output.write_bytes(b"new image"); return str(output)
    scope["generate_via_snapgen"] = generate
    make = load(scope, "make_image")
    record = dict(character="ท้าวก่ำกาดำ", reference=str(ref), context={"name": "ท้าวก่ำกาดำ", "ทรงผม": "ผมสั้น (สมมุติ)"}, notes="ผมเกรียนตามเรฟ")
    result = make("keep old curly hair", [str(ref)], tmp_path, "repair", "9:16", board=str(current), identity_repair=record)
    prompt, refs = sent[0]
    assert refs == [str(current), str(ref)]
    assert "Image 2 is the selected MASTER" in prompt
    assert prompt.index("IDENTITY CORRECTION") > prompt.index("STORYBOARD PANEL")
    assert "ผมเกรียนตามเรฟ" in prompt and "ผมสั้น (สมมุติ)" in prompt and "the master wins" in prompt
    assert Path(result).read_bytes() == b"new image" and current.read_bytes() == b"wrong hair"
    with pytest.raises(N.ImageProviderError, match="ยังไม่ได้แนบเรฟ"):
        make("repair", [], tmp_path, "invalid", "9:16", identity_repair=record)
    assert len(sent) == 1


@pytest.mark.parametrize("outcome", ["success", "failure", "stop"])
def test_repair_only_selected_image_and_invalidate_its_clip_after_success(tmp_path, outcome):
    scope, _ = batch_scope(tmp_path, 2)
    project = scope["state"]["project"]
    for i, scene in enumerate(project["scenes"]):
        image, clip = tmp_path / f"old-{i}.png", tmp_path / f"old-{i}.mp4"
        image.write_bytes(f"image-{i}".encode()); clip.write_bytes(b"old clip")
        scene.update(image=str(image), clip=str(clip), motion_image="old digest", seen="old description")
    before = json.loads(json.dumps(project["scenes"]))
    project["done"] = dict(images=True, motion=True, clips=True, video=True)
    scope["state"]["busy"] = False
    scope.update(start_btn=Widget(), bar=Widget(), stage_var=Widget(), detail_var=Widget(), refresh_all=lambda: None,
                 messagebox=SimpleNamespace(showerror=lambda *a, **kw: pytest.fail("unexpected dialog")),
                 threading=SimpleNamespace(Thread=lambda target, **kw: SimpleNamespace(start=target)))
    calls = []
    def make(prompt, refs, folder, name, aspect, **kwargs):
        calls.append((refs, kwargs))
        if outcome == "failure": raise N.ImageProviderError("provider down")
        if outcome == "stop": raise N.Stopped()
        out = tmp_path / "fixed.png"; out.write_bytes(b"fixed"); return str(out)
    scope["make_image"] = make
    record = dict(character="actor", reference=str(tmp_path / "actor.png"), context={"name": "actor"}, notes="fix hair")
    repair = load(scope, "repair_identity")
    repair(0, record)
    assert not scope["state"]["busy"]
    assert project["scenes"][1] == before[1]
    assert all(Path(scene["image"]).read_bytes() == f"image-{i}".encode() for i, scene in enumerate(before))
    assert calls[0][0] == [record["reference"]] and calls[0][1]["board"] == before[0]["image"]
    assert calls[0][1]["identity_repair"]["context"] == {"name": "actor"}
    if outcome == "success":
        scene = project["scenes"][0]
        assert scene["image"] == str(tmp_path / "fixed.png") and "clip" not in scene and "seen" not in scene
        assert scene["image_history"] == [dict(image=before[0]["image"], clip=before[0]["clip"])]
        assert project["done"] == {"images": True}
        restored = json.loads((tmp_path / "project.json").read_text())
        assert restored["scenes"][0]["identity_repair"] == record
    else:
        assert project["scenes"] == before and project["done"]["video"]
        assert project["identity_repairs_pending"]["0"] == record


def test_explicit_repaired_reference_replaces_old_same_character_attachment(tmp_path):
    old, correct, other = [tmp_path / name for name in ("actor.png", "actor_4k.png", "friend.png")]
    for path in (old, correct, other): path.write_bytes(b"ref")
    scope = dict(vars(N), runtime={"img_match_refs_for_text": lambda text: [("actor", str(old)), ("friend", str(other))]},
                 scene_prompt=lambda scene: "actor friend", attachment_folder=lambda: None)
    attachments = load(scope, "attachments_for")
    scene = dict(characters=["actor", "friend"], identity_repair={"character": "actor", "reference": str(correct)})
    assert attachments(scene, limit=None) == [str(correct), str(other)]


def check_groups(hidden_tk):
    tk, root = hidden_tk
    box = tk.Frame(root); box.pack()
    tools = tk.Frame(box); tools.pack()
    events = []
    scope = dict(vars(N), tk=tk, box=box, table_tools=tools, bg="white", video_mode=True, state={"project": {}})
    names = ["regenerate_selected", "edit_current_selected", "repair_identity_selected", "edit_prompt", "refine_selected",
             "use_scene_image", "remake_clips_selected", "fix_problem_selected", "review_clips_selected",
             "reslow_selected", "start_pipeline", "open_path"]
    for name in names: scope[name] = lambda *a, name=name, **kw: events.append((name, kw))
    node = next(n for n in ast.walk(TREE) if isinstance(n, ast.If) and any(
        isinstance(child, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "action_groups" for t in child.targets)
        for child in n.body))
    exec(compile(ast.Module(body=[node], type_ignores=[]), N.__file__, "exec"), scope)
    root.update_idletasks()
    groups = tools.winfo_children()
    assert [g.cget("text") for g in groups] == ["รูปภาพ", "วิดีโอ"]
    for group in groups:
        buttons = group.winfo_children()
        assert len(buttons) == 6
        assert {(b.grid_info()["row"], b.grid_info()["column"]) for b in buttons} == {(r,c) for r in range(2) for c in range(3)}
        assert group.winfo_reqheight() < 130
    groups[0].winfo_children()[2].invoke(); groups[1].winfo_children()[1].invoke()
    assert [e[0] for e in events] == ["repair_identity_selected", "fix_problem_selected"]
    button = groups[1].winfo_children()[2]
    # Invoke the registered Tk callback without mapping a window on the desktop.
    command = button.bind("<FocusIn>").split("[", 1)[1].split()[0]
    button.tk.call(command, *(button._w if key == "%W" else "0" for key in button._subst_format))
    assert "ไม่ใช่ตรวจหน้าตาตรงเรฟ" in scope["action_hint"].get()


def check_folding(hidden_tk):
    tk, root = hidden_tk
    box = tk.Frame(root); box.pack()
    settings, run = tk.Frame(box), tk.Frame(box)
    settings.pack(); run.pack()
    value = tk.StringVar(value="selected model")
    tk.Entry(settings, textvariable=value).pack()
    button = tk.Button(run)
    scope = dict(settings_parent=settings, run_row=run, settings_open=[True], settings_button=button)
    toggle = load(scope, "toggle_settings")
    toggle(False); assert settings.winfo_manager() == ""
    toggle(True); assert settings.winfo_manager() == "pack" and value.get() == "selected model"
    assert box.pack_slaves() == [settings, run]


@pytest.mark.parametrize("check", ["groups", "folding"])
def test_real_tk_controls_in_isolated_process(check):
    # Keep Tcl interpreters/variables out of the API tests' worker threads.
    result = subprocess.run([sys.executable, "-B", __file__, check], capture_output=True,
                            text=True, errors="replace", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":
    import tkinter as tk
    root = tk.Tk(); root.withdraw()
    try:
        {"groups": check_groups, "folding": check_folding}[sys.argv[1]]((tk, root))
    finally:
        root.destroy()
