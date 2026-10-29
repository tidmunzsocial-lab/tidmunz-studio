"""Verify actual curl multipart bytes without submitting a paid provider request."""
import email.parser
import email.policy
import http.server
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
import snapgen_grok_lower as G
from test_video_auto_scene_provider import load


@pytest.mark.parametrize("model", [G.MODEL, G.GROK_LITE_MODEL])
@pytest.mark.parametrize("prompt", [
    'King Thao Wanlop speaks; no other voices.\nพูดว่า “เจ้าโตเป็นสาวแล้ว จะเลี้ยงกระต่ายทำไมเล่า”',
    '@not-a-file; พูดตามบท\nNegative: extra words; camera cuts',
    '<not-a-file;type=text/plain\nบทพูดภาษาไทย "ครบทั้งประโยค"',
])
def test_curl_sends_complete_literal_prompt_and_reference(tmp_path, model, prompt):
    if not shutil.which("curl"):
        pytest.skip("curl executable unavailable")
    received = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            message = email.parser.BytesParser(policy=email.policy.default).parsebytes(
                ("Content-Type: " + self.headers["Content-Type"] + "\r\n\r\n").encode() + raw)
            received.append({part.get_param("name", header="content-disposition"):
                             part.get_payload(decode=True) for part in message.iter_parts()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"uuid":"local-test-only"}')

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        image = tmp_path / "reference.png"
        image.write_bytes(b"reference bytes")
        command = G.build_command("local-test-key", prompt, image, "720p", "6", "landscape", "custom", model)
        command[command.index("POST") + 1] = f"http://127.0.0.1:{server.server_port}/"
        subprocess.run(command, check=True, capture_output=True, timeout=10)
        assert received[0]["prompt"].decode("utf-8") == prompt
        assert received[0]["files"] == b"reference bytes"
        assert received[0]["skip_audio"] == b"false"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_auto_slot_dialogue_follows_each_scene_after_silent_scene():
    class Value:
        def __init__(self, value=""):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    class Box:
        def delete(self, *args):
            self.text = ""

        def insert(self, index, text):
            self.text = text

    dialogue, box, captured = Value("ไม่มีบทพูด"), Box(), []
    cfg = {"dialogue": dialogue}
    runtime = dict(slot_cfg_vars=[{}, cfg], slot_images=[None, Value()], slot_prompts=[None, box],
                   slot_busy=[False, True])
    runtime["on_generate_slot"] = lambda index: captured.append((dialogue.get(), box.text))
    scope = dict(runtime=runtime, state={"project": {"aspect": "16:9"}}, slot_index=1,
                 scene={}, seedance_refs=[], prompt="reviewed prompt", errors=[],
                 set_slot_config=lambda *args: None, VIDEO_AUTO_MODEL="grok-lower",
                 VIDEO_GROK_LITE_MODEL=G.GROK_LITE_MODEL, VIDEO_GROK_LOWER_MODEL=G.MODEL,
                 GROK_CLIP_SECONDS=(6, 10, 15), tk=SimpleNamespace(END="end"))
    submit = load(scope, "submit", "make_clip")
    for speaker in (None, "ท้าววัลลภ", None, "เขมา"):
        scope["scene"] = dict(dialogue=speaker, image="scene.png", clip_model=G.MODEL,
                              clip_seconds=6, clip_slow=False)
        assert submit()
    assert [mode for mode, _ in captured] == ["ไม่มีบทพูด", "มีบทพูด", "ไม่มีบทพูด", "มีบทพูด"]
    assert all(text == "reviewed prompt" for _, text in captured)
