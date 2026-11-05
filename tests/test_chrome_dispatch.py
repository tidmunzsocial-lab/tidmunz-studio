"""Execute production dispatch while quota fetches hang and while Auto cancels an in-page send."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


SOURCE = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()


def run_node(code):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    result = subprocess.run([node, "-e", code], capture_output=True, text=True, check=True, timeout=10)
    return json.loads(result.stdout)


def test_hung_account_requests_do_not_block_receiving_or_running_work():
    code = SOURCE[SOURCE.index("let account ="):SOURCE.index("// ── the ChatGPT tab")]
    data = run_node(code + r'''
let running=false, taken=0, sent=0, reloaded=false;
const sleep=async()=>{}, badge=()=>{}, isWorkerTab=()=>false;
global.setTimeout=()=>1; global.clearTimeout=()=>{};
global.fetch=()=>new Promise(()=>{});
global.chrome={storage:{local:{get:async()=>({})}},tabs:{query:async()=>[]},runtime:{
 getManifest:()=>({version:'1.0.23'}),reload:()=>{reloaded=true;}}};
const relay=async(path)=>{
 if(path.startsWith('/next')){taken++;return taken===1?{id:'job',type:'chat'}:{reload:true};}
 if(path==='/result'){sent++;return {ok:true};}
 throw Error('unexpected path');
};
const runJob=async()=>({text:'OK'});
loop().then(()=>console.log(JSON.stringify({taken,sent,reloaded,running})))
 .catch(e=>{console.error(e);process.exitCode=1});
''')
    assert data == {"taken": 2, "sent": 1, "reloaded": True, "running": False}


def test_account_timeout_aborts_the_fetch_instead_of_leaving_it_pending():
    code = SOURCE[SOURCE.index("async function accountJSON("):SOURCE.index("async function chatgptAccount(")]
    data = run_node(code + r'''
let cleared=false;
global.setTimeout=fn=>{queueMicrotask(fn);return 7;};
global.clearTimeout=()=>{cleared=true;};
global.fetch=(_url,opts)=>new Promise((_resolve,reject)=>{
 opts.signal.addEventListener('abort',()=>reject(new Error('aborted')));
});
accountJSON('https://example.invalid').then(()=>{throw Error('should abort');})
 .catch(e=>console.log(JSON.stringify({message:e.message,cleared})));
''')
    assert data == {"message": "aborted", "cleared": True}


@pytest.mark.parametrize("failed,expected_resets", [(True, 0), (False, 1)])
def test_failed_job_keeps_its_page_and_draft_for_inspection(failed, expected_resets):
    code = SOURCE[SOURCE.index("let account ="):SOURCE.index("// ── the ChatGPT tab")]
    data = run_node(code + r'''
let running=false, taken=0, resets=0;
const sleep=async()=>{}, badge=()=>{}, isWorkerTab=()=>false, workerTab=async()=>7;
global.setTimeout=()=>1; global.clearTimeout=()=>{};
global.fetch=()=>new Promise(()=>{});
global.chrome={storage:{local:{get:async()=>({workerTabId:7})}},tabs:{query:async()=>[],update:async()=>{resets++;}},runtime:{
 getManifest:()=>({version:'1.0.27'}),reload:()=>{}}};
const relay=async path=>path.startsWith('/next')?(++taken===1?{id:'job',type:'chat'}:{reload:true}):{ok:true};
const runJob=async()=>FAILED?{error:'unconfirmed'}:{text:'OK'};
loop().then(()=>console.log(JSON.stringify({resets}))).catch(e=>{console.error(e);process.exitCode=1});
'''.replace("FAILED", str(failed).lower()))
    assert data["resets"] == expected_resets


def test_cancel_aborts_the_dedicated_in_page_wait_without_replaying_send():
    code = SOURCE[SOURCE.index("async function runJob("):SOURCE.index("// ── functions below")]
    data = run_node(code + r'''
let heartbeat, cleared=false, active=true, sends=0, reloads=0, releaseSend, notify;
const ready=new Promise(resolve=>{notify=resolve;});
const CHAT_JOB_LIMIT_MS=180000; const JOB_LIMIT_MS=720000, sleep=async()=>{};
global.setInterval=fn=>{heartbeat=fn;return 7;};
global.clearInterval=()=>{cleared=true;};
global.chrome={tabs:{reload:async()=>{reloads++;releaseSend();}}};
const workerTab=async()=>7, openPage=async id=>id;
function pageNodes(){} function pageSend(){} function pagePoll(){throw Error('must not poll');}
const relay=async()=>({active});
async function inPage(_id,fn){
 if(fn.name==='pageNodes')return [];
 if(fn.name==='pageSend'){
  sends++;
  return new Promise((_resolve,reject)=>{releaseSend=()=>reject(Error('page reloaded'));notify();});
 }
 return fn();
}
(async()=>{
 const execution=runJob({id:'job',type:'chat',conversation_id:'existing'});
 await ready;active=false;await heartbeat();
 const result=await execution;
 console.log(JSON.stringify({result,sends,reloads,cleared}));
})().catch(e=>{console.error(e);process.exitCode=1});
''')
    assert "cancelled" in data["result"]["error"]
    assert data["sends"] == data["reloads"] == 1 and data["cleared"]


def test_late_heartbeat_from_finished_job_cannot_reload_the_next_jobs_tab():
    code = SOURCE[SOURCE.index("async function runJob("):SOURCE.index("// ── functions below")]
    data = run_node(code + r'''
let heartbeat, pendingBeat, finishBeat, reloads=0;
const JOB_LIMIT_MS=720000; const CHAT_JOB_LIMIT_MS=180000;
global.setInterval=fn=>{heartbeat=fn;return 1;};global.clearInterval=()=>{};
global.chrome={tabs:{get:async()=>({status:'complete'}),reload:async()=>{reloads++;}}};
const sleep=async()=>{if(!pendingBeat)pendingBeat=heartbeat();};
const workerTab=async()=>7,openPage=async id=>id;
function pageNodes(){} function pageSend(){} function pagePoll(){}
const relay=async(_path,body)=>body.phase?{active:true}:new Promise(resolve=>{finishBeat=resolve;});
async function inPage(_id,fn){
 if(fn.name==='pageNodes')return [];
 if(fn.name==='pageSend')return {ok:true,before:[],oldPointers:[]};
 return {done:true,text:'OK'};
}
(async()=>{
 const result=await runJob({id:'old-job',type:'chat',conversation_id:'existing'});
 finishBeat({active:false});await pendingBeat;
 console.log(JSON.stringify({result,reloads}));
})().catch(e=>{console.error(e);process.exitCode=1});
''')
    assert data["result"]["text"] == "OK" and data["reloads"] == 0
