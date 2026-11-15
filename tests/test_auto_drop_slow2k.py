"""Auto's standalone drag/drop Topaz utility is independent of its pipeline."""
from pathlib import Path
import sys
import tkinter as tk
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "snapgen_modules"))
sys.path.insert(0, str(ROOT / "vendor"))


def test_topaz_drop_uses_strict_model_and_2k(monkeypatch, tmp_path):
    import ai_slow2x as slow
    source = tmp_path / "shot.mp4"
    source.write_bytes(b"test")
    monkeypatch.setattr(slow, "_topaz_dirs", lambda: ("topaz_ffmpeg", "models"))
    monkeypatch.setattr(slow, "_video_dimensions", lambda *args: (1920, 1080))
    monkeypatch.setattr(slow, "_probe_video", lambda *args: (24.0, True))
    calls = []
    def run(inp, out, factor, fps, has_audio, say, **kwargs):
        calls.append((factor, kwargs.get("target_size"), str(out)))
        return str(out)
    monkeypatch.setattr(slow, "_topaz_slow", run)
    first = slow.make_topaz_slow2x_2k(source)
    assert Path(first).name == "shot_2K.mp4"
    assert Path(first).parent == source.parent
    assert calls[0][:2] == (2, (2048, 1152))
    monkeypatch.setattr(slow, "_video_dimensions", lambda *args: (1080, 1920))
    slow.make_topaz_slow2x_2k(source)
    assert calls[1][:2] == (2, (1152, 2048))
    Path(first).touch()
    second = slow.make_topaz_slow2x_2k(source)
    assert second != first
    assert Path(second).name == "shot_2K_2.mp4"
    assert Path(source).read_bytes() == b"test"
    with pytest.raises(ValueError):
        slow.make_topaz_slow2x_2k(source, output_video=source)


def test_topaz_drop_rejects_missing_topaz(monkeypatch, tmp_path):
    import ai_slow2x as slow
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    monkeypatch.setattr(slow, "_topaz_dirs", lambda: None)
    with pytest.raises(RuntimeError, match="Topaz"):
        slow.make_topaz_slow2x_2k(source)


def test_auto_drop_card_is_visible_and_drag_enabled():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No display")
    try:
        parent = tk.Frame(root)
        parent.pack(fill="x")
        from snapgen_auto_drop_slow import install
        card = install(parent, root)
        root.update()
        assert card.winfo_ismapped()
        assert any("ลากวิดีโอเพื่อสโลว์" in str(x.cget("text"))
                   for x in card.winfo_children() if isinstance(x, tk.Label))
        assert any(isinstance(x, tk.Button) for x in card.winfo_children())
        assert card.winfo_width() == 320
        assert root.tk.call("package", "present", "tkdnd")
    finally:
        root.destroy()
