# -*- coding: utf-8 -*-
"""The footer reflects only the real extension heartbeat, not GPT image jobs."""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
from snapgen_followup_footer import label_for_followup
from snapgen_chrome_relay import _Relay


class FollowupFooterTests(unittest.TestCase):
    def test_missing_extension_heartbeat_never_claims_active(self):
        text, colour = label_for_followup(None)
        self.assertIn("ไม่พบข้อมูล", text)
        self.assertEqual(colour, "#9E9E9E")

    def test_existing_image_generation_does_not_turn_on_monitor(self):
        text, _ = label_for_followup({"enabled": False, "alarm_active": False,
                                      "phase": "idle", "next_at": 0})
        self.assertIn("ยังไม่เปิดติดตาม", text)

    def test_active_chrome_alarm_shows_remaining_and_configured_minutes(self):
        t = 1_800_000_000_000
        text, colour = label_for_followup(
            {"enabled": True, "alarm_active": True, "phase": "idle",
             "next_at": t + 4 * 60000, "interval_minutes": 15},
            now_ms=t)
        self.assertIn("GPT ตรวจอีก 4 นาที", text)
        self.assertIn("รอบ 15 นาที", text)
        self.assertEqual(colour, "#4CAF50")

    def test_missing_alarm_cannot_be_green(self):
        text, colour = label_for_followup(
            {"enabled": True, "alarm_active": False, "phase": "idle",
             "next_at": 1_800_000_300_000, "interval_minutes": 5},
            now_ms=1_800_000_000_000)
        self.assertIn("ไม่พบ Alarm", text)
        self.assertNotEqual(colour, "#4CAF50")

    def test_checking_is_distinct_from_creating_media(self):
        text, colour = label_for_followup(
            {"enabled": True, "alarm_active": True, "checking": True,
             "phase": "idle"}, now_ms=1_800_000_000_000)
        self.assertIn("กำลังตรวจความคืบหน้า", text)
        self.assertNotIn("กำลังทำงาน", text)
        self.assertNotEqual(colour, "#4CAF50")

    def test_sound_effect_selector_stops_monitor(self):
        text, colour = label_for_followup(
            {"enabled": False, "stop_requested": True,
             "phase": "awaiting_effect_selection"})
        self.assertIn("ถึงหน้าเลือกเสียง", text)
        self.assertIn("หยุดแล้ว", text)
        self.assertNotEqual(colour, "#4CAF50")

    def test_authenticated_relay_endpoint_accepts_only_extension_reports(self):
        import json
        import threading
        import urllib.error
        import urllib.request
        import snapgen_chrome_relay as relay_mod
        from http.server import ThreadingHTTPServer

        previous = relay_mod.RELAY
        relay_mod.RELAY = _Relay()
        relay_mod.RELAY.token = "test-only-not-a-real-token"
        server = ThreadingHTTPServer(("127.0.0.1", 0), relay_mod._Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}/followup/status"
            with self.assertRaises(urllib.error.HTTPError) as bad:
                urllib.request.urlopen(base, timeout=3)
            self.assertEqual(bad.exception.code, 403)
            payload = {"enabled": True, "alarm_active": True, "phase": "idle",
                       "next_at": 1800000000000, "interval_minutes": 15}
            url = base + "?token=test-only-not-a-real-token"
            request = urllib.request.Request(
                url, data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=3) as response:
                self.assertTrue(json.load(response)["ok"])
            with urllib.request.urlopen(url, timeout=3) as response:
                observed = json.load(response)
            self.assertTrue(observed["enabled"])
            self.assertEqual(observed["interval_minutes"], 15)
            self.assertFalse(observed["checking"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
            relay_mod.RELAY = previous

    def test_in_memory_relay_stales_out(self):
        relay = _Relay()
        relay.update_followup({"enabled": True, "alarm_active": True,
                               "phase": "idle", "next_at": 1_800_000_000_000,
                               "interval_minutes": 10})
        self.assertTrue(relay.followup_snapshot()["enabled"])
        relay.followup_heartbeat = time.monotonic() - 91
        self.assertIsNone(relay.followup_snapshot())


if __name__ == "__main__":
    unittest.main()
