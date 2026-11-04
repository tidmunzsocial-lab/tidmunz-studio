import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "snapgen_modules"))
import snapgen_muse_video as M
import snapgen_seedance_video as S
import snapgen_vela_video as V
from snapgen_mobile_controller import MobileController


def test_muse_command_uses_snapgen_free_ten_second_contract(tmp_path):
    image = tmp_path / "scene.png"
    image.write_bytes(b"scene")
    command = M.build_command("test-key", "slow camera move", image, "30", "9:16")
    assert command[command.index("POST") + 1] == M.API_URL
    assert "model=muse-ai-video" in command
    assert "duration=10" in command
    assert "orientation=portrait" in command
    assert "prompt=slow camera move" in command
    assert "files=@" + str(image) in command
    assert M.orientation_for_aspect("1:1") == "square"
    assert M.find_video_url({"generated_video": [{"video_url": "https://cdn.example/video.mp4"}]}) == "https://cdn.example/video.mp4"


def test_muse_compresses_oversize_reference_without_touching_original(tmp_path, monkeypatch):
    import hashlib
    import os
    from PIL import Image

    source = tmp_path / "oversize.png"
    data = os.urandom(2000 * 1800 * 3)
    Image.frombytes("RGB", (2000, 1800), data).save(source, compress_level=0)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    assert source.stat().st_size > M.MAX_REFERENCE_BYTES
    monkeypatch.setattr(M.tempfile, "gettempdir", lambda: str(tmp_path))
    command = M.build_command("test-key", "move slowly", source, "10", "16:9")
    upload = Path(command[command.index("--form") + 1].split("@", 1)[1])
    assert upload != source and upload.suffix == ".jpg"
    assert 0 < upload.stat().st_size <= M.MAX_REFERENCE_BYTES
    with Image.open(upload) as result:
        assert result.size == (2000, 1800)
        result.verify()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_oversized_noise_is_downscaled_until_upload_fits(tmp_path, monkeypatch):
    import hashlib
    import os
    from PIL import Image

    source = tmp_path / "random.png"
    Image.frombytes("RGB", (600, 400), os.urandom(600 * 400 * 3)).save(source, compress_level=0)
    original_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    monkeypatch.setattr(M.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(M, "MAX_REFERENCE_BYTES", 100_000)
    upload = M.upload_image(source)
    with Image.open(upload) as image:
        assert image.size[0] < 600  # JPEG quality reductions alone cannot meet this small test limit.
        assert image.size[1] < 400
        image.verify()
    assert 0 < upload.stat().st_size <= 100_000
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_digest
    assert M.upload_image(source) == upload  # Cache safely reuses the verified output.


def test_oversized_image_auto_compresses_for_vela_and_seedance_refs(tmp_path, monkeypatch):
    import os
    from PIL import Image

    scene = tmp_path / "scene.png"
    ref = tmp_path / "actor.png"
    for path in (scene, ref):
        Image.frombytes("RGB", (600, 400), os.urandom(600 * 400 * 3)).save(path, compress_level=0)
    original_sizes = {path: path.stat().st_size for path in (scene, ref)}
    monkeypatch.setattr(M.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(M, "MAX_REFERENCE_BYTES", 100_000)

    vela = V.build_command("key", "gentle camera move", scene, "5", "16:9")
    vela_path = Path(next(arg.split("@", 1)[1] for arg in vela if arg.startswith("files=@")))
    assert vela_path != scene and vela_path.stat().st_size <= 100_000

    seedance = S.build_command(
        "key", "sd-2-lower", "gentle camera move", scene, "720p", "5", "16:9",
        [{"name": "Actor", "role": "ตัวละคร", "path": str(ref)}],
    )
    sent = [Path(arg.split("@", 1)[1]) for arg in seedance if arg.startswith("ref_images=@")]
    assert len(sent) == 2
    assert all(path.suffix == ".jpg" and path.stat().st_size <= 100_000 for path in sent)
    assert all(path != origin for path, origin in zip(sent, (scene, ref)))
    assert all(path.stat().st_size == size for path, size in original_sizes.items())


def test_muse_is_available_in_mobile_video_options():
    controller = MobileController.__new__(MobileController)
    controller.app = {}
    controller.g = {"duration_values_for_model": lambda model: ["8"]}
    assert {"value": M.MODEL, "label": M.LABEL} in controller._models()
    options = controller.options(M.MODEL)
    assert options["duration"] == ["10"]
    assert options["aspect"] == ["อัตโนมัติ", "16:9", "9:16", "1:1"]
