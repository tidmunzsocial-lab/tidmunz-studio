import io
import json
import random
import sys
from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
import snapgen_page_narrate as N


def noise(path, size, mode="RGB", exif=None):
    channels = 4 if mode == "RGBA" else 3
    image = Image.frombytes(mode, size, random.Random(42).randbytes(size[0] * size[1] * channels))
    if mode == "RGBA":
        image.putalpha(128)
    image.save(path, "PNG", compress_level=0, **({"exif": exif} if exif else {}))
    return path


def test_small_references_keep_original_bytes_and_order(tmp_path):
    refs = [noise(tmp_path / f"{i}.png", (16 + i, 16)) for i in range(3)]
    originals = [p.read_bytes() for p in refs]
    assert N._prepare_maxplus_references(refs) == [("image/png", data) for data in originals]
    assert [p.read_bytes() for p in refs] == originals


def test_oversized_png_compresses_without_reducing_dimensions(tmp_path):
    path = noise(tmp_path / "sheet.png", (256, 144))
    original = path.read_bytes()
    logs = []
    [(mime, data)] = N._prepare_maxplus_references([path], max_image_bytes=100_000, log=logs.append)
    assert len(original) > 100_000 >= len(data)
    assert mime == "image/jpeg"
    with Image.open(io.BytesIO(data)) as result:
        assert result.size == (256, 144)
    assert path.read_bytes() == original
    assert len(logs) == 1


def test_total_budget_is_enforced_without_reordering_or_dropping_refs(tmp_path):
    sizes = [(128, 64), (64, 128), (128, 128)]
    refs = [noise(tmp_path / f"{i}.png", size) for i, size in enumerate(sizes)]
    originals = [p.read_bytes() for p in refs]
    assert all(len(data) < 100_000 for data in originals)
    assert sum(map(len, originals)) > 70_000
    prepared = N._prepare_maxplus_references(refs, max_image_bytes=100_000, max_total_bytes=70_000)
    assert len(prepared) == len(refs)
    assert sum(len(data) for _, data in prepared) <= 70_000
    for (_, data), (width, height) in zip(prepared, sizes):
        with Image.open(io.BytesIO(data)) as result:
            assert abs(result.width / result.height - width / height) < 0.04
    assert [p.read_bytes() for p in refs] == originals


def test_transparent_reference_keeps_alpha(tmp_path):
    path = noise(tmp_path / "actor.png", (96, 64), "RGBA")
    [(mime, data)] = N._prepare_maxplus_references([path], max_image_bytes=15_000)
    assert mime == "image/webp" and len(data) <= 15_000
    with Image.open(io.BytesIO(data)) as result:
        assert result.mode == "RGBA"
        assert result.getchannel("A").getextrema() == (128, 128)


def test_reencoded_reference_applies_exif_orientation(tmp_path):
    exif = Image.Exif()
    exif[274] = 6
    path = noise(tmp_path / "portrait.png", (128, 64), exif=exif)
    [(mime, data)] = N._prepare_maxplus_references([path], max_image_bytes=20_000)
    with Image.open(io.BytesIO(data)) as result:
        assert result.size == (64, 128)


def test_invalid_reference_fails_before_network(tmp_path, monkeypatch):
    path = tmp_path / "broken.png"
    path.write_bytes(b"not an image")
    calls = []
    monkeypatch.setattr(N.urllib.request, "urlopen", lambda *a, **kw: calls.append(a))
    with pytest.raises(RuntimeError, match="ชนิดไฟล์"):
        N.maxplus_image("test", [str(path)], str(tmp_path), "result", "9:16", "test-key")
    assert not calls


@pytest.mark.parametrize("aspect", ["9:16", "16:9"])
def test_compressed_multipart_preserves_4k_model_quality_and_aspect(tmp_path, monkeypatch, aspect):
    path = noise(tmp_path / "sheet.png", (128, 64))
    original = path.read_bytes()
    prepare = N._prepare_maxplus_references
    monkeypatch.setattr(N, "_prepare_maxplus_references", lambda refs, **kw:
                        prepare(refs, max_image_bytes=8_000, max_total_bytes=16_000, **kw))
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(buffer, "PNG")
    generated = buffer.getvalue()
    encoded = N.base64.b64encode(generated).decode("ascii")
    calls = []

    def reply(request, **kwargs):
        calls.append(request)
        return io.BytesIO(json.dumps({"data": [{"url": "data:image/png;base64," + encoded}]}).encode())

    monkeypatch.setattr(N.urllib.request, "urlopen", reply)
    result = N.maxplus_image("nine shots", [str(path)], str(tmp_path), "result", aspect,
                             "test-key", model="gpt-image-2-4k", quality="high", size=aspect)
    assert len(calls) == 1
    request = calls[0]
    assert request.full_url == N.MAXPLUS_IMAGE_EDIT_URL
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + request.get_header("Content-type").encode() + b"\r\n\r\n" + request.data)
    parts = list(message.iter_parts())
    fields = {p.get_param("name", header="content-disposition"): p.get_content().strip()
              for p in parts if not p.get_filename()}
    assert fields["model"] == "gpt-image-2-4k"
    assert fields["quality"] == "high" and fields["size"] == aspect
    attached = [p for p in parts if p.get_filename()]
    assert len(attached) == 1 and attached[0].get_content_type() == "image/jpeg"
    assert len(attached[0].get_payload(decode=True)) <= 8_000
    assert Path(result).read_bytes() == generated
    assert path.read_bytes() == original
