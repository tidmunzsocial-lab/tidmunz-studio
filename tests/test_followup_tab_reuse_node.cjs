"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const code=fs.readFileSync(path.join(__dirname,"../snapgen_modules/chrome_ext/followup.js"),"utf8");
const store={};
const tabs=new Map();
let nextId=101, created=0, switches=0;
let currentStory="Film A", nextCid=1, mockDraft=false;
const chrome={
  storage:{local:{
    get:async keys=>{
      const output={};for(const key of (Array.isArray(keys)?keys:[keys]))output[key]=store[key];
      return output;
    },
    set:async data=>Object.assign(store,data),
    remove:async keys=>{for(const key of (Array.isArray(keys)?keys:[keys]))delete store[key];}
  }},
  alarms:{create:async()=>{},clear:async()=>true,get:async()=>null,
    onAlarm:{addListener:()=>{}}},
  tabs:{
    query:async({windowId})=>[...tabs.values()].filter(tab=>tab.windowId===windowId),
    get:async id=>{if(!tabs.has(id))throw Error("No tab");return {...tabs.get(id)};},
    create:async option=>{const tab={id:nextId++,windowId:1,active:option.active,url:option.url};
      tabs.set(tab.id,tab);created++;return {...tab};},
    update:async(id,params)=>{const tab=tabs.get(id);
      if(!tab)throw Error("No tab");if(params.url){tab.url=params.url;switches++;}
      Object.assign(tab,params);return {...tab};}
  },
  windows:{getAll:async()=>[{id:1}],update:async()=>{}},
  runtime:{onMessage:{addListener:()=>{}}},
  scripting:{executeScript:async({target,func,args})=>[{result:mockPage(target.tabId,func,args)}]}
};
const self={tmMonitorComposeWithApps:function tmMonitorComposeWithApps(){}};
function mockPage(tabId,fn,args) {
  if(fn===self.tmMonitorComposeWithApps){
    tabs.get(tabId).url="https://chatgpt.com/c/"+String(nextCid++).padStart(8,"0")+"-1111-1111-1111-111111111111";
    return {attempted:true,appMentionsVerified:true};
  }
  if(fn.name==="findMarker")return {found:true};
  if(String(fn).includes("hasDraft"))
    return {ready:true,hasDraft:mockDraft,hasChips:false,responding:false};
  return true;
}
const fetch=async(url,options)=>{
  if(String(url).includes("/monitor/status"))return {ok:true,json:async()=>({
    ready:true,story:currentStory,host:"DESKTOP-TESTHOST",
    busy:false,effect_review_pending:false,complete:false
  })};
  if(String(url).includes("/followup/status"))return {ok:true};
  if(String(url).includes("/status?"))return {ok:true,json:async()=>({
    connected:true,busy:0,queue:0
  })};
  throw Error("unexpected URL "+url);
};
const context={chrome,self,fetch,console,Date,Promise,URL,
  setTimeout:(fn)=>{Promise.resolve().then(fn);return 1;}};
vm.runInNewContext(code,context,{filename:"followup.js"});
self.tmFollowupInit({
  programWindowId:async()=>1,
  getLink:async()=>({port:8766,token:"unit-test"}),
  pageSend:()=>{throw Error("Unexpected send in tab reuse test");},
  inPage:async()=>{throw Error("scripting.executeScript must be used");}
});
const job=(story,char)=>({
  type:"monitor_bootstrap",project_key:char.repeat(64),
  story,host:"DESKTOP-TESTHOST",existing_url:""
});
(async()=>{
  const first=await self.tmFollowupBootstrap(job("Film A","a"));
  assert.equal(first.ok,true,JSON.stringify(first));
  assert.equal(created,1);
  const id=store.tmMonitorOwnedTabId;
  assert.equal(typeof id,"number");
  assert.equal(store.tmMonitorBootstrapPending,undefined);
  currentStory="Film B";
  const second=await self.tmFollowupBootstrap(job("Film B","b"));
  assert.equal(second.ok,true,JSON.stringify(second));
  assert.equal(created,1,"a new story must reuse the monitor tab, not open a second");
  assert.equal(store.tmMonitorOwnedTabId,id);
  assert.ok(switches>=1,"the owned tab navigated to the new story chat");
  assert.equal(tabs.size,1,"exactly one monitor tab for multiple projects");
  // A project chat manually opened by the user is not an owned monitor tab:
  // starting another project may not navigate it away.
  tabs.set(999,{id:999,url:"https://chatgpt.com/c/user-owned-chat",active:true,windowId:1});
  store.tmProjectFollowup.tabId=999;
  currentStory="Film C";
  const third=await self.tmFollowupBootstrap(job("Film C","c"));
  assert.equal(third.ok,true,JSON.stringify(third));
  assert.equal(created,1);
  assert.equal(tabs.get(999).url,"https://chatgpt.com/c/user-owned-chat");

  // A real draft in the ONE owned tab must block navigation without making
  // a new tab (or silently deleting what the user typed).
  const currentUrl=tabs.get(id).url;
  currentStory="Film D";mockDraft=true;
  const blocked=await self.tmFollowupBootstrap(job("Film D","d"));
  assert.match(blocked.error||"",/ข้อความร่าง/);
  assert.equal(created,1);
  assert.equal(tabs.get(id).url,currentUrl);
  // An OLD follow-up marked uncertain is not evidence the NEW reserved
  // project chat sent. Recover that pending blank tab WITHOUT replaying the
  // earlier marker and WITHOUT creating a second Chrome tab.
  mockDraft=false;
  // Simulate the exactly reserved UNSENT tab left by the old extension.
  // Unlike the draft-block scenario, this is a safe retry of the SAME
  // pending project and not a request to open an extra chat.
  tabs.get(id).url="https://chatgpt.com/";
  store.tmMonitorBootstrapPending={
    projectKey:"d".repeat(64),story:"Film D",host:"DESKTOP-TESTHOST",
    tabId:id,marker:"TMB-1700000000001",attempted:false,
    createdAt:Date.now()
  };
  store.tmProjectFollowup.phase="uncertain";
  store.tmProjectFollowup.marker="TMF-1700000000000-1";
  store.tmProjectFollowup.lastResult="sent";
  store.tmProjectFollowup.lastError="Previous send unconfirmed";
  const fourth=await self.tmFollowupBootstrap(job("Film D","d"));
  assert.equal(fourth.ok,true,JSON.stringify(fourth));
  assert.equal(created,1,"uncertain follow-up does not duplicate bootstrap tab");
  assert.equal(store.tmMonitorPreviousUncertain.marker,"TMF-1700000000000-1");
  assert.equal(store.tmProjectFollowup.phase,"idle");
  assert.equal(store.tmProjectFollowup.marker,"");
  console.log("PASS one monitor tab reused; user chat preserved; draft blocks navigation; uncertain old follow-up safely archived");
})().catch(e=>{console.error(e);process.exitCode=1;});