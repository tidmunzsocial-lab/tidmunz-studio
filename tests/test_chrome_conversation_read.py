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


def test_extension_attaches_real_text_file_before_sending():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    functions = source[source.index("async function pageSend(job)"):source.index("async function pagePoll(kind, state)")]
    harness = r'''
let attached=0, clicks=0, names=[];
const messages=[{id:'old-user',role:'user',text:'old'},{id:'old-assistant',role:'assistant',text:'old reply'}];
const nodes=()=>messages.map(m=>({innerText:m.text,textContent:m.text,
 getAttribute:k=>k==='data-message-id'?m.id:m.role}));
const removeButtons=()=>Array.from({length:attached},()=>({getAttribute:k=>k==='aria-label'?'Remove attachment':''}));
const input={multiple:true,accept:'',files:[],dispatchEvent:()=>{attached=input.files.length;}};
const editor={isConnected:true,innerText:'',textContent:'',closest:()=>form,focus(){}};
const send={disabled:false,isConnected:true,click(){clicks++;messages.push({id:'new-user',role:'user',text:editor.innerText});}};
const form={isConnected:true,querySelectorAll:s=>s==='button'?removeButtons():[],querySelector:s=>s==='button[type="submit"]'?send:null};
global.location={pathname:'/c/existing'};
global.setTimeout=fn=>{fn();return 0;};
global.Event=class{constructor(type,opts){this.type=type;this.opts=opts;}};
global.File=class{constructor(parts,name,opts){this.parts=parts;this.name=name;this.type=opts.type;names.push(name);}};
global.DataTransfer=class{constructor(){const list=[];this.items={add:f=>list.push(f)};this.files=list;}};
global.atob=s=>Buffer.from(s,'base64').toString('binary');
global.document={body:{innerText:''},activeElement:editor,visibilityState:'visible',hasFocus:()=>true,
 querySelectorAll:s=>s.includes('data-message-id')?nodes():(s==='input[type=file]'?[input]:[]),
 querySelector:()=>editor,
 execCommand:(cmd,_show,value)=>{if(cmd==='selectAll')editor.innerText='';if(cmd==='insertText')editor.innerText=value;return true;}
};
global.fetch=async()=>{throw Error('loaded chat must not use fetch');};
const encoded=Buffer.from('story context','utf8').toString('base64');
pageSend({type:'chat',conversation_id:'existing',prompt:'read attachment',images:[],
 files:[{filename:'story_context.txt',mime_type:'text/plain',file_data:encoded}]}).then(result=>
 console.log(JSON.stringify({result,attached,clicks,names})))
 .catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run([node, "-e", functions + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["result"]["ok"] is True
    assert data["attached"] == data["clicks"] == 1
    assert data["names"] == ["story_context.txt"]


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
const editor = {isConnected:true, innerText:'', textContent:'', closest:()=>form, focus:()=>{}};
global.document = {querySelector:()=>editor,execCommand:(cmd,_show,value)=>{
 if(cmd==='selectAll')editor.innerText='';
 if(cmd==='insertText')editor.innerText=value;
}};
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
        relay.progress({"id": job["id"], "retry_after": 30})

    worker = threading.Thread(target=extension)
    worker.start()
    result = relay.run({"type": "chat", "prompt": "already sent"})
    worker.join()
    assert result["provider_status"] == 429 and result["send_state"] == "sent"
    assert not relay.pending and not relay.waiting


def test_loaded_chat_can_send_text_without_private_conversation_reads():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    functions = source[source.index("async function pageNodes("):source.index("async function pagePoll(")]
    harness = r'''
let clicks=0, apiReads=0;
global.location={pathname:'/c/existing'};
global.setTimeout=fn=>{fn();return 0;};
const messages=['user','assistant'].map((role,i)=>({getAttribute:k=>k==='data-message-id'?'old-'+i:role}));
const send={disabled:false,click:()=>{clicks++;messages.push({textContent:'write video JSON',getAttribute:k=>k==='data-message-id'?'sent-user':'user'});}};
const form={isConnected:true,querySelectorAll:()=>[],querySelector:s=>s==='button[type="submit"]'?send:null};
const editor={isConnected:true,innerText:'',textContent:'',closest:()=>form,focus:()=>{}};
global.document={querySelectorAll:()=>messages,querySelector:()=>editor,execCommand:(cmd,_show,value)=>{
 if(cmd==='selectAll')editor.innerText='';
 if(cmd==='insertText')editor.innerText=value;
}};
global.fetch=async url=>{
 apiReads++;throw Error('UI text jobs should not need any private fetch for a loaded existing chat');
};
(async()=>{
 const known=await pageNodes('existing','chat');
 const result=await pageSend({type:'chat',conversation_id:'existing',prompt:'write video JSON',images:[]});
 console.log(JSON.stringify({known,result,clicks,apiReads}));
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run([node, "-e", functions + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["clicks"] == 1 and data["apiReads"] == 0
    assert data["result"]["dom_mode"] is True
    assert data["result"]["user_message_id"] == "sent-user"
    assert data["result"]["dom_before"] == data["known"] == ["old-0", "old-1"]


@pytest.mark.parametrize("clear_draft", [False, True])
def test_text_send_is_never_repeated_without_confirmation(clear_draft):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    functions = source[source.index("async function pageNodes("):source.index("async function pagePoll(")]
    harness = r'''
let clicks=0;
const clearDraft=CLEAR_DRAFT;
const messages=[
 {id:'old-user',role:'user',text:'old'},
 {id:'old-assistant',role:'assistant',text:'old reply'}
].map(m=>({textContent:m.text,getAttribute:k=>k==='data-message-id'?m.id:m.role}));
const editor={isConnected:true,innerText:'',textContent:'',closest:()=>form,focus(){}};
const send={disabled:false,click(){
 clicks++;
 if(clearDraft) editor.innerText='';
}};
const form={isConnected:true,querySelectorAll:()=>[],querySelector:s=>s==='button[type="submit"]'?send:null};
global.location={pathname:'/c/existing'};
global.setTimeout=fn=>{fn();return 0;};
global.document={
 querySelectorAll:s=>s.includes('data-message-id')?messages:[],
 querySelector:()=>editor,
 execCommand:(cmd,_show,value)=>{if(cmd==='selectAll')editor.innerText='';if(cmd==='insertText')editor.innerText=value;}
};
global.fetch=async()=>{throw Error('loaded chat must use the DOM path');};
pageSend({type:'chat',conversation_id:'existing',prompt:'new plan prompt',images:[]}).then(result=>
 console.log(JSON.stringify({result,clicks})))
 .catch(e=>{console.error(e);process.exitCode=1});
'''.replace("CLEAR_DRAFT", str(clear_draft).lower())
    result = subprocess.run([node, "-e", functions + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["clicks"] == 1
    assert data["result"]["send_state"] == "unknown"
    assert "no reply wait started" in data["result"]["error"]
    diagnostics = data["result"]["delivery_debug"]
    assert diagnostics["send_clicks"] == 1
    assert all(type(value) in (int, bool) for value in diagnostics.values())
    assert "new plan prompt" not in data["result"]["error"]


def test_text_send_confirmation_ignores_rendered_whitespace_and_invisible_unicode():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    functions = source[source.index("async function pageNodes("):source.index("async function pagePoll(")]
    harness = r'''
let clicks=0;
const messages=[
 {id:'old-user',role:'user',text:'old'},
 {id:'old-assistant',role:'assistant',text:'old reply'}
].map(m=>({innerText:m.text,getAttribute:k=>k==='data-message-id'?m.id:m.role}));
const editor={isConnected:true,innerText:'',textContent:'',closest:()=>form,focus(){}};
const send={disabled:false,click(){
 clicks++;
 if(clicks===1){
   messages.push({innerText:'new\nplan\u200b  prompt',getAttribute:k=>k==='data-message-id'?'sent-user':'user'});
   editor.innerText='';
 }
}};
const form={isConnected:true,querySelectorAll:()=>[],querySelector:s=>s==='button[type="submit"]'?send:null};
global.location={pathname:'/c/existing'};
global.setTimeout=fn=>{fn();return 0;};
global.document={querySelectorAll:s=>s.includes('data-message-id')?messages:[],querySelector:()=>editor,
 execCommand:(cmd,_show,value)=>{if(cmd==='selectAll')editor.innerText='';if(cmd==='insertText')editor.innerText=value;}};
global.fetch=async()=>{throw Error('loaded chat must use the DOM path');};
pageSend({type:'chat',conversation_id:'existing',prompt:'new plan prompt',images:[]}).then(result=>
 console.log(JSON.stringify({result,clicks}))).catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run([node, "-e", functions + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["clicks"] == 1
    assert data["result"]["user_message_id"] == "sent-user"


def test_oversized_prompt_toast_is_reported_as_definite_not_sent():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    functions = source[source.index("async function pageNodes("):source.index("async function pagePoll(")]
    harness = r'''
let clicks=0, bodyText='ChatGPT';
const messages=['user','assistant'].map((role,i)=>({innerText:'old',getAttribute:k=>k==='data-message-id'?'old-'+i:role}));
const alerts=[];
const send={disabled:false,click(){clicks++;bodyText+='\nข้อความที่คุณส่งยาวเกินไป โปรดแก้ไขแล้วส่งอีกครั้ง';
 alerts.push({innerText:'ข้อความที่คุณส่งยาวเกินไป โปรดแก้ไขแล้วส่งอีกครั้ง'});},getAttribute:()=>null};
const form={isConnected:true,querySelectorAll:()=>[send],querySelector:s=>s==='button[type="submit"]'?send:null};
const editor={isConnected:true,innerText:'',textContent:'',closest:()=>form,focus(){}};
global.location={pathname:'/c/existing'};
global.setTimeout=fn=>{fn();return 0;};
global.document={body:{get innerText(){return bodyText;}},activeElement:null,visibilityState:'visible',hasFocus:()=>true,
 querySelectorAll:s=>s.includes('data-message-id')?messages:s.includes('role="alert"')?alerts:[],
 querySelector:()=>editor,execCommand:(cmd,_show,value)=>{if(cmd==='selectAll')editor.innerText='';if(cmd==='insertText')editor.innerText=value;}};
global.fetch=async()=>{throw Error('loaded chat must use the DOM path');};
pageSend({type:'chat',conversation_id:'existing',prompt:'large image prompt',images:[]}).then(result=>
 console.log(JSON.stringify({result,clicks}))).catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run([node, "-e", functions + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["clicks"] == 1
    assert data["result"]["code"] == "prompt_too_long"
    assert data["result"]["send_state"] == "not_sent"


def test_run_job_does_not_resend_a_prompt_rejected_as_too_long():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    run = source[source.index("async function runJob("):source.index("// ── functions below")]
    harness = r'''
let sends=0,fresh=0,polls=0;
const JOB_LIMIT_MS=720000,sleep=async()=>{};
const workerTab=async()=>7,freshTab=async()=>{fresh++;return 8;},openPage=async id=>id;
function pageNodes(){} function pageSend(){} function pagePoll(){polls++;}
async function inPage(_id,fn){if(fn.name==='pageNodes')return [];
 if(fn.name==='pageSend'){sends++;return {error:'ChatGPT rejected the prompt because it was too long',
 code:'prompt_too_long',send_state:'not_sent'};} return fn();}
const relay=async()=>({active:true});
runJob({id:'job',type:'chat',conversation_id:'existing',prompt:'oversized'}).then(result=>
 console.log(JSON.stringify({result,sends,fresh,polls}))).catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run([node, "-e", run + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["sends"] == 1 and data["fresh"] == 0 and data["polls"] == 0
    assert data["result"]["code"] == "prompt_too_long"


def test_text_send_confirmation_survives_chatgpt_replacing_old_message_dom():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    functions = source[source.index("async function pageNodes("):source.index("async function pagePoll(")]
    harness = r'''
let clicks=0;
const message=(id,role,text)=>({innerText:text,getAttribute:k=>k==='data-message-id'?id:role});
let messages=[message('old-user','user','old'),message('old-assistant','assistant','old reply')];
const editor={isConnected:true,innerText:'',textContent:'',closest:()=>form,focus(){}};
const send={disabled:false,click(){
 clicks++;
 messages=[message('sent-user','user','new plan prompt')];
 editor.innerText='';
}};
const form={isConnected:true,querySelectorAll:()=>[],querySelector:s=>s==='button[type="submit"]'?send:null};
global.location={pathname:'/c/existing'};
global.setTimeout=fn=>{fn();return 0;};
global.document={querySelectorAll:s=>s.includes('data-message-id')?messages:[],querySelector:()=>editor,
 execCommand:(cmd,_show,value)=>{if(cmd==='selectAll')editor.innerText='';if(cmd==='insertText')editor.innerText=value;}};
global.fetch=async()=>{throw Error('loaded chat must use the DOM path');};
pageSend({type:'chat',conversation_id:'existing',prompt:'new plan prompt',images:[]}).then(result=>
 console.log(JSON.stringify({result,clicks}))).catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run([node, "-e", functions + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["clicks"] == 1
    assert data["result"]["user_message_id"] == "sent-user"


def test_run_job_does_not_poll_gpt_after_an_unconfirmed_send():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    run = source[source.index("async function runJob("):source.index("// ── functions below")]
    harness = r'''
let polls=0;
const JOB_LIMIT_MS=720000, sleep=async()=>{};
const workerTab=async()=>7, openPage=async id=>id;
function pageNodes(){} function pageSend(){} function pagePoll(){polls++;}
async function inPage(_id,fn){
 if(fn.name==='pageNodes')return ['old-user','old-assistant'];
 if(fn.name==='pageSend')return {error:'ChatGPT page did not answer: prompt was not confirmed'};
 return fn();
}
const relay=async()=>({active:true});
runJob({id:'job',type:'chat',conversation_id:'existing',prompt:'plan'}).then(result=>
 console.log(JSON.stringify({result,polls})))
 .catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run([node, "-e", run + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["polls"] == 0
    assert "not confirmed" in data["result"]["error"]


def test_unconfirmed_prompt_is_unknown_and_never_clicked_twice():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    page_send = source[source.index("async function pageSend(job)"):source.index("async function pagePoll(kind, state)")]
    harness = r'''
let clicks=0;
global.location={pathname:'/c/existing'};
global.setTimeout=fn=>{fn();return 0;};
const messages=['user','assistant'].map((role,i)=>({
 getAttribute:k=>k==='data-message-id'?'old-'+i:role
}));
const send={disabled:false,click:()=>clicks++,getAttribute:()=>null};
const form={isConnected:true,querySelectorAll:()=>[send],
 querySelector:s=>s==='button[type="submit"]'?send:null};
const editor={isConnected:true,innerText:'',textContent:'',closest:()=>form,focus:()=>{document.activeElement=editor;}};
global.document={activeElement:null,visibilityState:'visible',hasFocus:()=>true,
 querySelectorAll:s=>s.includes('data-message-id')?messages:[],querySelector:()=>editor,
 execCommand:(cmd,_show,value)=>{if(cmd==='selectAll')editor.innerText='';if(cmd==='insertText')editor.innerText=value;}};
pageSend({type:'chat',conversation_id:'existing',prompt:'plan',images:[]}).then(result=>
 console.log(JSON.stringify({result,clicks}))).catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run([node, "-e", page_send + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["clicks"] == 1
    assert data["result"]["send_state"] == "unknown"
    assert data["result"]["delivery_debug"]["send_clicks"] == 1
    assert data["result"]["delivery_debug"]["draft_matches"] is True


@pytest.mark.parametrize("accepted,status,expected_state,expected_reads", [
    (False, 200, "not_sent", 2),
    (True, 200, "sent", 1),
    (False, 429, "unknown", 1),
])
def test_delivery_verification_requires_fresh_authoritative_reads(accepted, status, expected_state, expected_reads):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    function = source[source.index("async function pageVerifyDelivery("):source.index("async function pageSend(job)")]
    harness = r'''
let reads=0;
global.location={pathname:'/c/existing'};
global.setTimeout=fn=>{fn();return 0;};
const send={disabled:false,getAttribute:()=>null};
const form={isConnected:true,querySelectorAll:()=>[send],querySelector:s=>s==='button[type="submit"]'?send:null};
const editor={isConnected:true,innerText:'plan',textContent:'plan',closest:()=>form};
global.document={querySelector:()=>editor,querySelectorAll:()=>[]};
global.fetch=async(url,options)=>{
 if(url==='/api/auth/session')return {json:async()=>({accessToken:'test'})};
 if(options.cache!=='no-store')throw Error('delivery read must not use cache');
 reads++;
 if(STATUS!==200)return {ok:false,status:STATUS};
 const mapping={
  'old-user':{message:{author:{role:'user'},content:{parts:['plan']}}},
  'old-assistant':{message:{author:{role:'assistant'},content:{parts:['old reply']}}}
 };
 if(ACCEPTED)mapping['new-user']={message:{author:{role:'user'},content:{parts:['plan']}}};
 return {ok:true,json:async()=>({mapping})};
};
pageVerifyDelivery({conversation_id:'existing',prompt:'plan',images:[]},['old-user','old-assistant']).then(result=>
 console.log(JSON.stringify({result,reads}))).catch(e=>{console.error(e);process.exitCode=1});
'''.replace("ACCEPTED", str(accepted).lower()).replace("STATUS", str(status))
    result = subprocess.run([node, "-e", function + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["result"]["state"] == expected_state
    assert data["reads"] == expected_reads


def test_delivery_verification_accepts_exact_new_dom_prompt_without_private_api_read():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    function = source[source.index("async function pageVerifyDelivery("):source.index("async function pageSend(job)")]
    harness = r'''
const old={getAttribute:k=>k==='data-message-id'?'old-user':'user',innerText:'plan'};
const fresh={getAttribute:k=>k==='data-message-id'?'new-user':'user',innerText:'plan'};
global.location={pathname:'/c/existing'};
global.document={querySelectorAll:()=>[old,fresh]};
global.fetch=async()=>{throw Error('the exact new DOM message is sufficient');};
pageVerifyDelivery({conversation_id:'existing',prompt:'plan',images:[]},['old-user']).then(result=>
 console.log(JSON.stringify(result))).catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run([node, "-e", function + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data == {"state": "sent", "user_message_id": "new-user"}


@pytest.mark.parametrize("verification,retry_expected", [("not_sent", True), ("unknown", False)])
def test_unknown_existing_chat_retries_only_after_verified_no_delivery(verification, retry_expected):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    run = source[source.index("async function runJob("):source.index("// ── functions below")]
    harness = r'''
let sends=0,polls=0,fresh=0,verifies=0,reads=0;
const JOB_LIMIT_MS=720000,sleep=async()=>{};
const workerTab=async()=>7, freshTab=async()=>{fresh++;return 8;}, openPage=async id=>id;
global.chrome={tabs:{get:async()=>({status:'complete'})}};
function pageNodes(){} function pageSend(){} function pageVerifyDelivery(){} function pagePoll(){}
async function inPage(_id,fn){
 if(fn.name==='pageNodes'){reads++;return ['old-user','old-assistant'];}
 if(fn.name==='pageSend'){
  sends++;
  return sends===1?{error:'prompt was not confirmed',send_state:'unknown',before:['old-user','old-assistant']}:
    {ok:true,before:['old-user','old-assistant'],oldPointers:[],conversation_id:'existing'};
 }
 if(fn.name==='pageVerifyDelivery'){verifies++;return {state:VERIFICATION};}
 if(fn.name==='pagePoll'){polls++;return {done:true,text:'recovered reply',conversation_id:'existing'};}
}
const relay=async()=>({active:true});
runJob({id:'job',type:'chat',conversation_id:'existing',prompt:'plan'}).then(result=>
 console.log(JSON.stringify({result,sends,polls,fresh,verifies,reads})))
 .catch(e=>{console.error(e);process.exitCode=1});
'''.replace("VERIFICATION", json.dumps(verification))
    result = subprocess.run([node, "-e", run + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["sends"] == (2 if retry_expected else 1)
    assert data["fresh"] == (1 if retry_expected else 0)
    assert data["verifies"] == 1 and data["reads"] >= 2
    assert data["polls"] == (1 if retry_expected else 0)
    if retry_expected:
        assert data["result"]["text"] == "recovered reply"
    else:
        assert data["result"]["send_state"] == "unknown"


def test_run_job_retries_proven_unsent_prompt_once_in_fresh_worker_tab():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    run = source[source.index("async function runJob("):source.index("// ── functions below")]
    harness = r'''
let sends=0,polls=0,fresh=0;
const opened=[];
const JOB_LIMIT_MS=720000,sleep=async()=>{};
const workerTab=async()=>7;
const freshTab=async(id,url,key)=>{fresh++;if(id!==7||key!=='workerTabId')throw Error('wrong worker');return 8;};
const openPage=async(id,url)=>{opened.push({id,url});return id;};
function pageNodes(){} function pageSend(){} function pagePoll(){}
global.chrome={tabs:{get:async()=>({status:'complete'})}};
const relay=async()=>({active:true});
async function inPage(_id,fn){
 if(fn.name==='pageNodes')return ['old-user','old-assistant'];
 if(fn.name==='pageSend'){
   sends++;
   return sends===1?{error:'composer did not submit',send_state:'not_sent'}:
     {ok:true,before:[],oldPointers:[],conversation_id:'existing'};
 }
 if(fn.name==='pagePoll'){polls++;return {done:true,text:'recovered reply',conversation_id:'existing'};}
}
runJob({id:'job',type:'chat',conversation_id:'existing',prompt:'plan'}).then(result=>
 console.log(JSON.stringify({result,sends,polls,fresh,opened})))
 .catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run([node, "-e", run + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["sends"] == 2 and data["fresh"] == 1 and data["polls"] == 1
    assert [item["id"] for item in data["opened"]] == [7, 8]
    assert data["result"]["text"] == "recovered reply"


def test_run_job_recovers_unknown_send_when_existing_chat_gains_messages():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    run = source[source.index("async function runJob("):source.index("// ── functions below")]
    harness = r'''
let sends=0, polls=0, reads=0;
const JOB_LIMIT_MS=720000, sleep=async()=>{};
const workerTab=async()=>7, openPage=async id=>id;
global.chrome={tabs:{get:async()=>({status:'complete'})}};
function pageNodes(){} function pageSend(){} function pageVerifyDelivery(){} function pagePoll(){}
async function inPage(_id,fn){
 if(fn.name==='pageNodes')return ++reads===1?['old-user','old-assistant']:['old-user','old-assistant','new-user'];
 if(fn.name==='pageSend'){sends++;return {error:'prompt was not confirmed',send_state:'unknown'};}
 if(fn.name==='pageVerifyDelivery')return {state:'sent',user_message_id:'new-user'};
 if(fn.name==='pagePoll'){polls++;return {done:true,text:'recovered reply',conversation_id:'existing'};}
}
const relay=async()=>({active:true});
runJob({id:'job',type:'chat',conversation_id:'existing',prompt:'plan'}).then(result=>
 console.log(JSON.stringify({result,sends,polls,reads})))
 .catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run([node, "-e", run + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["sends"] == data["polls"] == 1
    assert data["reads"] == 2
    assert data["result"]["text"] == "recovered reply"


@pytest.mark.parametrize("location,expected_polls", [
    ("https://chatgpt.com/c/12345678-1234-1234-1234-123456789abc", 1),
    ("https://chatgpt.com/", 0),
    ("https://example.invalid/c/12345678-1234-1234-1234-123456789abc", 0),
])
def test_unknown_new_chat_recovers_created_conversation_without_resending(location, expected_polls):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    run = source[source.index("async function runJob("):source.index("// ── functions below")]
    harness = r'''
let sends=0, polls=0, polledCid=null;
const JOB_LIMIT_MS=720000, sleep=async()=>{}, workerTab=async()=>7, openPage=async id=>id;
global.chrome={tabs:{get:async()=>({status:'complete',url:LOCATION})}};
function pageNodes(){} function pageSend(){} function pageVerifyDelivery(){} function pagePoll(){}
async function inPage(_id,fn,args){
 if(fn.name==='pageSend'){sends++;return {error:'prompt was not confirmed',send_state:'unknown'};}
 if(fn.name==='pageVerifyDelivery')return {state:'sent',user_message_id:'new-user'};
 if(fn.name==='pagePoll'){polls++;polledCid=args[1].cid;return {done:true,text:'new reply'};}
 throw Error('unexpected read');
}
const relay=async()=>({active:true});
runJob({id:'job',type:'chat',prompt:'whole story',conversation_id:null}).then(result=>
 console.log(JSON.stringify({result,sends,polls,polledCid}))).catch(e=>{console.error(e);process.exitCode=1});
'''.replace("LOCATION", json.dumps(location))
    result = subprocess.run([node, "-e", run + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["sends"] == 1 and data["polls"] == expected_polls
    if expected_polls:
        assert data["polledCid"] == "12345678-1234-1234-1234-123456789abc"
        assert data["result"]["text"] == "new reply"
    else:
        assert data["result"]["send_state"] == "unknown"


def test_text_reply_requires_new_id_and_stable_json_without_api_polling():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    function = source[source.index("async function pagePoll("):source.index("chrome.alarms.create")]
    harness = r'''
let text='{"shots":[{"video_prompt":"new"}]}', showNew=false;
const block={innerText:'json Copy '+text,querySelectorAll:()=>[{textContent:text}]};
const message=(id,role='assistant')=>({getAttribute:k=>k==='data-message-id'?id:role,querySelectorAll:()=>[block]});
global.location={pathname:'/c/existing'};
global.document={querySelectorAll:s=>s.includes('data-message-id')?
 [message('old'),message('sent-user','user'),...(showNew?[message('new')]:[])]:[]};
global.fetch=async()=>{throw Error('must not read the throttled API');};
(async()=>{
 const state={cid:'existing',idle:2,sentAt:Date.now()-10000,before:['old'],dom_before:['old'],dom_mode:true,user_message_id:'sent-user'};
 const old=await pagePoll('chat',state);
 showNew=true;
 const fresh=await pagePoll('chat',state);
 Object.assign(state,{dom_reply_id:fresh.dom_reply_id,dom_reply_text:fresh.dom_reply_text});
 const done=await pagePoll('chat',state);
 console.log(JSON.stringify({old,fresh,done}));
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run([node, "-e", function + harness], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["old"]["done"] is False and data["fresh"]["done"] is False
    assert data["done"]["done"] is True and data["done"]["message_id"] == "new"
    assert json.loads(data["done"]["text"])["shots"][0]["video_prompt"] == "new"
