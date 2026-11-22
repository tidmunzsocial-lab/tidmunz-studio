"""v2.0.45 must preserve the installed manual monitor while freeing Auto and covers."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "snapgen_modules"))
import snapgen_page_narrate as N
PAGE = (ROOT / "snapgen_modules" / "snapgen_page_narrate.py").read_text(encoding="utf8")
EXTENSION = ROOT / "snapgen_modules" / "chrome_ext"

def test_film_preserves_colors_and_texture():
    assert N.FILM_GRADE == ""
    assert "colorbalance=" not in N.FILM_LOOK and "saturation=" not in N.FILM_LOOK
    assert "noise=alls=24" in N.FILM_LOOK and "vignette=" in N.FILM_LOOK
    assert "สีซีดอมเขียวเทา" not in N.STYLES["เรื่องผี"]["prompt"]

def test_red_button_and_cover_folder_present():
    assert 'is_cover = title == "วิดีโอ" and label == "สร้างหน้าปก"' in PAGE
    assert 'bg="#DC2626" if is_cover' in PAGE
    assert 'button.after(1600, enforce_cover_red)' in PAGE
    assert 'out_dir = folder / "หน้าปก"' in PAGE
    assert 'label="เปิดโฟลเดอร์หน้าปก"' in PAGE
    assert '"covers": stage_covers' in PAGE

def test_manual_monitor_kept_but_not_required_in_auto():
    assert all(k != "monitor" for k, _, _ in N.VIDEO_STAGES)
    assert all(k != "monitor" for k, _, _ in N.LEGACY_VIDEO_STAGES)
    assert sum(w for _, _, w in N.VIDEO_STAGES) == 100
    assert sum(w for _, _, w in N.LEGACY_VIDEO_STAGES) == 100
    assert 'def stage_monitor_chat(*, wake=False)' in PAGE
    assert 'stage_monitor_chat(wake=True)' not in PAGE
    assert 'keys = auto_resume_keys_with_monitor(project, keys' not in PAGE
    assert (EXTENSION / "followup.js").is_file()
    assert (EXTENSION / "monitor_apps.js").is_file()
    assert 'importScripts("followup.js")' in (EXTENSION / "background.js").read_text(encoding="utf8")
