"""SnapGen Grok Lower video API adapter."""

import json
import subprocess
from pathlib import Path


MODEL = "grok-lower"
LABEL = "Grok Lower — เสียเครดิต 50%"
API_URL = "https://api.snapgen.ai/uapi/v1/video-gen/grok-lower"
GROK_LITE_MODEL = "grok-1.5-lite"
GROK_LITE_LABEL = "Grok 1.5 Lite · 720p / 1080p"
GROK_LITE_API_URL = "https://api.snapgen.ai/uapi/v1/video-gen/grok-1.5-lite"
SUPPORTED_DURATIONS = ("6", "10", "15")
GROK_LITE_RESOLUTIONS = ("720p", "1080p")  # first = default (cheaper: 720p 10 s about 7 credits)


def build_command(api_key, prompt, image, resolution, duration, aspect, mode, model=MODEL):
    key = str(api_key or "").strip()
    if not key:
        raise RuntimeError("กรุณาใส่ SnapGen API key ในหน้าตั้งค่าก่อน")
    model = str(model or MODEL).strip()
    api_url = {MODEL: API_URL, GROK_LITE_MODEL: GROK_LITE_API_URL}.get(model)
    if not api_url:
        raise ValueError(f"ไม่รองรับโมเดล Grok: {model}")
    if model == GROK_LITE_MODEL:
        resolution = str(resolution or "").strip()
        resolution = resolution if resolution in GROK_LITE_RESOLUTIONS else GROK_LITE_RESOLUTIONS[0]
    else:
        resolution = str(resolution or "480p").strip()
    source = Path(str(image or "").strip())
    if not source.is_file():
        raise RuntimeError("ไม่พบรูปเริ่มต้นสำหรับ Grok")
    return [
        "curl", "-sS", "-N", "--max-time", "45", "-X", "POST", api_url,
        "-H", "x-api-key: " + key,
        "--form", "prompt=" + str(prompt or "").strip(),
        "--form", "model=" + model,
        "--form", "resolution=" + resolution,
        "--form", "duration=" + str(duration or "6").strip(),
        "--form", "aspect_ratio=" + str(aspect or "landscape").strip(),
        "--form", "mode=" + str(mode or "custom").strip(),
        "--form", "skip_audio=false",
        "--form", "files=@" + str(source),
    ]


def _json_lines(raw):
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    text = str(raw or "").strip()
    if not text:
        return []
    candidates = [text]
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            line = line[5:].strip()
        if line and line != "[DONE]":
            candidates.append(line)
    payloads = []
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            payloads.append(value)
    return payloads


def request(api_key, prompt, image, resolution, duration, aspect, mode, model=MODEL):
    command = build_command(api_key, prompt, image, resolution, duration, aspect, mode, model)
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        output = (result.stdout or result.stderr or "").strip()
        return _response_from_output(output, result.returncode, model)
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or exc.stderr or ""
        return _response_from_output(output, 28, model)


def _response_from_output(output, returncode, model=MODEL):
    label = "Grok Lite" if model == GROK_LITE_MODEL else "Grok Lower"
    payloads = _json_lines(output)
    if payloads:
        for payload in payloads:
            if any(payload.get(key) for key in ("uuid", "history_uuid", "conversion_uuid", "id")):
                return payload
        return payloads[0]
    if returncode:
        raise RuntimeError(f"{label} API ตอบกลับไม่สำเร็จ: " + str(output)[:1000])
    raise RuntimeError(f"{label} API ตอบกลับไม่ใช่ JSON: " + str(output)[:1000])
