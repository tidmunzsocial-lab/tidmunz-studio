import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
from snapgen_image_api_config import current_image_api_key, load_image_api_key, save_image_api_key


def test_missing_or_invalid_image_key_file_is_empty(tmp_path):
    path = tmp_path / "snapgen_image_api_key.json"
    assert load_image_api_key(path) == ""
    path.write_text("not json", encoding="utf-8")
    assert load_image_api_key(path) == ""
    path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    assert load_image_api_key(path) == ""


def test_image_key_round_trips_trimmed_without_touching_other_settings(tmp_path):
    path = tmp_path / "snapgen_data" / "snapgen_image_api_key.json"
    save_image_api_key(path, "  image-test-key  ")
    assert load_image_api_key(path) == "image-test-key"
    assert json.loads(path.read_text(encoding="utf-8")) == {"api_key": "image-test-key"}


def test_image_key_prefers_page_value_and_never_falls_back_to_legacy_video_key():
    page = {"snapgen_image_api_key_var": SimpleNamespace(get=lambda: " page-image-key ")}
    runtime = {"snapgen_image_api_key_var": SimpleNamespace(get=lambda: "runtime-image-key"),
               "api_key_var": SimpleNamespace(get=lambda: "legacy-video-key")}
    assert current_image_api_key(page, runtime) == "page-image-key"

    blank_page = {"snapgen_image_api_key_var": SimpleNamespace(get=lambda: " ")}
    legacy_only = {"api_key_var": SimpleNamespace(get=lambda: "legacy-video-key")}
    assert current_image_api_key(blank_page, legacy_only) == ""
