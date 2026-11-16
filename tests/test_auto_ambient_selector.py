"""The final Video Auto soundtrack uses only confirmed numbered SFX selections."""
from pathlib import Path
import sys
import wave
import tkinter as tk
import pytest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "snapgen_modules"))
sys.path.insert(0, str(BASE / "vendor"))


def test_clip_numbers_and_source_dialogue_override():
    from snapgen_ambient_selector import (
        DEFAULT_SELECTED_CLIPS, normalized_selection, suggested_status,
    )
    assert normalized_selection(DEFAULT_SELECTED_CLIPS, 31) == [2, 5, 9, 14, 17, 22, 26, 31]
    assert normalized_selection([1, 1, 0, 6, 33, -2], 6) == [1, 6]
    assert suggested_status({"dialogue": "hero"}, {"reason": "included"}) == "speech"
    assert suggested_status({}, {"reason": "voice_detected"}) == "speech"
    assert suggested_status({}, {"reason": "speech_vad_detected"}) == "speech"
    assert suggested_status({}, {"reason": "included"}) == "effect"
    assert suggested_status({}, {"reason": "no_audio"}) == "unknown"
    assert suggested_status({}, {"reason": "classifier_unavailable"}) == "unknown"


def test_scan_uses_classifier_and_preserves_dialogue(monkeypatch):
    import snapgen_audio_sfx
    import snapgen_ambient_selector as picker

    scenes = [{"dialogue": "person speaking", "clip": "1.mp4"},
              {"dialogue": "", "clip": "2.mp4"},
              {"dialogue": "", "clip": "3.mp4"}]
    monkeypatch.setattr(snapgen_audio_sfx, "_load", lambda: object())
    found = [("included", "speech"), ("included", "effect"), ("almost_silent", "unknown")]
    calls = []
    def fake_analyze(scene, *_args, **kwargs):
        assert kwargs["preview_only"] is True
        calls.append(scene["clip"])
        return {"reason": found[len(calls)-1][0]}
    monkeypatch.setattr(snapgen_audio_sfx, "_analyze_one", fake_analyze)
    progress = []
    assert picker.scan_effect_statuses(
        "ffmpeg", scenes, [10,10,10], progress=lambda *a: progress.append(a)
    ) == [x[1] for x in found]
    assert calls == ["1.mp4","2.mp4","3.mp4"]
    assert progress[-1] == (3,3)


def test_scan_fails_closed_if_ai_unavailable(monkeypatch):
    import snapgen_audio_sfx
    from snapgen_ambient_selector import scan_effect_statuses
    def raise_error():
        raise RuntimeError("audio models unavailable")
    monkeypatch.setattr(snapgen_audio_sfx, "_load", raise_error)
    assert scan_effect_statuses("ffmpeg", [{"dialogue":"A"},{"dialogue":""}], [10,10]) == ["speech","unknown"]


def test_effect_mixer_only_uses_checked_clips(monkeypatch, tmp_path):
    np = pytest.importorskip("numpy")
    import snapgen_audio_sfx as sfx

    scenes = [{"clip": f"{i}.mp4", "start": float(i)} for i in range(3)]
    calls = []
    monkeypatch.setattr(sfx, "_load", lambda: object())
    sample = np.full((48000,2), 400, dtype=np.int16)
    def fake_analyze(scene, *_args):
        calls.append(scene["clip"])
        return {"reason":"included","signal":sample}
    monkeypatch.setattr(sfx, "_analyze_one", fake_analyze)
    result, audit = sfx.build_effect_track(
        "ffmpeg", scenes, [1,1,1], 3, tmp_path, selected_scene_numbers=[2],
    )
    assert calls == ["1.mp4"]
    assert audit["included"] == 1
    assert audit["rejected"]["not_selected"] == 2
    with wave.open(str(result), "rb") as out:
        assert out.getnframes() == 3*48000
        samples = np.frombuffer(out.readframes(out.getnframes()), dtype=np.int16).reshape(-1,2)
        assert not np.any(samples[:48000])
        assert np.all(samples[48000:96000] == 400)
        assert not np.any(samples[96000:])

    calls.clear()
    none_result, audit = sfx.build_effect_track(
        "ffmpeg", scenes, [1,1,1], 3, tmp_path, selected_scene_numbers=[],
    )
    assert none_result is None and not calls and audit["included"] == 0


def test_compact_selector_has_eight_columns_and_short_legend():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No graphical window manager")
    try:
        root.withdraw()
        from snapgen_ambient_selector import show_selector
        observed = {}
        def confirm():
            dialog = next(c for c in root.winfo_children() if isinstance(c, tk.Toplevel))
            widgets = []
            def children(node):
                for c in node.winfo_children():
                    widgets.append(c)
                    children(c)
            children(dialog)
            checks = [w for w in widgets if isinstance(w, tk.Checkbutton)]
            assert len(checks) == 32
            assert [int(w.grid_info()["column"]) for w in checks[:16]] == list(range(8))*2
            text = [w.cget("text") for w in widgets if isinstance(w, tk.Label)]
            assert "เขียว = เอฟเฟกต์  ·  แดง = บทพูด  ·  เทา = ไม่พบเสียง" in text
            assert "เป็นเพียงการคาดเดาของโปรแกรมเท่านั้น" in text
            assert checks[1].cget("bg") == "#ECF8EF"
            assert checks[2].cget("bg") == "#FFF0F0"
            assert checks[0].cget("bg") == "#F3F4F6"
            observed["n"] = len(checks)
            button = next(w for w in widgets if isinstance(w, tk.Button)
                          and w.cget("text") == "ยืนยันและรวมวิดีโอ")
            button.invoke()
        root.after(150, confirm)
        statuses = (["unknown","effect","speech"] + ["unknown"]*29)
        result = show_selector(root, [{}]*32, statuses)
        assert observed["n"] == 32
        assert result == [2,5,9,14,17,22,26,31]
    finally:
        root.destroy()
