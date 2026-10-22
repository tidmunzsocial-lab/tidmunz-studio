import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "snapgen_modules"))
import snapgen_muse_video as M
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


def test_muse_is_available_in_mobile_video_options():
    controller = MobileController.__new__(MobileController)
    controller.app = {}
    controller.g = {"duration_values_for_model": lambda model: ["8"]}
    assert {"value": M.MODEL, "label": M.LABEL} in controller._models()
    options = controller.options(M.MODEL)
    assert options["duration"] == ["10"]
    assert options["aspect"] == ["อัตโนมัติ", "16:9", "9:16", "1:1"]
