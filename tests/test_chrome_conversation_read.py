"""Execute the extension's real page functions with controlled HTTP responses."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from test_chrome_api import api


@pytest.mark.parametrize("already_there", [False, True])
def test_navigation_waits_for_target_document_and_reuses_current_chat(already_there):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    function = source[source.index("async function openPage("):source.index("async function inPage(")]
    harness = r'''
const target='https://chatgpt.com/c/target';
let checks=0, navigations=0;
const initial=ALREADY ? target : 'https://chatgpt.com/c/old';
global.location=new URL(initial);
global.document={title:'ChatGPT',body:{innerText:''},querySelector:()=>({})};
global.chrome={tabs:{get:async()=>({url:initial}),update:async()=>{navigations++;}}};
const sleep=async()=>{};
async function inPage(id, fn, args){
 checks++;
 if(checks===2) global.location=new URL(target);
 return fn(...args);
}
openPage(7,target).then(id=>console.log(JSON.stringify({id,checks,navigations})))
 .catch(e=>{console.error(e);process.exitCode=1});
'''.replace("ALREADY", str(already_there).lower())
    result = subprocess.run([node, "-e", function + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data == {"id": 7, "checks": 1 if already_there else 2, "navigations": 0 if already_there else 1}


@pytest.mark.parametrize("statuses,clicks,reads,not_found", [
    ([404, 200], 1, 2, False), ([404, 404, 404], 0, 3, True), ([403], 0, 1, False), ([429], 0, 1, False)])
def test_extension_retries_reads_without_resending_or_mislabeling_403(statuses, clicks, reads, not_found):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    functions = source[source.index("async function pageSend(job)"):source.index("async function pagePoll(kind, state)")]
    harness = r'''
const statuses = STATUSES;
let clicks = 0, reads = 0;
global.setTimeout = fn => {fn(); return 0;};
const send = {disabled:false, click:()=>clicks++};
const form = {isConnected:true, querySelectorAll:()=>[], querySelector:s=>s==='button[type="submit"]'?send:null};
const editor = {isConnected:true, closest:()=>form, focus:()=>{}};
global.document = {querySelector:()=>editor,execCommand:()=>{}};
global.fetch = async (url, options) => {
 if(url==='/api/auth/session') return {json:async()=>({accessToken:'test'})};
 reads++;
 if(options.cache!=='no-store') throw Error('cached read');
 const status=statuses.shift();
 return {status,ok:status===200,headers:{get:()=> '75'},json:async()=>({mapping:{}})};
};
pageSend({conversation_id:'test-chat',prompt:'test',images:[]}).then(result=>{
 console.log(JSON.stringify({result,clicks,reads}));
}).catch(e=>{console.error(e);process.exitCode=1});
'''.replace("STATUSES", json.dumps(statuses))
    result = subprocess.run([node, "-e", functions + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["clicks"] == clicks and data["reads"] == reads
    assert bool(data["result"].get("not_found")) is not_found
    if statuses == [403]:
        assert data["result"]["provider_status"] == 403
        code, body = api.error_reply(data["result"])
        assert code == 403 and body["error"]["code"] == "chatgpt_conversation_access_denied"
    if statuses == [429]:
        assert data["result"]["send_state"] == "not_sent"
        assert data["result"]["retry_after"] == 75
        assert api.error_reply(data["result"])[0] == 429


def test_extension_429_after_send_waits_and_reads_same_reply_without_sending_again():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    run = source[source.index("async function runJob("):source.index("// ── functions below")]
    poll = source[source.index("async function pagePoll("):source.index("chrome.alarms.create")]
    harness = r'''
let now=100000, sends=0, reads=0, heartbeats=0;
Date.now=()=>now;
const JOB_LIMIT_MS=720000;
const sleep=async ms=>{now+=ms;};
const workerTab=async()=>7, openPage=async id=>id;
function pageNodes(){} function pageSend(){}
global.chrome={tabs:{get:async()=>({status:'complete'})}};
global.document={querySelectorAll:()=>[]}; global.location={pathname:'/c/test-chat'};
global.fetch=async url=>{
 if(url==='/api/auth/session') return {json:async()=>({accessToken:'test'})};
 reads++;
 if(reads===1) return {ok:false,status:429,headers:{get:()=> '900'}};
 return {ok:true,json:async()=>({current_node:'reply',mapping:{reply:{message:{
  author:{role:'assistant'},content:{content_type:'text',parts:['recovered']},create_time:1}}}})};
};
const relay=async(path,body)=>{if(path!=='/progress'||body.id!=='job')throw Error('wrong heartbeat');heartbeats++;return {active:true};};
async function inPage(id,fn,args){
 if(fn.name==='pageNodes') return [];
 if(fn.name==='pageSend'){sends++;return {ok:true,before:[],oldPointers:[]};}
 return fn(...args);
}
runJob({id:'job',type:'chat',conversation_id:'test-chat'}).then(result=>
 console.log(JSON.stringify({result,sends,reads,heartbeats,elapsed:now-100000})))
 .catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run([node, "-e", run + poll + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["result"]["text"] == "recovered"
    assert data["sends"] == 1 and data["reads"] == 2
    assert data["elapsed"] >= 900000 and data["heartbeats"] >= 180


def test_relay_heartbeat_keeps_existing_job_alive_without_requeue(monkeypatch):
    import threading
    import time
    import snapgen_chrome_relay as module
    relay = module._Relay()
    monkeypatch.setattr(relay, "status", lambda: {"connected": True})
    monkeypatch.setattr(module, "JOB_TIMEOUT", 0.08)
    jobs = []

    def extension():
        job = relay.next_job(1)
        jobs.append(job)
        for _ in range(8):
            time.sleep(0.025)
            assert relay.progress({"id": job["id"]})
        relay.finish({"id": job["id"], "text": "recovered"})

    worker = threading.Thread(target=extension)
    worker.start()
    result = relay.run({"type": "chat", "prompt": "same request"})
    worker.join()
    assert result["text"] == "recovered" and len(jobs) == 1
    assert not relay.pending and not relay.waiting
    assert not relay.progress({"id": "unknown"})


def test_lost_heartbeat_never_reports_the_submitted_prompt_as_unsent(monkeypatch):
    import threading
    import snapgen_chrome_relay as module
    relay = module._Relay()
    monkeypatch.setattr(relay, "status", lambda: {"connected": True})
    monkeypatch.setattr(module, "JOB_TIMEOUT", 0.05)

    def extension():
        job = relay.next_job(1)
        relay.progress({"id": job["id"]})

    worker = threading.Thread(target=extension)
    worker.start()
    result = relay.run({"type": "chat", "prompt": "already sent"})
    worker.join()
    assert result["provider_status"] == 429 and result["send_state"] == "sent"
    assert not relay.pending and not relay.waiting
