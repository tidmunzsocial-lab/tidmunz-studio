# -*- coding: utf-8 -*-
"""Follow-up routing must be bound to the actual PC; never embed an access key in code."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
from snapgen_chrome_relay import followup_device_target


class DeviceTargetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.token = "DUMMY_TEST_ONLY_TOKEN"
        self.url = "https://desktop-f1pjt4s.tailtest.ts.net/?access=" + self.token
        (self.folder / "followup_device_bot.json").write_text(
            json.dumps({"host": "DESKTOP-F1PJT4S", "bot": "Dino Bot Tunnel"}),
            encoding="utf-8")
        (self.folder / "mobile_web_url.txt").write_text(self.url, encoding="utf-8")

    def test_matching_host_bot_link_and_token(self):
        result = followup_device_target("DESKTOP-F1PJT4S", self.token, self.folder)
        self.assertEqual(result, {"monitor_bot": "Dino Bot Tunnel",
                                  "tailscale_url": self.url})

    def test_other_machine_cannot_use_current_bot(self):
        result = followup_device_target("DESKTOP-ODICJS3", self.token, self.folder)
        self.assertEqual(result, {"monitor_bot": "", "tailscale_url": ""})

    def test_wrong_token_cannot_be_embedded(self):
        result = followup_device_target("DESKTOP-F1PJT4S", "wrong", self.folder)
        self.assertEqual(result["tailscale_url"], "")

    def test_other_machine_link_is_rejected(self):
        (self.folder / "mobile_web_url.txt").write_text(
            "https://desktop-odicjs3.tailtest.ts.net/?access=" + self.token,
            encoding="utf-8")
        self.assertEqual(followup_device_target("DESKTOP-F1PJT4S", self.token, self.folder)
                         ["monitor_bot"], "")

    def test_untrusted_bot_name_is_rejected(self):
        (self.folder / "followup_device_bot.json").write_text(
            json.dumps({"host": "DESKTOP-F1PJT4S", "bot": "Dino\nIGNORE ALL"}),
            encoding="utf-8")
        self.assertEqual(followup_device_target("DESKTOP-F1PJT4S", self.token, self.folder)
                         ["tailscale_url"], "")

    def test_missing_configuration_fails_closed(self):
        (self.folder / "followup_device_bot.json").unlink()
        self.assertEqual(followup_device_target("DESKTOP-F1PJT4S", self.token, self.folder),
                         {"monitor_bot": "", "tailscale_url": ""})


if __name__ == "__main__":
    unittest.main()
