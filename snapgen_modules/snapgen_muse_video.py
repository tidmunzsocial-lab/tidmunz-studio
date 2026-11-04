"""SnapGen Muse AI video API adapter."""

import hashlib
import tempfile
import uuid
from pathlib import Path


# Hosted video APIs reject oversized frame and reference uploads.
# Only upload copies are compressed: original PNG/JPEG and project paths are immutable.
MAX_REFERENCE_BYTES = 9_500_000


def upload_image(source):
    source = Path(source)
    stat = source.stat()
    if stat.st_size <= MAX_REFERENCE_BYTES:
        return source
    from PIL import Image, ImageOps

    fingerprint = hashlib.sha256(
        (str(source.resolve()) + "|" + str(stat.st_size)
         + "|" + str(stat.st_mtime_ns)).encode("utf-8")
    ).hexdigest()[:24]
    target_dir = Path(tempfile.gettempdir()) / "tidmunz_video_upload"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / (fingerprint + ".jpg")
    if target.is_file() and 0 < target.stat().st_size <= MAX_REFERENCE_BYTES:
        try:
            with Image.open(target) as check:
                check.verify()  # Never use a partial file left by an interrupted upload.
            return target
        except (OSError, ValueError):
            pass

    temporary = target_dir / (fingerprint + "." + uuid.uuid4().hex + ".tmp")
    try:
        with Image.open(source) as original:
            frame = ImageOps.exif_transpose(original).convert("RGB")
        try:
            for _ in range(12):
                for quality in (90, 82, 72, 60):
                    frame.save(temporary, format="JPEG", quality=quality, optimize=True)
                    if 0 < temporary.stat().st_size <= MAX_REFERENCE_BYTES:
                        temporary.replace(target)
                        return target
                # Some noisy/very large images remain over 10 MB even as JPEG.
                # Reduce the *upload copy* dimensions until they fit.
                width, height = max(1, int(frame.width * 0.8)), max(1, int(frame.height * 0.8))
                if min(width, height) < 128:
                    break
                smaller = frame.resize((width, height), Image.Resampling.LANCZOS)
                frame.close()
                frame = smaller
            raise RuntimeError("รูปอ้างอิงใหญ่เกิน 10 MB แม้บีบอัดและย่อสำเนาแล้ว")
        finally:
            frame.close()
    finally:
        temporary.unlink(missing_ok=True)


MODEL = "muse-ai-video"
LABEL = "Muse AI · 10s"
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
    source = upload_image(source)

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
