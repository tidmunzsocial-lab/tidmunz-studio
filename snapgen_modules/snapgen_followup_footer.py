"""Format the *existing Chrome extension* follow-up status; no watcher or timer is created.

The local Chrome relay receives an authenticated heartbeat from followup.js.
This module only renders it in the application's footer.
"""
from __future__ import annotations

import math
import time


def label_for_followup(status: dict | None, *, now_ms: int | None = None) -> tuple[str, str]:
    if not status:
        return "ติดตาม: ไม่เชื่อมต่อ", "#9E9E9E"
    now = int(time.time() * 1000) if now_ms is None else int(now_ms)
    enabled = bool(status.get("enabled"))
    phase = str(status.get("phase") or "")
    if phase == "awaiting_effect_selection":
        return "ติดตาม: ถึงหน้าเลือกเสียง", "#9E9E9E"
    if phase == "uncertain":
        return "ติดตาม: รอตรวจสอบ", "#FFC107"
    if not enabled:
        return ("ติดตาม: หยุด" if status.get("stop_requested") else
                "ติดตาม: ปิด"), "#9E9E9E"
    if not status.get("alarm_active"):
        return "ติดตาม: ไม่พร้อม", "#FFC107"
    if status.get("checking") or phase == "sending":
        return "ติดตาม: กำลังส่งตรวจ", "#FFC107"
    if status.get("tool_state") == "awaiting_proof":
        return "ติดตาม: รอ GPT เรียกบอท", "#FFC107"
    if status.get("tool_state") == "not_verified":
        return "ติดตาม: บอทยังไม่ยืนยัน", "#FFC107"
    if status.get("tool_state") == "repair_unverified":
        return "ติดตาม: รอตรวจผลแก้", "#FFC107"
    try:
        next_at = int(status.get("next_at") or 0)
        interval = int(status.get("interval_minutes") or 0)
    except (TypeError, ValueError):
        next_at = interval = 0
    if next_at <= 0:
        return "ติดตาม: รอนัดตรวจ", "#FFC107"
    remaining = max(0, math.ceil((next_at - now) / 60000))
    if remaining == 0:
        return "ติดตาม: ถึงรอบตรวจ", "#FFC107"
    return f"ติดตาม: อีก {remaining} นาที", "#4CAF50"
