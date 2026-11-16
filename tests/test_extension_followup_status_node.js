/* Fake Chrome MV3 APIs: verifies the EXISTING followup.js status channel only. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

async function run() {
  const root = path.resolve(__dirname, "..", "snapgen_modules", "chrome_ext");
  const source = fs.readFileSync(path.join(root, "followup.js"), "utf8");
  const storage = {};
  const reported = [];
  let alarm = null;
  let onMessage;
  const chrome = {
    storage: {local: {
      get: async key => ({[key]: storage[key]}),
      set: async value => Object.assign(storage, value)
    }},
    alarms: {
      create: async (name, options) => {assert.equal(name, "tm-project-followup"); alarm={name,...options};},
      clear: async name => {if(alarm?.name===name){alarm=null;return true;}return false;},
      get: async name => alarm?.name===name?alarm:undefined,
      onAlarm: {addListener: () => {}}
    },
    runtime: {onMessage:{addListener: fn=>{onMessage=fn;}}},
  };
  const fetch = async(url, options) => {
    if(url.includes("/monitor/status")) return {ok:true,json:async()=>({
      ready:true,host:"DESKTOP-F1PJT4S",story:"บท - มฆมานพ",busy:true,
      effect_review_pending:false
    })};
    if(url.includes("/followup/status")) {
      reported.push(JSON.parse(options.body));
      return {ok:true};
    }
    throw Error("unexpected URL");
  };
  const self = {};
  vm.runInNewContext(source, {chrome, fetch, self, URL, Date, Promise,
    setTimeout, clearTimeout, console}, {filename:"followup.js"});
  self.tmFollowupInit({inPage:async()=>{},pageSend:async()=>{},
    getLink:async()=>({port:8766,token:"only-test-token"})});
  const poll = async()=>{await self.tmFollowupReport();await new Promise(r=>setTimeout(r,0));};
  const rpc = msg=>new Promise(resolve=>{onMessage(msg,{},resolve);});

  await poll();
  assert.equal(reported.at(-1).enabled,false);
  const start=await rpc({type:"tm_followup_start",
    url:"https://chatgpt.com/c/01234567-89ab-cdef-0123-456789abcdef"});
  assert.equal(start.ok,true,JSON.stringify(start));
  await poll();
  assert.equal(reported.at(-1).enabled,true);
  assert.equal(reported.at(-1).alarm_active,true);
  assert.equal(reported.at(-1).story,"บท - มฆมานพ");
  assert.equal(reported.at(-1).interval_minutes,1);
  assert.ok(reported.at(-1).next_at>Date.now());

  const stop=await rpc({type:"tm_followup_stop"});
  assert.equal(stop.ok,true,JSON.stringify(stop));
  await poll();
  assert.equal(reported.at(-1).enabled,false);
  assert.equal(reported.at(-1).alarm_active,false);
  assert.equal(reported.at(-1).stop_requested,true);
  console.log("PASS native extension status: idle -> schedule 1m -> stop/clear alarm; no watchers");
}
run().catch(e=>{console.error(e);process.exitCode=1;});
