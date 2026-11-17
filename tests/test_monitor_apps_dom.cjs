// Run: node tests/test_monitor_apps_dom.cjs
// No browser/network/files changed. Real app chips must be created by UI click.
const assert=require("assert");
const fs=require("fs");
const vm=require("vm");
const path=require("path");
const code=fs.readFileSync(path.join(__dirname,"../snapgen_modules/chrome_ext/monitor_apps.js"),"utf8");
const APPS=[
 ["Tidmunz Studio AI Operator","app://plugins_6aebd38bc5588191808c3cbd710ded69"],
 ["Dino Bot Tunnel","app://asdk_app_6afac8c38ba88191afe3e6f5a07f43eb"],
];
async function scenario(available,atMention=false){
  let menu=false, mentionMenu=false, sent=0;
  const chipPaths=[], actions=[];
  const visible={width:20,height:10};
  const form={querySelectorAll:()=>[send]};
  const last={};
  const input={
    innerText:"",
    closest:x=>x==="form"?form:null,
    getBoundingClientRect:()=>visible,
    querySelectorAll:q=>q==="[app-mention-path]"?chipPaths.map(p=>({getAttribute:n=>n==="app-mention-path"?p:null})):[],
    querySelector:q=>q==="p:last-child"?last:null,
    focus:()=>actions.push("focus"),
  };
  const plus={
    getBoundingClientRect:()=>visible,
    getAttribute:n=>n==="aria-label"?"เพิ่มไฟล์และอื่นๆ":null,
    innerText:"",
    click:()=>{menu=true;actions.push("plus");}
  };
  const rows=APPS.map(([name,id],i)=>({
    innerText:name+"\n"+name,
    getBoundingClientRect:()=>((menu&&available.includes(i))||(mentionMenu&&atMention&&i===1))
      ?visible:{width:0,height:0},
    click:()=>{chipPaths.push(id);input.innerText+=" "+name;menu=false;mentionMenu=false;actions.push("app"+i)}
  }));
  const send={
    disabled:false,
    getBoundingClientRect:()=>visible,
    getAttribute:n=>n==="aria-label"?"ส่ง":n==="data-testid"?"send-button":null,
    click:()=>{sent++;actions.push("send")}
  };
  const document={
    querySelectorAll:q=>q==="form [contenteditable=\"true\"]"?[input]:q==="button"?[plus,...rows]:[],
    createRange:()=>({selectNodeContents:()=>{},collapse:()=>{}}),
    dispatchEvent:()=>{menu=false;return true},
    execCommand:(_command,_show,text)=>{input.innerText+=text;
      if(text.includes("@dino"))mentionMenu=true;return true}
  };
  const sandbox={
    self:{},location:{hostname:"chatgpt.com",pathname:"/"},
    document,KeyboardEvent:class {constructor(type,props){this.type=type;this.props=props;}},
    window:{getSelection:()=>({removeAllRanges:()=>{},addRange:()=>{}})},
    setTimeout,Promise
  };
  vm.createContext(sandbox);
  vm.runInContext(code,sandbox);
  const result=await sandbox.self.tmMonitorComposeWithApps({
    prompt:"[Tidmunz monitor TMB-123] ตรวจเครื่องและโปรเจกต์",
    marker:"TMB-123"
  });
  return {result,chipPaths,actions,sent};
}
(async()=>{
  const ok=await scenario([0,1]);
  assert.equal(ok.result.attempted,true);
  assert.equal(ok.result.appMentionsVerified,true);
  assert.deepStrictEqual(ok.chipPaths,APPS.map(x=>x[1]));
  assert.equal(ok.sent,1);
  const fallback=await scenario([0],true);
  assert.equal(fallback.result.attempted,true);
  assert.equal(fallback.result.appMentionsVerified,true);
  assert(fallback.actions.includes("app1"));
  const fail=await scenario([0],false);
  assert.equal(fail.result.attempted,false);
  assert.match(fail.result.error,/App not selectable/);
  assert.equal(fail.sent,0);
  console.log("PASS native Plus/at-mention two-app composer + fail-closed missing app");
})().catch(e=>{console.error(e);process.exit(1)});
