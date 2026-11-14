"""Single native editing choice with lossless original audio; no external production renderer."""
from pathlib import Path
import ast

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"snapgen_modules"/"snapgen_page_narrate.py"
AUDIO=ROOT/"snapgen_modules"/"snapgen_audio_sfx.py"

def _native_video_body():
    src=SCRIPT.read_text(encoding="utf-8")
    start=src.index("    def stage_video(force=False):")
    end=src.index("    def update_preview():",start)
    return src[start:end]

def test_no_audio_mode_dialog():
    body=_native_video_body()
    assert "askyesnocancel" not in body
    assert "เลือกรูปแบบตัดต่อ" not in body
    assert "mixed.wav" not in body
    assert "clip_ambience_selected" not in body
    assert 'project["clip_ambience"] = False' in body

def test_native_audio_alac_and_verified_effects():
    body=_native_video_body()
    for token in ("build_effect_track(","lossless_audio_args(","verify_original_pcm(",
                  'project["audio_source_unmodified"] = True',
                  'project["audio_output_codec"] = "ALAC lossless 48000Hz stereo"'):
        assert token in body
    assert '"-b:a", "192k"' not in body
    assert 'project["clip_audio_policy"] = "lossless_narration_and_classifier_verified_sfx_only"' in body
    assert "save_project()" in body

def test_audio_module_export_contract():
    source=AUDIO.read_text(encoding="utf-8")
    ast.parse(source)
    assert all(('def '+name+'(') in source for name in
               ("build_effect_track","lossless_audio_args","verify_original_pcm"))
    assert 'return None, {"included":0' in source

def test_scene_speech_is_visual_not_audio_mixing():
    body=_native_video_body()
    assert 'with_video_audio(' not in body
    assert 'verify_original_pcm(' in body
