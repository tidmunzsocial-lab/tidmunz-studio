"""Regression guards for fresh-project 20-second narration planning."""
import inspect
from test_video_auto_scene_provider import N


def test_economy_plan_merges_short_narration_without_spending_video_credit():
    segments = [
        {"start": float(i * 5), "end": float((i + 1) * 5), "text": f"event {i}"}
        for i in range(8)
    ]
    normal = N.video_shots(segments)
    economy = N.video_shots(segments, N.ECONOMY_TARGET, N.ECONOMY_LIMIT)
    assert len(normal) == 4
    assert len(economy) == 2
    assert max(N.segment_durations([x["start"] for x in economy], 40)) <= 20


def test_economy_prompt_requires_visual_audio_alignment_not_blank_slow_motion():
    note = N.ECONOMY_NOTE
    assert "ภาพไม่ต้องตรงทุกประโยค" not in note
    assert "ห้ามยืดภาพคนนั่งนิ่ง" in note
    assert "ใช้คลิปที่ยิง AI ให้น้อยที่สุด" in note
    assert "ห้ามสโลว์" in note
    source = inspect.getsource(N.video_plan_request)
    assert "ห้ามให้ภาพค้างอยู่ที่เหตุการณ์ก่อนหน้า" in source
