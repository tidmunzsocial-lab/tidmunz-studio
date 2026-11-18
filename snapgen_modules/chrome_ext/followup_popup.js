"use strict";
const $=id=>document.getElementById(id);
const fmtDate=t=>t?new Date(t).toLocaleString("th-TH",{hour:"2-digit",minute:"2-digit",day:"2-digit",month:"short"}):"—";
function notice(s,bad=false){
 const el=$("notice");el.className=bad?"error":"good";el.textContent=s||"";
}
async function rpc(type,extra={}){
 return chrome.runtime.sendMessage(Object.assign({type:"tm_followup_"+type},extra));
}
async function refresh(){
 try{
  const r=await rpc("status");
  if(!r||!r.ok)throw Error(r&&r.error||"ไม่ตอบ");
  const c=r.config||{},s=r.project||{};
  $("host").textContent=s.host||"—";
  $("images").textContent=Number.isInteger(s.images)?s.images+"/"+s.total:"—";
  $("clips").textContent=Number.isInteger(s.clips)?s.clips+"/"+s.total:"—";
  $("bar").style.width=Number.isInteger(s.clips)?((s.clips/s.total)*100).toFixed(1)+"%":"0%";
  $("stage").textContent=(s.busy===true?"กำลังทำ":s.busy===false?"พักอยู่":"ไม่ทราบ");
  $("follow").textContent=c.phase==="uncertain"?(c.enabled?"กำลังตรวจข้อความเดิม":"หยุดตรวจข้อความ"):c.phase==="complete"?"เสร็จ":
     c.enabled?"เปิดใช้งาน":"ยังไม่เปิด";
  $("next").textContent=c.enabled?fmtDate(c.retryAt||c.nextAt):"—";
  $("start").disabled=!!c.enabled || c.phase==="sending" || c.phase==="uncertain";
  $("stop").disabled=!c.enabled;
  $("now").disabled=!c.enabled || !["idle","uncertain"].includes(c.phase);
  $("verify").disabled=!!c.enabled || c.phase!=="uncertain";
  if(!$("chatUrl").value&&c.url)$("chatUrl").value=c.url;
  if(c.lastError)notice(c.lastError,true);
  else if(s.error)notice("อ่านสถานะโปรเจกต์ไม่ได้: "+s.error,true);
  else notice(c.enabled?"ระบบกำหนดรอบอัตโนมัติแล้ว":"ระบุลิงก์แชทก่อนเปิดติดตาม");
 }catch(e){notice("ไม่สามารถอ่านสถานะ: "+String(e.message||e),true);}
}
async function tabs(){
 const all=await chrome.tabs.query({url:"https://chatgpt.com/*"});
 const select=$("openTabs");
 for(const t of all){
  if(!/\/c\/[0-9a-f-]{20,}/i.test(t.url||""))continue;
  const op=document.createElement("option");op.value=t.url;
  op.textContent=(t.title||"ChatGPT")+" — "+(t.url||"").slice(-27);
  select.appendChild(op);
 }
}
async function action(type,extra={}){
 try{
  const r=await rpc(type,extra);
  if(!r||!r.ok)throw Error(r&&r.error||"ไม่สำเร็จ");
  notice(type==="start"?"เปิดรอบติดตามแล้ว":type==="stop"?"หยุดติดตามแล้ว":"เริ่มตรวจรอบนี้แล้ว");
  await refresh();
 }catch(e){notice(String(e.message||e),true);}
}
$("openTabs").addEventListener("change",e=>{if(e.target.value)$("chatUrl").value=e.target.value;});
$("start").addEventListener("click",()=>action("start",{url:$("chatUrl").value}));
$("stop").addEventListener("click",()=>action("stop"));
$("now").addEventListener("click",()=>action("now"));
$("refresh").addEventListener("click",refresh);
$("verify").addEventListener("click",()=>action("reconcile"));
$("diag").addEventListener("click",async()=>{
 try{
  const r=await rpc("diagnose");
  if(!r || !r.ok)throw Error(r && r.error || "diagnostic failed");
  const d=r.diag||{};
  const bs=(d.buttons||[]).map(x=>(x.testid||x.type||"?")+":"+(x.disabled?"off":"on")+":"+(x.aria||x.title||x.text)).join(" | ");
  notice("ช่องส่ง: "+d.route+" match="+d.match+", editor="+Boolean(d.editor)+", draft="+(d.editor&&d.editor.draftLength||0)+", submit="+d.submitCount+"; buttons="+bs);
 }catch(e){notice("ตรวจช่องส่งไม่ได้: "+String(e.message||e),true);}
});
tabs().then(refresh).catch(refresh);
