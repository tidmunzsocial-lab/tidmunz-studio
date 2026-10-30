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
    ([404, 200], 1, 2, False), ([404, 404, 404], 0, 3, True), ([403], 0, 1, False)])
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
 return {status,ok:status===200,json:async()=>({mapping:{}})};
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
