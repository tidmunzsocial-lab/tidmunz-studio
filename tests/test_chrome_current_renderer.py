"""Regression tests for current ChatGPT text turns, with independent accounts/routes."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "snapgen_modules/chrome_ext/background.js"


@pytest.mark.parametrize("case", ["fresh", "continued", "stale", "wrong_route", "wrong_reply_route", "streaming", "other_account"])
def test_current_renderer_only_accepts_completed_fresh_reply_on_own_route(case):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = WORKER.read_text(encoding="utf-8")
    poll = source[source.index("async function pagePoll("):source.index("chrome.alarms.create(")]
    harness = r"""
const cidA='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const cidB='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const userId='cccccccc-cccc-4ccc-8ccc-cccccccccccc';
const replyId='dddddddd-dddd-4ddd-8ddd-dddddddddddd';
const oldId='eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee';
const accountB=CASE==='other_account';
const own=accountB?cidB:cidA;
global.location={pathname:'/c/'+(CASE==='wrong_route'?cidB:own)};
const unit={getAttribute:()=>userId};
const user={closest:()=>unit,compareDocumentPosition:()=>4};
const reply={getAttribute:k=>k==='data-chatgpt-selection-message-id'?replyId:CASE==='wrong_reply_route'?cidB:own,
 innerText:accountB?'ACCOUNT_B_READY':'STORY_READY',querySelectorAll:()=>[]};
const body={querySelectorAll:()=>[reply]};
const turn={querySelector:()=>body,getAttribute:()=>CASE==='streaming'?'streaming':'complete'};
global.document={querySelectorAll:s=>s==='[data-user-message-bubble]'?[user]:s==='[data-talvt-turn-state]'?[turn]:[]};
global.fetch=async()=>{throw Error('must not fetch while cooldown or route mismatch');};
const prior=CASE==='stale'?[userId,replyId]:CASE==='continued'?[oldId]:[];
pagePoll('chat',{cid:own,before:prior,dom_before:[],existing_chat:prior.length>0,sentAt:Date.now()-60000,
 api_read_at:Date.now(),user_message_id:null}).then(r=>console.log(JSON.stringify(r)));
""".replace("CASE", json.dumps(case))
    result = subprocess.run([node, "-e", poll + harness], capture_output=True, text=True, check=True, timeout=10)
    data = json.loads(result.stdout)
    assert data["done"] is (case in {"fresh", "continued", "other_account"})
    if data["done"]:
        assert data["source"] == "chatgpt_page_current_complete"
        assert data["conversation_id"] == ("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb" if case == "other_account" else "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        assert data["text"] == ("ACCOUNT_B_READY" if case == "other_account" else "STORY_READY")


def test_local_upgrade_keeps_optional_worker_and_device_config(monkeypatch, tmp_path):
    import sys
    sys.path.insert(0, str(ROOT / "snapgen_modules"))
    import snapgen_chrome_relay as relay
    source = WORKER.parent
    worker = WORKER.read_text(encoding="utf-8")
    installed = tmp_path / "installed"
    installed.mkdir()
    (installed / "manifest.json").write_text(json.dumps({"version": "1.0.62", "host_permissions": ["https://snapgen.ai/*"]}))
    (installed / "background.js").write_text(worker + "\n// optional provider dispatch\n", encoding="utf-8")
    (installed / "snapgen_web.js").write_text("optional provider code", encoding="utf-8")
    monkeypatch.setattr(relay, "extension_dir", lambda: installed)
    for port, token in [(8766, "device-a-test"), (8767, "device-b-test")]:
        relay._write_extension(source, token, port)
        assert json.loads((installed / "manifest.json").read_text()) == {"version":"1.0.63","host_permissions":["https://snapgen.ai/*"]}
        assert "optional provider dispatch" in (installed / "background.js").read_text(encoding="utf-8")
        assert (installed / "snapgen_web.js").read_text() == "optional provider code"
        config = (installed / "config.js").read_text()
        assert token in config and str(port) in config
        assert ("device-b-test" if token=="device-a-test" else "device-a-test") not in config
