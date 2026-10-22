"""SnapGen Muse AI video API adapter."""

from pathlib import Path


MODEL = "muse-ai-video"
LABEL = "Muse AI · 10s · ฟรี"
API_URL = "https://api.snapgen.ai/uapi/v1/video-gen/meta"
SUPPORTED_DURATION = "10"


def orientation_for_aspect(aspect):
    value = str(aspect or "").strip().lower()
    if value in {"1:1", "square"}:
        return "square"
    return "portrait" if value in {"9:16", "portrait", "vertical"} else "landscape"


def build_command(api_key, prompt, image, duration, aspect):
    key = str(api_key or "").strip()
    if not key:
        raise RuntimeError("กรุณาใส่ SnapGen API key ในหน้าตั้งค่าก่อน")
    source = Path(str(image or "").strip())
    if not source.is_file():
        raise RuntimeError("ไม่พบรูปเริ่มต้นสำหรับ Muse AI")

    return [
        "curl", "-sS", "-X", "POST", API_URL,
        "-H", "x-api-key: " + key,
        "--form-string", "prompt=" + str(prompt or "").strip(),
        "--form-string", "model=" + MODEL,
        "--form-string", "duration=" + SUPPORTED_DURATION,
        "--form-string", "orientation=" + orientation_for_aspect(aspect),
        "--form", "files=@" + str(source),
    ]


def find_video_url(payload):
    """Find Muse's finished video URL in SnapGen history response shapes."""
    if isinstance(payload, dict):
        for key in ("media_url", "video_url", "download_url", "output_url", "url"):
            value = find_video_url(payload.get(key))
            if value:
                return value
        for key in ("generated_video", "media_files", "generate_result", "result", "data", "media"):
            value = find_video_url(payload.get(key))
            if value:
                return value
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            value = find_video_url(item)
            if value:
                return value
    elif isinstance(payload, str) and payload.startswith(("http://", "https://")):
        return payload
    return None
