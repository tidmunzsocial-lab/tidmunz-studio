"use strict";
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const src = fs.readFileSync(path.join(__dirname, "..", "snapgen_modules", "chrome_ext", "followup.js"), "utf8");
const CHAT = "11111111-1111-1111-1111-111111111111";
const calls = { messages: [], urls: [], alarms: [], cleared: [] };
let statusTerminal = false;
let conf = { enabled:true, cid:CHAT, url:"https://chatgpt.com/c/"+CHAT,
  host:"TEST-WORKSTATION", story:"Project One", phase:"idle",
  nextAt:0, stopRequested:false, sentCount:0, dailyCount:0 };
const alarmListeners = [];
const tab = { id: 1, url:"https://chatgpt.com/c/"+CHAT, windowId:1 };
global.self = global;
global.self.tmMonitorComposeWithApps=function tmMonitorComposeWithApps(){};
const localStore={tmProjectFollowup:conf};
global.chrome = {
  storage:{ local:{
    get: async key => Object.fromEntries((Array.isArray(key)?key:[key]).map(k=>[k,localStore[k]])),
    set: async item => {Object.assign(localStore,item);if(item.tmProjectFollowup)conf={...item.tmProjectFollowup};},
  }},
  alarms:{
    create: name => calls.alarms.push(name),
    clear: async name => {calls.cleared.push(name); return true;},
    onAlarm:{addListener:fn=>alarmListeners.push(fn)}
  },
  runtime:{onMessage:{addListener:()=>{}}},
  tabs:{
    get:async()=>tab, update:async()=>tab, query:async()=>[],
    create:async()=>tab
  },
  windows:{update:async()=>{}, getAll:async()=>[{id:1}]},
  scripting:{ executeScript:async({func,args})=>{
    if(func===global.self.tmMonitorComposeWithApps){
      calls.messages.push(args[0].prompt);
      return [{result:{attempted:true,appMentionsVerified:true}}];
    }
    if(func.name==="findMarker")return [{result:{found:true}}];
    if(func.name==="composer")return [{result:{ok:true}}];
    return [{result:{ok:true}}];
  } }
};
global.fetch = async url => {
  calls.urls.push(String(url));
  if (String(url).includes("/monitor/status?token=")) {
    return {ok:true,json:async()=>({
      ready:true, story:"Project One", host:"TEST-WORKSTATION",
      checked_at:"test time", busy:true, stage:"สร้างคลิป", detail:"กำลังทำ",
      images:1, clips:0, total:2, effect_review_pending:statusTerminal,
      monitor_bot:"dino-bot-tunnel",tailscale_url:"https://testhost.example/",
      complete:false
    })};
  }
  if (String(url).includes("/status?token=")) {
    return {ok:true,json:async()=>({connected:true, busy:0, queue:0})};
  }
  throw Error("Unexpected or unauthenticated URL: " + url);
};
vm.runInThisContext(src, {filename:"followup.js"});
assert.equal(typeof self.tmFollowupInit, "function");
self.tmFollowupInit({
  getLink:async()=>({port:8766,token:"test-only"}),
  inPage:async(tabId, func, args)=>{
    assert.equal(tabId,1);
    if(func.name==="composer")return {ok:true};
    if(func.name==="findMarker")return {found:true};
    if(func.name==="inspectComposer")return {editor:null};
    if(func.name==="pageSend"){
      calls.messages.push(args[0].prompt);
      return {ok:true,user_message_id:"user-message-ok"};
    }
    throw Error("unexpected inPage fn: "+func.name);
  },
  pageSend:function pageSend(){}
});
async function waitUntil(predicate, ms=3500) {
  const until=Date.now()+ms;
  while(!predicate() && Date.now()<until)await new Promise(res=>setTimeout(res,30));
  assert.ok(predicate(), "timeout waiting for followup state");
}
(async()=>{
  await waitUntil(()=>conf.sentCount===1);
  assert.equal(calls.messages.length,1, "one verified message only");
  assert.ok(calls.messages[0].includes("Project One"));
  assert.ok(calls.urls.some(url=>url.includes("/status?token=test-only")),
    "the extension queue check must authenticate to the local relay");
  assert.ok(conf.enabled, "follow-up remains running before human-review stage");
  statusTerminal=true;
  for(const alarm of alarmListeners)alarm({name:"tm-project-followup"});
  await waitUntil(()=>conf.phase==="awaiting_effect_selection");
  assert.equal(conf.enabled,false);
  assert.equal(conf.stopRequested,true);
  assert.equal(conf.nextAt,0);
  assert.ok(calls.cleared.includes("tm-project-followup"));
  assert.equal(calls.messages.length,1, "must never send after human selector");
  assert.ok(!src.includes("text.includes(\"บท - ศึกอสูระกับเทวดา\")"),
    "no single story may be hardcoded into followup");
  console.log("PASS: authenticated relay status -> one same-chat follow-up -> final Chrome alarm cleared");
})().catch(err=>{console.error(err);process.exitCode=1;});
