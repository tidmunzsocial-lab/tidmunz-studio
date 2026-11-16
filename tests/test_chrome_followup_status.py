"""Tests the authenticated relay's read-only project status projection without live tokens."""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
import snapgen_chrome_relay as relay


class ProjectMonitorStatusTests(unittest.TestCase):
    def test_native_audio_selector_signal_and_secret_redaction(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "mobile_web_token.txt").write_text("local-test-only", encoding="utf-8")
            snapshot = {
                "ready": True,
                "auto": {
                    "title": "Test Auto",
                    "busy": True, "stage": "ตัดต่อ", "detail": "เลือกเสียง",
                    "shots": [{"image": {"id": "picture"}, "clip": True},
                              {"image": None, "clip": False}],
                    "video": None,
                    "effect_review_pending": True,
                }
            }
            payload = io.BytesIO(json.dumps(snapshot, ensure_ascii=False).encode("utf-8"))
            with mock.patch.object(relay, "data_dir", return_value=root), \
                 mock.patch("urllib.request.urlopen", return_value=payload) as http, \
                 mock.patch("socket.gethostname", return_value="TEST-WORKSTATION"):
                result = relay.project_monitor_status()
            self.assertTrue(result["ready"])
            self.assertEqual(result["story"], "Test Auto")
            self.assertEqual(result["host"], "TEST-WORKSTATION")
            self.assertEqual(result["total"], 2)
            self.assertEqual(result["images"], 1)
            self.assertEqual(result["clips"], 1)
            self.assertTrue(result["effect_review_pending"])
            self.assertFalse(result["complete"])
            self.assertNotIn("local-test-only", json.dumps(result))
            self.assertIn("127.0.0.1:8765/api/status", http.call_args.args[0])
            self.assertEqual(http.call_args.kwargs["timeout"], 3)

    def test_reject_missing_auto_story(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "mobile_web_token.txt").write_text("test-token", encoding="utf-8")
            payload = io.BytesIO(b'{"ready":true,"auto":{}}')
            with mock.patch.object(relay, "data_dir", return_value=root), \
                 mock.patch("urllib.request.urlopen", return_value=payload):
                with self.assertRaisesRegex(RuntimeError, "No active Auto"):
                    relay.project_monitor_status()


if __name__ == "__main__":
    unittest.main()
