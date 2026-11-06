"""Regression: auto Context must recover only same-story missing GPT chat."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
from snapgen_prompt_ref_history_recovery import safe_to_rebuild_context_history as ok


def kwargs():
    return dict(http_status=404, error_message="conversation_not_found — ChatGPT cannot load this chat",
                retry_allowed=True, require_history=True, context_ready=False,
                conversation_id="an-existing-chat-id",
                expected_story_hash="same-story", current_story_hash="same-story")


def test_one_safe_retry_for_missing_unsaved_context_history():
    assert ok(**kwargs())


def test_never_retry_saved_context_or_different_story_or_media_turn():
    for changed in (
        {"context_ready": True},
        {"current_story_hash": "another-story"},
        {"require_history": False},
        {"retry_allowed": False},
        {"conversation_id": ""},
        {"expected_story_hash": ""},
        {"http_status": 429},
        {"error_message": "404 unknown endpoint"},
    ):
        values = kwargs()
        values.update(changed)
        assert not ok(**values), changed


def test_prompt_ref_uses_same_story_retry_guard():
    code = (Path(__file__).resolve().parents[1] / "snapgen_gui_v2.py").read_text(encoding="utf-8")
    assert "safe_to_rebuild_context_history(" in code
    assert "_ingest_prompt_ref_story(candidate_story)" in code
    assert "return _prompt_ref_chat(messages, require_history=True," in code
    assert "_repair_retry=False, model=model" in code
