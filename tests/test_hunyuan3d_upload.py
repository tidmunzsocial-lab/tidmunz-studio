import io
import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from snapgen_modules.hunyuan3d import Hunyuan3DClient, resize_for_hunyuan_upload


def test_resize_for_hunyuan_upload_is_square_transparent_and_preserves_source(tmp_path):
    source_path = tmp_path / "source.png"
    output_path = tmp_path / "upload.png"
    Image.new("RGBA", (1400, 700), (220, 80, 30, 128)).save(
        source_path, compress_level=0
    )

    result = resize_for_hunyuan_upload(str(source_path), str(output_path))

    assert result == output_path
    with Image.open(result) as resized:
        assert resized.size == (1024, 1024)
        assert resized.getpixel((512, 512))[3] == 128
        assert resized.getpixel((512, 100))[3] == 0
    with Image.open(source_path) as original:
        assert original.size == (1400, 700)


def test_slow_cos_upload_retries_large_png_at_lower_resolution(tmp_path, monkeypatch):
    image_path = tmp_path / "transparent.png"
    original = Image.new("RGBA", (2100, 2100), (220, 80, 30, 128))
    original.save(image_path, compress_level=0)
    original_size = image_path.stat().st_size
    assert original_size > 4 * 1024 * 1024

    class CosServiceError(Exception):
        def get_error_code(self):
            return "UserNetworkTooSlow"

    clients = []

    class FakeCosClient:
        def __init__(self, _config):
            self.calls = []
            clients.append(self)

        def put_object(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise CosServiceError()
            self.uploaded_bytes = kwargs["Body"].read()

    monkeypatch.setitem(
        sys.modules,
        "qcloud_cos",
        SimpleNamespace(
            CosConfig=lambda **_kwargs: object(),
            CosS3Client=FakeCosClient,
            CosServiceError=CosServiceError,
        ),
    )
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("", encoding="utf-8")
    client = Hunyuan3DClient(str(cookie_file))
    client._curl = lambda *_args, **_kwargs: {
        "region": "ap-guangzhou",
        "encryptTmpSecretId": "temporary-id",
        "encryptTmpSecretKey": "temporary-key",
        "encryptToken": "temporary-token",
        "bucketName": "test-bucket",
        "location": "test.png",
        "resourceUrl": "https://example.invalid/test.png",
    }

    assert client.upload_image(str(image_path)) == "https://example.invalid/test.png"
    assert len(clients[0].calls) == 2
    assert clients[0].uploaded_bytes
    with Image.open(io.BytesIO(clients[0].uploaded_bytes)) as uploaded:
        assert uploaded.size == (1024, 1024)
        assert uploaded.getpixel((0, 0))[3] == 128
    with Image.open(image_path) as unchanged:
        assert unchanged.size == (2100, 2100)
    assert image_path.stat().st_size == original_size
