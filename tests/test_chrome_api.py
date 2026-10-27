"""The program's own ChatGPT API (snapgen_chrome_api) that replaced the separate Bridge."""
import base64
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "snapgen_modules"))

import snapgen_chrome_api as api  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16
PNG_B64 = base64.b64encode(PNG).decode("ascii")


def test_chat_job_continued_story_sends_only_newest_user_text_and_pictures():
    body = {"messages": [{"role": "user", "content": "old turn"},
                         {"role": "user", "content": [
                             {"type": "text", "text": "ดูรูปนี้"},
                             {"type": "image_url", "image_url": {"url": "data:image/png;base64," + PNG_B64}}]}],
            "metadata": {"conversation_id": "c1", "parent_message_id": "m1"}}
    job = api.chat_job(body)
    assert job == {"type": "chat", "prompt": "ดูรูปนี้", "images": ["data:image/png;base64," + PNG_B64],
                   "conversation_id": "c1"}


def test_chat_job_new_chat_joins_system_and_user_and_reads_docx_as_text():
    import io
    import zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("word/document.xml", "<w:p><w:r><w:t>บทที่ 1 &amp; นาค</w:t></w:r></w:p>")
    docx = base64.b64encode(buffer.getvalue()).decode("ascii")
    body = {"messages": [{"role": "system", "content": "กฎ"},
                         {"role": "user", "content": [{"type": "input_text", "text": "อ่านบท"},
                                                      {"type": "input_file", "filename": "s.docx", "file_data": docx}]}]}
    job = api.chat_job(body)
    assert job["conversation_id"] is None
    assert job["prompt"].startswith("[SYSTEM]\nกฎ\n\n[USER]\nอ่านบท")
    assert "บทที่ 1 & นาค" in job["prompt"]


def test_vision_and_image_jobs_accept_raw_base64_and_data_url_items():
    vision = api.chat_job({"prompt": "จำรูป", "images": [PNG_B64],
                           "input_images": [{"name": "a.jpg", "data_url": "data:image/jpeg;base64,AAAA"}]})
    assert vision["images"] == ["data:image/png;base64," + PNG_B64, "data:image/jpeg;base64,AAAA"]
    image = api.image_job({"prompt": "วาด", "images": [PNG_B64], "metadata": {"conversation_id": "c9"}})
    assert image == {"type": "image", "prompt": "วาด", "images": ["data:image/png;base64," + PNG_B64],
                     "conversation_id": "c9"}


def test_replies_echo_the_story_account_and_carry_the_cursor():
    seen = []

    def run(job):
        seen.append(job)
        if job["type"] == "chat":
            return {"text": "OK", "conversation_id": "c1", "message_id": "m2"}
        return {"images": ["data:image/png;base64," + PNG_B64], "conversation_id": "c1", "message_id": "m3"}

    code, reply = api.handle("POST", "/v1/chat/completions",
                             {"messages": [{"role": "user", "content": "hi"}], "chatgpt_account": "tidmunz"},
                             run, {"email": "x@gmail.com"})
    assert code == 200
    assert reply["choices"][0]["message"]["content"] == "OK"
    assert api.extract_cursor(reply) == ("c1", "m2")
    assert reply["chatgpt_account"] == "tidmunz"  # old story bound to a Bridge account name keeps working
    code, reply = api.handle("POST", "/v1/images/generations", {"prompt": "วาด"}, run, {"email": "x@gmail.com"})
    assert code == 200 and reply["data"][0]["b64_json"] == PNG_B64
    assert (reply["conversation_id"], reply["parent_message_id"], reply["chatgpt_account"]) == ("c1", "m3", "x@gmail.com")


def test_errors_map_to_codes_pages_already_understand():
    lost = api.handle("POST", "/v1/chat/completions", {"prompt": "x"},
                      lambda job: {"error": "conversation failed: 404", "not_found": True}, {})
    assert lost[0] == 404 and "conversation_not_found" in lost[1]["error"]["message"]
    no_picture = api.handle("POST", "/v1/images/edits", {"prompt": "x"},
                            lambda job: {"text": "You've hit the limit, try again later"}, {})
    assert no_picture[0] == 429 and "rate limit" in no_picture[1]["error"]["message"]
    assert api.handle("GET", "/health", {}, None, {"connected": True})[1]["active_operations"] == 0
    assert api.handle("GET", "/v1/chatgpt/admin/accounts", {}, None, {})[0] == 404


def test_relay_serves_the_api_under_its_token_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    import snapgen_chrome_relay as relay
    root = relay.api_root()
    assert root.startswith("http://127.0.0.1:") and root.rsplit("/", 1)[1] == relay.RELAY.token

    def fake_extension():
        job = relay.RELAY.next_job(10)
        relay.RELAY.finish({"id": job["id"], "text": "ตอบ: " + job["prompt"], "conversation_id": "c7",
                            "message_id": "m8"})
    threading.Thread(target=fake_extension, daemon=True).start()
    request = urllib.request.Request(
        root + "/v1/chat/completions", method="POST", headers={"Content-Type": "application/json"},
        data=json.dumps({"messages": [{"role": "user", "content": "สวัสดี"}]}).encode("utf-8"))
    with urllib.request.urlopen(request, timeout=20) as response:
        reply = json.loads(response.read().decode("utf-8"))
    assert reply["text"] == "ตอบ: สวัสดี" and reply["conversation_id"] == "c7"
    # Without the token in the path nothing reaches the extension.
    bad = urllib.request.Request(root.rsplit("/", 1)[0] + "/wrong/v1/chat/completions", method="POST",
                                 data=b"{}", headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(bad, timeout=5)
        raise AssertionError("request without the token was accepted")
    except urllib.error.HTTPError as exc:
        assert exc.code == 403
