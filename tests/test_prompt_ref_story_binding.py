"""Changing the source file must not send a second story into an old chat."""
import ast
import copy
import hashlib
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
