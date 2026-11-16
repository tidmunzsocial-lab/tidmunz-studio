"""Format the *existing Chrome extension* follow-up status; no watcher or timer is created.

The local Chrome relay receives an authenticated heartbeat from followup.js.
This module only renders it in the application's footer.
"""
from __future__ import annotations

import math
import time


def label_for_followup(status: dict | None, *, now_ms: int | None = None) -> tuple[str, str]:
    if not status:
        return "สคริปต์ติดตาม: ไม่พบข้อมูลจากส่วนขยาย", "#9E9E9E"
    now = int(time.time() * 1000) if now_ms is None else int(now_ms)
    enabled = bool(status.get("enabled"))
    phase = str(status.get("phase") or "")
    if phase == "awaiting_effect_selection":
        return "สคริปต์ติดตาม: ถึงหน้าเลือกเสียง · หยุดแล้ว", "#9E9E9E"
    if phase == "uncertain":
        return "สคริปต์ติดตาม: หยุด · ต้องตรวจข้อความก่อน", "#FFC107"
    if not enabled:
        return ("สคริปต์ติดตาม: หยุดติดตาม" if status.get("stop_requested") else
                "สคริปต์ติดตาม: ยังไม่เปิดติดตาม"), "#9E9E9E"
    if not status.get("alarm_active"):
        return "สคริปต์ติดตาม: ยังไม่พร้อม · ไม่พบ Alarm", "#FFC107"
    if status.get("checking") or phase == "sending":
        return "สคริปต์ติดตาม: กำลังตรวจความคืบหน้า", "#FFC107"
    try:
        next_at = int(status.get("next_at") or 0)
        interval = int(status.get("interval_minutes") or 0)
    except (TypeError, ValueError):
        next_at = interval = 0
    if next_at <= 0:
        return "สคริปต์ติดตาม: เปิดอยู่ · ยังไม่ได้นัดตรวจ", "#FFC107"
    remaining = max(0, math.ceil((next_at - now) / 60000))
    if remaining == 0:
        return "สคริปต์ติดตาม: ถึงรอบตรวจ · รอ GPT", "#FFC107"
    if interval > 0:
        return f"เฝ้าติดตาม · นัด GPT ตรวจอีก {remaining} นาที (รอบ {interval} นาที)", "#4CAF50"
    return f"เฝ้าติดตาม · นัด GPT ตรวจอีก {remaining} นาที", "#4CAF50"
