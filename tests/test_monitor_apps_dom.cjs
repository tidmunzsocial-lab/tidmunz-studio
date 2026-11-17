"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const code = fs.readFileSync(path.join(__dirname, "../snapgen_modules/chrome_ext/monitor_apps.js"), "utf8");
const APPS = [
  ["Tidmunz Studio AI Operator", "app://plugins_6aebd38bc5588191808c3cbd710ded69"],
  ["Dino Bot Tunnel", "app://asdk_app_6afac8c38ba88191afe3e6f5a07f43eb"]
];
async function scenario(available) {
  const actions=[], chips=[], visible={width:20,height:10};
  let raw="", shown="", sent=0, deleted=0;
  const last={};
  const form={querySelectorAll:()=>[send]};
  const editor={
    get innerText() {return raw;},
    getBoundingClientRect:()=>visible,
    querySelectorAll: selector=>selector==="[app-mention-path]"
      ? chips.map(path=>({getAttribute:name=>name==="app-mention-path"?path:null})):[],
    querySelector: selector=>selector==="p:last-child"?last:null,
    closest: selector=>selector==="form"?form:null,
    focus:()=>actions.push("focus")
  };
  const rows=APPS.map(([name,uri],index)=>({
    get innerText(){return shown && available.includes(index) &&
      (shown==="@tidmunz"&&index===0 || shown.trim()==="@dino"&&index===1)
      ?name+"\n"+name:"";},
    getBoundingClientRect(){return this.innerText?visible:{width:0,height:0};},
    click(){chips.push(uri);raw=raw.replace(/@tidmunz|@dino/g,"")+name+" ";
      shown="";actions.push("chip"+index);}
  }));
  const send={
    disabled:false,
    getBoundingClientRect:()=>visible,
    getAttribute:name=>name==="aria-label"?"ส่ง":name==="data-testid"?"send-button":null,
    click:()=>{sent++;actions.push("send");}
  };
  const document={
    querySelectorAll:selector=>selector==='form [contenteditable="true"]'
      ?[editor]:selector==="button"?[...rows,send]:[],
    createRange:()=>({selectNodeContents:()=>{},collapse:()=>{}}),
    execCommand:(cmd,_ui,text)=>{
      if(cmd==="insertText"){raw+=text;shown=text.trim();actions.push("insert:"+text);return true;}
      if(cmd==="delete"){raw="";chips.length=0;deleted++;return true;}
      return false;
    }
  };
  const sandbox={self:{},document,
    location:{hostname:"chatgpt.com",pathname:"/"},
    window:{getSelection:()=>({removeAllRanges:()=>{},addRange:()=>{}})},
    setTimeout:(fn)=>{Promise.resolve().then(fn);return 1;},Promise};
  vm.createContext(sandbox);
  vm.runInContext(code,sandbox);
  const result=await sandbox.self.tmMonitorComposeWithApps({prompt:"[Tidmunz Studio | TMB-123]",
    marker:"TMB-123"});
  return {result,chips,actions,sent,deleted,raw};
}
(async()=>{
  const ok=await scenario([0,1]);
  assert.equal(ok.result.appMentionsVerified,true);
  assert.equal(ok.result.attempted,true);
  assert.deepEqual(ok.chips,APPS.map(row=>row[1]));
  assert.equal(ok.sent,1);
  assert.ok(ok.actions.includes("insert:@tidmunz"));
  assert.ok(ok.actions.includes("insert: @dino"));
  // No app -> no false textual @bot substitution and no message is sent.
  const missingFirst=await scenario([1]);
  assert.equal(missingFirst.result.attempted,false);
  assert.match(missingFirst.result.error,/Tidmunz Studio AI Operator/);
  assert.equal(missingFirst.sent,0);
  assert.equal(missingFirst.deleted,1);
  const missingSecond=await scenario([0]);
  assert.equal(missingSecond.result.attempted,false);
  assert.match(missingSecond.result.error,/Dino Bot Tunnel/);
  assert.equal(missingSecond.sent,0);
  assert.equal(missingSecond.deleted,1);
  console.log("PASS real @tidmunz/@dino chip paths; missing app fails closed and clears own draft");
})().catch(error=>{console.error(error);process.exitCode=1;});