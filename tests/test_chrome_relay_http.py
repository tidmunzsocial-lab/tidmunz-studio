"""HTTP integration: the existing Chrome relay serves authenticated, read-only Auto status."""
import json
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
import snapgen_chrome_relay as bridge


class AuthenticatedMonitorHttpTests(unittest.TestCase):
    def test_monitor_status_does_not_accept_missing_or_wrong_token(self):
        old_token = bridge.RELAY.token
        bridge.RELAY.token = "isolated-test-only-secret"
        server = ThreadingHTTPServer(("127.0.0.1", 0), bridge._Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:" + str(server.server_port) + "/monitor/status"
        try:
            with mock.patch.object(bridge, "project_monitor_status", return_value={
                "ready": True, "story": "isolated auto", "host": "TEST-MACHINE",
                "effect_review_pending": True,
            }) as status:
                for url in (base, base + "?token=wrong"):
                    with self.assertRaises(HTTPError) as caught:
                        urlopen(url, timeout=2)
                    self.assertEqual(caught.exception.code, 403)
                self.assertEqual(status.call_count, 0)
                from urllib.parse import quote
                with urlopen(base + "?token=" + quote(bridge.RELAY.token, safe=""), timeout=2) as res:
                    self.assertEqual(res.status, 200)
                    payload = json.load(res)
                self.assertTrue(payload["effect_review_pending"])
                self.assertEqual(payload["story"], "isolated auto")
                status.assert_called_once_with()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
            bridge.RELAY.token = old_token


if __name__ == "__main__":
    unittest.main()
