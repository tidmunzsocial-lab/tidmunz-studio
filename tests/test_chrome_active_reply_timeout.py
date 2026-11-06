"""Run real extension loop with virtual time; never contact ChatGPT."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("mode", ["slow", "stuck", "idle"])
def test_same_reply_recovery_is_bounded_without_resend(mode):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    code = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text()
    code = code[code.index("async function runJob("):code.index("// ── functions below")]
    harness = r'''
let now=0,sends=0,polls=0;
Date.now=()=>now;
const CHAT_JOB_LIMIT_MS=180000,JOB_LIMIT_MS=720000;
const sleep=async ms=>{now+=ms;};
const workerTab=async()=>7,openPage=async id=>id,relay=async()=>({active:true});
global.chrome={tabs:{get:async()=>({status:'complete'})}};
function pageNodes(){} function pageSend(){} function pagePoll(){}
async function inPage(id,fn,args){
 if(fn.name==='pageSend'){sends++;return {before:[],dom_before:[],user_message_id:'u'};}
 if(fn.name==='pagePoll'){
  polls++;
  if(MODE==='slow'&&now>=240000)return {done:true,text:'complete reply'};
  return {done:false,generating:MODE!=='idle'};
 }
 return [];
}
runJob({id:'test',type:'chat',conversation_id:'c'}).then(result=>
 console.log(JSON.stringify({result,now,sends,polls}))).catch(e=>{console.error(e);process.exitCode=1;});
'''.replace("MODE", json.dumps(mode))
    result = subprocess.run([node, "-e", code + harness], text=True, capture_output=True, check=True, timeout=10)
    data = json.loads(result.stdout)
    assert data["sends"] == 1
    assert data["now"] <= 720000
    if mode == "slow":
        assert data["result"]["text"] == "complete reply"
        assert data["now"] == 240000
    else:
        assert "error" in data["result"]
        assert data["now"] == (720000 if mode == "stuck" else 180000)
