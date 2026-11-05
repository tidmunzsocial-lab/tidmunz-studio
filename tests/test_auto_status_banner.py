"""Auto page status must reflect actual busy/error/completion, not stale progress."""
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
import snapgen_page_narrate as N


def test_auto_page_has_one_progress_panel_and_expandable_visible_log():
    source = inspect.getsource(N._build)
    assert "bar = ttk.Progressbar(status_banner, maximum=100)" in source
    assert "progress_row = tk.Frame" not in source
    assert 'log_box.configure(height=3)' in source
    assert 'log_box.configure(height=8 if expanded else 3)' in source
    assert 'status_percent_var.set(f"{int(percent)}%")' in source
    status, title, *_ = N.auto_work_status(False, False, percent=81)
    assert status == "idle"
    assert "81%" not in title  # The number is displayed once at the right.


def test_saved_percent_counts_93_of_115_clips_instead_of_dropping_to_40(tmp_path):
    scenes = []
    for i in range(115):
        still = tmp_path / f"still_{i}.png"
        still.write_bytes(b"still")
        clip = tmp_path / f"clip_{i}.mp4"
        if i < 93:
            clip.write_bytes(b"movie")
        scenes.append({"image": str(still), "clip": str(clip) if i < 93 else "",
                       "video_prompt_planned": "one-shot cinematic motion"})
    project = {"done": {"context": True, "transcribe": True, "plan": True,
                        "storyboard": True, "images": True}, "scenes": scenes}
    assert N.auto_saved_percent(project, N.VIDEO_STAGES) == 81
    assert N.auto_saved_percent(None, N.VIDEO_STAGES) == 0


@pytest.mark.parametrize("busy,finished,error,expected,color", [
    (True, False, "", "working", "#166534"),
    (False, True, "", "done", "#0F172A"),
    (False, False, "GPT ไม่ได้ตอบเป็น JSON", "error", "#991B1B"),
    (False, False, "", "idle", "#0F172A"),
])
def test_auto_banner_colors_track_real_work_state(busy, finished, error, expected, color):
    kind, title, detail, background, fg = N.auto_work_status(
        busy, finished, error=error, detail="ช็อต 105", elapsed=75, percent=40)
    assert kind == expected
    assert fg == color
    assert "กำลังทำงาน" in title if busy else "กำลังทำงาน" not in title
    if error and not busy:
        assert "GPT ไม่ได้ตอบ" in detail


def test_auto_banner_waiting_long_is_not_falsely_called_done():
    kind, title, detail, *_ = N.auto_work_status(
        True, False, detail="GPT กำลังตรวจช็อต 105", elapsed=750, silent_for=721)
    assert kind == "waiting"
    assert "รอผล" in title
    assert "105" in detail


def test_non_json_completed_reply_retries_and_then_succeeds():
    outputs = iter(["ขออภัย ไม่มี JSON", 'คำตอบ: {"camera":"medium_close","reason":"เห็นหน้าชัด"}'])
    calls, notices = [], []

    def sender(attempt):
        calls.append(attempt)
        return next(outputs)

    parsed = N.retry_structured_gpt_reply(
        sender, label="มุมกล้อง", attempts=3,
        valid=lambda result: result.get("camera") == "medium_close",
        on_retry=lambda attempt, total, why: notices.append((attempt, total, why)))
    assert parsed["camera"] == "medium_close"
    assert calls == [1, 2]
    assert notices[0][0:2] == (2, 3)


def test_wrong_json_schema_also_retries_and_never_returns_bad_camera():
    calls = []
    def sender(attempt):
        calls.append(attempt)
        return '{"camera":"cartoon"}'
    with pytest.raises(RuntimeError, match="3 ครั้ง"):
        N.retry_structured_gpt_reply(
            sender, label="มุมกล้อง", attempts=3,
            valid=lambda obj: obj.get("camera") in N._CAMERA_REPAIR_LABELS)
    assert calls == [1, 2, 3]


def test_transport_exception_is_not_replayed():
    calls = []
    def sender(attempt):
        calls.append(attempt)
        raise TimeoutError("possible accepted cloud request")
    with pytest.raises(TimeoutError):
        N.retry_structured_gpt_reply(sender, label="มุมกล้อง", attempts=3)
    assert calls == [1]
