# -*- coding: utf-8 -*-
"""The program's own ChatGPT API, answered by the "Tidmunz ChatGPT" Chrome extension.

Replaces the separate Bridge (chatgpt-api on 127.0.0.1:8000). Every page keeps sending the same
OpenAI-style requests it always sent; snapgen_chrome_relay serves them under
http://127.0.0.1:<port>/<token>/v1/... and turns each one into a job for the extension:

  chat:  {"type": "chat",  "prompt", "images": [data URLs], "conversation_id"}
         -> {"text", "conversation_id", "message_id"}
  image: {"type": "image", "prompt", "images": [data URLs], "conversation_id"}
         -> {"images": [data URLs], "text", "conversation_id", "message_id"}

Story histories stay real chatgpt.com conversations (conversation_id); the extension always
continues at the end of the chat, so parent_message_id is returned for the pages but not needed.
"""
from __future__ import annotations

import base64
import io
import re
import urllib.request
import zipfile

ROUTES = ("/v1/chat/completions", "/v1/chatgpt/vision", "/v1/images/generations", "/v1/images/edits")


def _mime_of(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/png"


def data_url(value) -> str:
    """A data URL from what pages send: a data URL, an http(s) URL, raw base64, or {"data_url"/"url"/"b64"}."""
    if isinstance(value, dict):
        value = value.get("data_url") or value.get("url") or value.get("b64_json") or value.get("b64") or ""
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("data:"):
        return text
    if text.startswith(("http://", "https://")):
        with urllib.request.urlopen(text, timeout=60) as response:
            raw = response.read()
            mime = response.headers.get_content_type() or _mime_of(raw)
        return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")
    try:
        raw = base64.b64decode(text, validate=False)
    except ValueError:
        return ""
    return f"data:{_mime_of(raw)};base64,{text}"


def document_text(data: bytes, name: str) -> str:
    """Plain text of an attached document: .docx paragraphs, anything else decoded as text."""
    if name.lower().endswith(".docx") or data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
            paragraphs = re.findall(r"<w:p[ >].*?</w:p>", xml, re.S)
            text = "\n".join("".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, re.S)) for p in paragraphs)
            for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'")):
                text = text.replace(a, b)
            return text.strip()
        except Exception as exc:
            return f"(อ่านไฟล์ {name} ไม่ได้: {exc})"
    return data.decode("utf-8", errors="replace")


def _content_text(content, images: list) -> str:
    """Text of one message's content; pictures are collected into images, documents become text."""
    if isinstance(content, str):
        return content
    parts = []
    for part in content or []:
        if isinstance(part, str):
            parts.append(part)
            continue
        if not isinstance(part, dict):
            continue
        kind = str(part.get("type") or "")
        if kind in ("text", "input_text"):
            parts.append(str(part.get("text") or ""))
        elif kind in ("image_url", "input_image"):
            url = part.get("image_url")
            url = url.get("url") if isinstance(url, dict) else (url or part.get("url") or part.get("data_url"))
            picture = data_url(url)
            if picture:
                images.append(picture)
        elif kind in ("input_file", "file"):
            name = str(part.get("filename") or part.get("name") or "file")
            try:
                raw = base64.b64decode(str(part.get("file_data") or ""))
            except ValueError:
                raw = b""
            parts.append(f"\n===== ไฟล์แนบ: {name} =====\n{document_text(raw, name)}\n===== จบไฟล์ {name} =====")
    return "\n".join(p for p in parts if p)


def conversation_of(body: dict) -> str | None:
    """The story chat to continue, wherever the page put it."""
    for holder in (body.get("metadata"), body):
        if isinstance(holder, dict) and isinstance(holder.get("conversation_id"), str) and holder["conversation_id"]:
            return holder["conversation_id"]
    return None


def chat_job(body: dict) -> dict:
    """chat/completions or chatgpt/vision request -> chat job."""
    images: list[str] = []
    conversation_id = conversation_of(body)
    if body.get("messages"):
        messages = [m for m in body["messages"] if isinstance(m, dict)]
        if conversation_id or len(messages) == 1:
            # A continued chat already holds the earlier turns: send only the newest user message.
            user = [m for m in messages if m.get("role", "user") == "user"] or messages
            prompt = _content_text(user[-1].get("content"), images)
        else:
            prompt = "\n\n".join(f"[{str(m.get('role') or 'user').upper()}]\n{_content_text(m.get('content'), images)}"
                                 for m in messages)
    else:
        prompt = str(body.get("prompt") or "")
    for item in list(body.get("images") or []) + list(body.get("input_images") or []):
        picture = data_url(item)
        if picture:
            images.append(picture)
    return {"type": "chat", "prompt": prompt, "images": images, "conversation_id": conversation_id}


def image_job(body: dict) -> dict:
    """images/generations or images/edits request -> image job."""
    sent = list(body.get("images") or []) + ([body["image"]] if body.get("image") else [])
    images = [p for p in (data_url(item) for item in sent) if p]
    return {"type": "image", "prompt": str(body.get("prompt") or ""), "images": images,
            "conversation_id": conversation_of(body)}


def error_reply(result: dict) -> tuple[int, dict]:
    error = str(result.get("error") or "ChatGPT (Chrome) error")
    if result.get("provider_status") in (401, 403):
        status = int(result["provider_status"])
        return status, {"error": {"code": "chatgpt_conversation_access_denied",
                                 "provider_status": status, "message": error}}
    if result.get("not_found") or "conversation failed: 404" in error:
        return 404, {"error": {"code": "chatgpt_conversation_not_found",
                               "message": "conversation_not_found — " + error}}
    low = error.lower()
    if "limit" in low or "ลิมิต" in error:
        return 429, {"error": {"code": "rate_limited", "message": "ChatGPT image rate limit: " + error}}
    return 502, {"error": {"code": "chrome_error", "message": "ChatGPT (Chrome): " + error}}


def chat_reply(result: dict, account: str) -> dict:
    text = str(result.get("text") or "")
    conversation_id = result.get("conversation_id")
    message_id = result.get("message_id")
    return {
        "object": "chat.completion", "model": "chatgpt-chrome",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}],
        "text": text, "conversation_id": conversation_id, "parent_message_id": message_id,
        "chatgpt_account": account,
    }


def image_reply(result: dict, account: str) -> tuple[int, dict]:
    data = []
    for url in result.get("images") or []:
        head, _, payload = str(url).partition(",")
        if payload:
            data.append({"b64_json": payload, "mime_type": head[5:].split(";")[0] or "image/png"})
    if not data:
        text = str(result.get("text") or "").strip()
        low = text.lower()
        if any(w in low for w in ("limit", "ลิมิต", "try again", "ลองใหม่อีกครั้ง", "ขีดจำกัด")):
            return 429, {"error": {"code": "rate_limited", "message": "ChatGPT image rate limit: " + text[:300]}}
        return 502, {"error": {"code": "no_image",
                               "message": "ChatGPT did not draw the image. GPT said: " + (text or "no picture")}}
    return 200, {"created": 0, "data": data, "conversation_id": result.get("conversation_id"),
                 "parent_message_id": result.get("message_id"), "chatgpt_account": account, "engine": "chrome"}


def handle(method: str, path: str, body: dict, run, status: dict) -> tuple[int, dict]:
    """One API request. run(job) -> extension result; status = relay status (email, busy ...)."""
    # Pages keep the account name each story chat was made under and check it on every reply.
    # The extension always uses the ChatGPT login of the program's Chrome, so the name a page sent
    # is echoed back: old stories (made under a Bridge account name) keep working.
    account = str(body.get("chatgpt_account") or status.get("email") or "chrome")
    if method == "GET":
        if path in ("/health", "/v1/health"):
            # The extension runs jobs one by one from its own queue, so a page never has to wait here.
            return 200, {"status": "ok", "engine": "chrome", "connected": bool(status.get("connected")),
                         "active_operations": 0, "account": account}
        if path.startswith("/v1/chatgpt/admin/artifacts"):
            return 200, {"artifacts": []}  # nothing is stored on the side: a lost reply cannot be recovered
        if path == "/v1/chatgpt/usage":
            return 200, {"account": account, "images_left": status.get("images_left"),
                         "images_reset": status.get("images_reset"), "plan": status.get("plan")}
        return 404, {"error": {"code": "not_found", "message": f"ไม่มี {path} (ไม่ใช้ Bridge แล้ว)"}}
    if path in ("/v1/chat/completions", "/v1/chatgpt/vision"):
        job = chat_job(body)
        if not job["prompt"] and not job["images"]:
            return 400, {"error": {"code": "empty", "message": "empty message"}}
        result = run(job)
        if result.get("error"):
            return error_reply(result)
        return 200, chat_reply(result, account)
    if path in ("/v1/images/generations", "/v1/images/edits"):
        result = run(image_job(body))
        if result.get("error"):
            return error_reply(result)
        return image_reply(result, account)
    return 404, {"error": {"code": "not_found", "message": f"ไม่มี {path} (ไม่ใช้ Bridge แล้ว)"}}


def extract_cursor(data):
    """(conversation_id, parent_message_id) of a reply, wherever it sits (also older reply layouts)."""
    if not isinstance(data, dict):
        return None, None
    candidates = [data]
    for key in ("metadata", "meta", "raw", "response", "result", "data"):
        value = data.get(key)
        if isinstance(value, dict):
            candidates.append(value)
    for choice in data.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        candidates.append(choice)
        message = choice.get("message")
        if isinstance(message, dict):
            candidates.append(message)
            candidates.extend(message[key] for key in ("metadata", "raw") if isinstance(message.get(key), dict))
    conversation_id = parent_message_id = None
    for value in candidates:
        conversation_id = conversation_id or value.get("conversation_id") or value.get("chatgpt_conversation_id")
        parent_message_id = (parent_message_id or value.get("parent_message_id") or value.get("message_id")
                             or value.get("chatgpt_message_id"))
    return conversation_id, parent_message_id
