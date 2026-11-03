"""Stop must release the real local HTTP wait before Auto takes the same GPT queue again."""
import json
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
import urllib.request

import pytest
from test_video_auto_scene_provider import N, load, Widget
import snapgen_chrome_relay as chrome


def test_source_extension_bump_reloads_v1_0_29_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(chrome, "data_dir", lambda: tmp_path)
    target = tmp_path / "chrome_extension"
    target.mkdir()
    source = Path(chrome.__file__).with_name("chrome_ext") / "manifest.json"
    (target / "manifest.json").write_bytes(source.read_bytes())
    assert chrome._newer_on_disk("1.0.29")
    assert not chrome._newer_on_disk("1.0.30")


def test_stop_cancels_http_wait_and_next_auto_run_takes_the_same_queue(monkeypatch):
    relay = chrome._Relay()
    relay.token = "test-token"
    relay.last_seen = time.time()
    monkeypatch.setattr(chrome, "RELAY", relay)
    server = ThreadingHTTPServer(("127.0.0.1", 0), chrome._Handler)
    server.daemon_threads = True
    relay.port = server.server_port
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    state = {"stop": False, "detail": "seed story"}
    queue = threading.Lock()
    scope = dict(vars(N), state=state, g={"_bridge_queue_lock": queue},
                 check_stop=lambda: None, ui=lambda fn, *args: fn(*args), detail_var=Widget(),
                 work_dir_name="Auto", log=lambda *_: None)
    queued = load(scope, "queued_bridge", parent="_build")
    received = []

    def extension():
        first = relay.next_job(3)
        received.append(first)
        state["stop"] = True
        second = relay.next_job(5)
        received.append(second)
        if second:
            relay.finish({"id": second["id"], "text": "OK"})

    def send():
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/test-token/v1/chat/completions",
            data=json.dumps({"messages": [{"role": "user", "content": "seed"}]}).encode(),
            headers={"Content-Type": "application/json"})
        N.stamp_bridge_operation(request)
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read())

    extension_thread = threading.Thread(target=extension)
    extension_thread.start()
    try:
        with pytest.raises(N.Stopped):
            queued(send)
        deadline = time.monotonic() + 2
        while queue.locked() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not queue.locked(), "cancelled HTTP worker still holds Auto's queue"
        assert not relay.waiting and not relay.pending
        assert not relay.progress({"id": received[0]["id"]})
        state["stop"] = False
        assert queued(send)["text"] == "OK"
        extension_thread.join(2)
        assert len(received) == 2 and received[0]["operation_id"] != received[1]["operation_id"]
        assert not queue.locked() and not relay.waiting and not relay.pending
    finally:
        server.shutdown()
        server.server_close()
        extension_thread.join(6)


def test_cancel_before_http_arrives_does_not_enqueue_late_work(monkeypatch):
    relay = chrome._Relay()
    monkeypatch.setattr(relay, "status", lambda: {"connected": True})
    relay.cancel("stopped-operation")
    assert "cancelled" in relay.run({"operation_id": "stopped-operation", "type": "chat"})["error"]
    assert not relay.pending and not relay.waiting


def test_normal_progress_is_not_mislabeled_as_a_sent_429():
    relay = chrome._Relay()
    relay.waiting["job"] = {"activity_at": 0, "phase": "queued"}
    assert relay.progress({"id": "job", "phase": "opening"})
    assert relay.status()["active_phase"] == "opening"
    assert not relay.waiting["job"].get("rate_limited")
    assert relay.progress({"id": "job", "retry_after": 30})
    assert relay.waiting["job"]["rate_limited"]
