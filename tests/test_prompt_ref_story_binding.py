"""Changing the source file must not send a second story into an old chat."""
import ast
import copy
import hashlib
import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest


TREE = ast.parse((Path(__file__).resolve().parents[1] / "snapgen_gui_v2.py").read_text(encoding="utf-8-sig"))


def scope():
    ns = {"hashlib": hashlib}
    for name in ("_prompt_ref_story_hash", "_prompt_ref_cursor_ready", "_check_prompt_ref_context_story",
                 "_ingest_and_build_prompt_ref_context", "_attach_docx_and_build_prompt_ref_context"):
        node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name)
        exec(compile(ast.Module(body=[node], type_ignores=[]), "prompt_ref", "exec"), ns)
    ns["_prompt_ref_conversation"] = dict(conversation_id="original", parent_message_id="parent",
                                          account_alias="owner", story_hash=ns["_prompt_ref_story_hash"]("old story"))
    return ns


@pytest.mark.parametrize("builder", ["_ingest_and_build_prompt_ref_context", "_attach_docx_and_build_prompt_ref_context"])
def test_different_story_stops_before_upload_and_preserves_cursor(builder):
    ns = scope()
    before = copy.deepcopy(ns["_prompt_ref_conversation"])
    args = ("new story",) if builder.startswith("_ingest") else ("never-open.docx", "new story")
    with pytest.raises(RuntimeError, match="บทหลักที่เลือกไม่ตรง"):
        ns[builder](*args)
    assert ns["_prompt_ref_conversation"] == before


def test_same_story_normalization_and_explicit_new_history_are_allowed():
    ns = scope()
    ns["_check_prompt_ref_context_story"](" old story\r\n")
    ns["_prompt_ref_conversation"] = {}
    ns["_check_prompt_ref_context_story"]("new story")


@pytest.mark.parametrize("pending,story_hash,required,retries", [
    (True, "", False, 2), (False, "", False, 1),
    (True, "completed", False, 1), (True, "", True, 1)])
def test_only_explicit_incomplete_new_story_recovers_from_404(monkeypatch, pending, story_hash, required, retries):
    ns = scope()
    node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "_prompt_ref_chat")
    exec(compile(ast.Module(body=[node], type_ignores=[]), "prompt_ref", "exec"), ns)
    ns["_prompt_ref_conversation"].update(new_story_requested=pending, story_hash=story_hash)
    requests = []

    def post(request, **kwargs):
        requests.append(json.loads(request.data))
        if len(requests) == 1:
            body = b'{"error":{"code":"chatgpt_conversation_not_found","message":"conversation_not_found"}}'
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(body))
        return io.BytesIO(json.dumps({"conversation_id": "fresh", "parent_message_id": "reply",
                                     "choices": [{"message": {"content": "FILE_READY"}}]}).encode())

    ns.update(json=json, _chatgpt_api_base=lambda: "http://localhost/v1",
              _save_prompt_ref_conversation=lambda: None,
              _reset_prompt_ref_conversation=lambda: ns["_prompt_ref_conversation"].clear(),
              _extract_bridge_cursor=lambda data: (data["conversation_id"], data["parent_message_id"]),
              Path=Path, __builtins__=__builtins__)
    import os
    ns["os"] = os
    monkeypatch.setattr(urllib.request, "urlopen", post)
    if retries == 2:
        assert ns["_prompt_ref_chat"]([{"role": "user", "content": "story"}], require_history=required) == "FILE_READY"
        assert "metadata" not in requests[1]
        assert ns["_prompt_ref_conversation"]["conversation_id"] == "fresh"
    else:
        with pytest.raises(RuntimeError, match="conversation_not_found"):
            ns["_prompt_ref_chat"]([{"role": "user", "content": "story"}], require_history=required)
        assert ns["_prompt_ref_conversation"]["conversation_id"] == "original"
    assert len(requests) == retries
