// Tidmunz ChatGPT: scheduled project follow-up in the SAME program Chrome extension.
// Read-only local status; no paid API calls or duplicate message resends.
(() => {
  const STORE="tmProjectFollowup", ALARM="tm-project-followup", MIN=60000;
  let running=false, injected=null;
  const delay=ms=>new Promise(done=>setTimeout(done,ms));
  const defaults=()=>({enabled:false,url:"",cid:"",phase:"idle",nextAt:0,lastAt:0,
    confirmedAt:0,lastError:"",lastResult:"",lastProgress:null,tabId:0,
    marker:"",sentCount:0,day:"",dailyCount:0,story:"",host:"",errors:0,stopRequested:false,intervalMinutes:0});
  async function load(){const x=(await chrome.storage.local.get(STORE))[STORE];return Object.assign(defaults(),x||{});}
  async function save(x){
    const previous=(await chrome.storage.local.get(STORE))[STORE]||{};
    if(previous.stopRequested===true && x.stopRequested!==false){
      x.enabled=false;x.stopRequested=true;x.nextAt=0;
    }
    // Persist the actual schedule, not the status of a GPT image/video job.
    if(!x.nextAt)x.intervalMinutes=0;
    else if(Number(x.nextAt)!==Number(previous.nextAt))
      x.intervalMinutes=Math.max(1,Math.ceil((Number(x.nextAt)-Date.now())/MIN));
    await chrome.storage.local.set({[STORE]:x});
    reportState().catch(()=>{});
  }
  async function reportState(){
    if(!injected||!injected.getLink)return;
    const link=await injected.getLink();
    const port=Number(link&&link.port), token=String(link&&link.token||"");
    if(!Number.isInteger(port)||port<1000||port>65535||!token)return;
    const c=await load(),alarm=await chrome.alarms.get(ALARM);
    await fetch("http://127.0.0.1:"+port+"/followup/status?token="+encodeURIComponent(token),{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        enabled:!!c.enabled,alarm_active:!!alarm,stop_requested:!!c.stopRequested,
        checking:running,phase:c.phase,next_at:c.nextAt||0,
        interval_minutes:c.intervalMinutes||0,story:c.story||"",host:c.host||""
      })
    });
  }
  async function finishFollowup(c,phase,reason){
    c.enabled=false;c.stopRequested=true;c.phase=phase;c.nextAt=0;
    c.lastError=reason||"";
    await save(c);await chrome.alarms.clear(ALARM);
    reportState().catch(()=>{});
  }
  function parse(raw){
    try{const u=new URL(String(raw||"").trim());
      const m=u.pathname.match(/(?:^|\/)c\/([0-9a-f-]{20,})(?:\/|$)/i);
      return u.protocol==="https:"&&u.hostname==="chatgpt.com"&&m?
        {cid:m[1].toLowerCase(),url:u.href}:null;
    }catch(_){return null;}
  }
  async function status(){
    if(!injected||!injected.getLink)throw Error("Chrome bridge is not initialized");
    const link=await injected.getLink();
    const port=Number(link&&link.port), token=String(link&&link.token||"");
    if(!Number.isInteger(port)||port<1000||port>65535||!token)
      throw Error("Tidmunz Chrome relay is not connected");
    const url="http://127.0.0.1:"+port+"/monitor/status?token="+encodeURIComponent(token);
    const response=await fetch(url,{cache:"no-store"});
    if(!response.ok)throw Error("Tidmunz project status unavailable (HTTP "+response.status+")");
    const s=await response.json();
    if(!s.ready||!s.story||!s.host)throw Error("Tidmunz Auto is not ready");
    return s;
  }
  async function otherExtensionJobBusy(){
    // The same extension also performs ChatGPT image/text jobs.
    // Never steal its worker tab's foreground focus during those jobs.
    const active=await injected.getLink();
    const port=Number(active&&active.port);
    if(!Number.isInteger(port) || port<1000 || port>65535)return true;
    try{
      const token=String(active&&active.token||"");
      if(!token)return true;
      const res=await fetch("http://127.0.0.1:"+port+"/status?token="+encodeURIComponent(token),{cache:"no-store"});
      if(!res.ok)return true;
      const j=await res.json();
      return !j.connected || Number(j.busy||0)>0 || Number(j.queue||0)>0;
    }catch(_){return true;}
  }
  function minutes(s,previous){
    const text=(s.stage||"")+" "+(s.detail||"");
    if(/429|quota|โควตา|ลิมิต|reset/i.test(text))return 30;
    if(s.busy===false)return 5;
    if(s.clips>=100)return 8;
    if(previous && s.clips<=previous.clips)return 10;
    return 15;
  }
  function message(s,marker,m){
    const pending=Array.isArray(s.pending)?(s.pending.slice(0,18).join(", ")||"ไม่มี"):"ต้องตรวจ UUID จากโปรเจกต์";
    const holds=Array.isArray(s.holds)?(s.holds.slice(0,18).map(x=>String(x.shot)+":"+String(x.reason)).join(", ")||"ไม่มี"):"ต้องตรวจสถานะช็อตจากโปรเจกต์";
    return "[Tidmunz Studio | สคริปต์ติดตามงานอัตโนมัติ | "+marker+"]\n"+
      "นี่คือข้อความติดตามอัตโนมัติจากส่วนขยาย Tidmunz ChatGPT ในแชทเดิม ไม่ใช่งานใหม่ของผู้ใช้ "+
      "ให้อ่านประวัติแชทนี้และตรวจสถานะจริงด้วยบอทของเครื่องเดิม ห้ามเดาหรือสลับเครื่อง.\n"+
      "เครื่อง: "+s.host+"; โปรเจกต์: "+s.story+"; ตรวจเมื่อ: "+s.checked_at+
      "; ภาพ "+s.images+"/"+s.total+"; คลิป "+s.clips+"/"+s.total+
      "; กำลังทำ="+s.busy+"; ขั้นตอน="+s.stage+"; รายละเอียด="+s.detail+
      "; UUID รอผล="+pending+"; ช็อตพัก="+holds+".\n"+
      "ตรวจความคืบหน้าจริงและแก้ปัญหาที่ปลอดภัยทันที จากนั้นทำงานเดิมต่อโดยไม่ส่งคำสั่งสร้างซ้ำ "+
      "ตรวจใบรับงานและเครดิตก่อนแก้หรือเจนใหม่ ห้ามสร้างระบบ watcher ซ้ำ. "+
      "เป้าหมายคือทำไปจนถึงหน้า 'เลือกเสียงประกอบก่อนรวมวิดีโอ' เท่านั้น: "+
      "เมื่อถึงหน้านั้นให้หยุดระบบติดตามและรอผู้ใช้เลือกเสียงเอง "+
      "ห้ามยืนยันหน้าเลือกเสียง ห้ามรวม/เรนเดอร์วิดีโอหลังจุดนั้นโดยอัตโนมัติ. "+
      "ระหว่างงานรอบนี้ถ้าต้องตรวจปัญหาให้ใช้เครื่องมือจริง รายงานสั้นๆ ว่าแก้อะไรแล้ว. "+
      "ส่วนขยายจะกำหนดรอบตรวจต่อโดยอาศัยสถานะ ไม่ใช่ GPT ที่ทำงานเบื้องหลังตลอดเวลา.";
  }
  async function inPage(tabId,fn,args=[]){
    const a=await chrome.scripting.executeScript({target:{tabId},world:"MAIN",func:fn,args});
    return a[0]&&a[0].result;
  }
  function composer(cid){
    if(location.hostname!=="chatgpt.com"||!location.pathname.endsWith("/c/"+cid))
      return {ok:false,why:"wrong_conversation"};
    const editor=document.querySelector('form div.ProseMirror[role="textbox"]')||
      document.querySelector('form #prompt-textarea[contenteditable="true"]')||
      document.querySelector('form [contenteditable="true"]');
    const form=editor&&editor.closest("form");
    if(!form)return {ok:false,why:"composer_unavailable"};
    const busy=[...form.querySelectorAll("button")].some(b=>b.dataset.testid==="stop-button"||
      /^(stop|หยุด|停止)/i.test(b.getAttribute("aria-label")||""));
    const draft=(editor.innerText||editor.textContent||"").trim();
    return {ok:!busy&&!draft,why:busy?"assistant_busy":draft?"draft_exists":""};
  }
  function inspectComposer(cid){
    if(location.hostname!=="chatgpt.com")return {error:"not_chatgpt"};
    const edit=document.querySelector('form div.ProseMirror[role="textbox"]')||
      document.querySelector('form #prompt-textarea[contenteditable="true"]')||
      document.querySelector('form [contenteditable="true"]');
    const form=edit && edit.closest("form");
    const buttons=form ? [...form.querySelectorAll("button")] : [];
    return {
      route:location.pathname, match:location.pathname.endsWith("/c/"+cid),
      formCount:document.querySelectorAll("form").length,
      editor:edit?{tag:edit.tagName,id:edit.id,role:edit.getAttribute("role"),
        editable:edit.getAttribute("contenteditable"),className:String(edit.className).slice(0,85),
        draftLength:String(edit.innerText||edit.textContent||"").trim().length,
        monitorMarker:(()=>{
          const draft=String(edit.innerText||edit.textContent||"").trim();
          const newer=draft.match(/^\[Tidmunz Studio \| สคริปต์ติดตามงานอัตโนมัติ \| (TMF-[0-9]{13}-[0-9]+)\]/);
          const legacy=draft.match(/^\[Tidmunz Auto Follow-up: (TMF-[0-9]{13}-[0-9]+)\]/);
          return (newer&&newer[1])||(legacy&&legacy[1])||null;
        })()}:null,
      buttons:buttons.map(b=>({type:b.type,testid:b.dataset.testid||"",
        aria:(b.getAttribute("aria-label")||"").slice(0,65),
        title:(b.getAttribute("title")||"").slice(0,65),
        text:(b.innerText||"").slice(0,30),disabled:b.disabled,
        html:b.outerHTML.slice(0,180)})).slice(-25),
      submitCount:form?form.querySelectorAll('button[type="submit"]').length:0
    };
  }
  function submitOwnedMonitorDraft(cid,marker){
    if(location.hostname!=="chatgpt.com" || !location.pathname.endsWith("/c/"+cid))
      return {attempted:false,reason:"wrong_conversation"};
    const edit=document.querySelector('form div.ProseMirror[role="textbox"]')||
      document.querySelector('form #prompt-textarea[contenteditable="true"]')||
      document.querySelector('form [contenteditable="true"]');
    const form=edit&&edit.closest("form");
    const text=String(edit&&(edit.innerText||edit.textContent)||"").trim();
    const isOwn=text.startsWith("[Tidmunz Studio | สคริปต์ติดตามงานอัตโนมัติ | "+marker+"]") ||
      text.startsWith("[Tidmunz Auto Follow-up: "+marker+"]");
    if(!form || !isOwn || !/เครื่อง:.*; โปรเจกต์:/.test(text))
      return {attempted:false,reason:"not_owned_monitor_draft"};
    if([...document.querySelectorAll('[data-message-author-role="user"]')]
        .some(x=>(x.innerText||x.textContent||"").includes(marker)))
      return {attempted:false,reason:"marker_already_visible"};
    const busy=[...form.querySelectorAll("button")].some(btn=>
      btn.dataset.testid==="stop-button" || /^(stop|หยุด|停止)/i.test(btn.getAttribute("aria-label")||""));
    const send=form.querySelector('button[type="submit"],button[data-testid="send-button"]');
    if(busy || !send || send.disabled)
      return {attempted:false,reason:"composer_not_ready"};
    send.click();
    return {attempted:true};
  }
  async function findMarker(marker,cid){
    if(!location.pathname.endsWith("/c/"+cid))return {found:false};
    if([...document.querySelectorAll('[data-message-author-role="user"]')]
        .some(x=>(x.innerText||x.textContent||"").includes(marker)))return {found:true};
    try{
      const session=await(await fetch("/api/auth/session",{cache:"no-store"})).json();
      if(!session.accessToken)return {found:false};
      const response=await fetch("/backend-api/conversation/"+cid,
        {cache:"no-store",headers:{Authorization:"Bearer "+session.accessToken}});
      if(!response.ok)return {found:false};
      const data=await response.json();
      return {found:Object.values(data.mapping||{}).some(node=>{
        const msg=node&&node.message;
        return msg&&msg.author&&msg.author.role==="user"&&
          ((msg.content&&msg.content.parts)||[]).some(x=>typeof x==="string"&&x.includes(marker));
      })};
    }catch(_){return {found:false};}
  }
  async function tab(conf){
    if(conf.tabId){
      try{
        const t=await chrome.tabs.get(conf.tabId);
        if(/^https:\/\/chatgpt\.com\//.test(t.url||t.pendingUrl||""))return t;
      }catch(_){}
    }
    const wins=await chrome.windows.getAll({windowTypes:["normal"]});
    if(!wins.length)throw Error("ต้องเปิด Chrome ของ Tidmunz Studio");
    const t=await chrome.tabs.create({windowId:wins[0].id,
      url:"https://chatgpt.com/c/"+conf.cid,active:false,pinned:false});
    await chrome.tabs.update(t.id,{autoDiscardable:false}).catch(()=>{});
    conf.tabId=t.id;await save(conf);
    return t;
  }
  async function ready(t,cid){
    const target="https://chatgpt.com/c/"+cid;
    const matches=(raw)=>{
      try{const u=new URL(raw);return u.hostname==="chatgpt.com"&&u.pathname.endsWith("/c/"+cid);}
      catch(_){return false;}
    };
    if(!matches(t.url||"")&&!matches(t.pendingUrl||""))
      await chrome.tabs.update(t.id,{url:target});
    for(let i=0;i<38;i++){
      await delay(900);
      try{
        const x=await inPage(t.id,composer,[cid]);
        if(x.ok||["draft_exists","assistant_busy"].includes(x.why))return x;
      }catch(_){}
    }
    throw Error("ChatGPT แชทเป้าหมายโหลดไม่สำเร็จ");
  }
  async function otherActiveDraft(cid,exclude){
    const tabs=await chrome.tabs.query({url:"https://chatgpt.com/*"});
    for(const t of tabs){
      if(!t.active||t.id===exclude||!(t.url||"").includes("/c/"+cid))continue;
      try{const c=await inPage(t.id,composer,[cid]);if(!c.ok)return true;}
      catch(_){return true;}
    }
    return false;
  }
  async function tick(force=false){
    if(running)return;
    running=true;
    let c=await load();
    reportState().catch(()=>{});
    try{
      if(!c.enabled||!c.cid||!injected)return;
      // Always check the terminal stage before any next message, even if nextAt is in the future.
      const live=await status();
      if(!c.story||!c.host||live.story!==c.story||live.host!==c.host){
        await finishFollowup(c,"wrong_project","The selected machine or story changed; follow-up stopped");
        return;
      }
      if(live.effect_review_pending||
         /เลือกเสียงประกอบก่อนรวมวิดีโอ|รอเลือกเสียงเอฟเฟกต์|รอเลือกเสียงประกอบ/i.test(String(live.stage||"")+" "+String(live.detail||""))){
        await finishFollowup(c,"awaiting_effect_selection","");
        return;
      }
      if(live.complete){
        await finishFollowup(c,"complete","");
        return;
      }
      if(c.phase==="uncertain")return;
      if(c.phase==="sending"&&c.marker){
        const t=await tab(c);
        await ready(t,c.cid);
        const check=await inPage(t.id,findMarker,[c.marker,c.cid]);
        if(!check.found){
          c.phase="uncertain";c.enabled=false;
          c.lastError="รอบก่อนอาจส่งสำเร็จแล้วแต่ตรวจไม่พบ: หยุดส่งซ้ำ";
        }else{
          c.phase="idle";c.marker="";c.confirmedAt=Date.now();
          c.nextAt=Date.now()+15*MIN;c.lastResult="recovered_confirmation";
        }
        await save(c);return;
      }
      if(!force&&Date.now()<(c.nextAt||0))return;
      const s=live,now=Date.now(),m=minutes(s,c.lastProgress);
      c.lastProgress={clips:s.clips,images:s.images,at:now};
      if(s.complete&&c.lastResult==="finished_sent"){
        c.enabled=false;c.phase="complete";c.nextAt=0;await save(c);return;
      }
      if(s.busy===null||s.busy===undefined){
        c.lastError="Auto API ไม่พร้อม";c.nextAt=now+5*MIN;await save(c);return;
      }
      const today=new Date().toISOString().slice(0,10);
      if(c.day!==today){c.day=today;c.dailyCount=0;}
      if(c.dailyCount>=64){c.nextAt=now+60*MIN;c.lastError="ครบเพดาน 64 ข้อความ/วัน";await save(c);return;}
      // The user explicitly wants monitoring while this conversation is open
      // on mobile/another tab. A dedicated monitor tab does not own the other
      // tab's draft. Defer only if THIS composer has a draft or is generating.
      if(await otherExtensionJobBusy()){c.nextAt=now+2*MIN;await save(c);return;}
      const t=await tab(c),check=await ready(t,c.cid);
      if(!check.ok && check.why==="draft_exists"){
        const diag=await inPage(t.id,inspectComposer,[c.cid]);
        const owned=diag&&diag.editor&&diag.editor.monitorMarker;
        const stamp=owned&&Number((owned.match(/^TMF-([0-9]{13})-/)||[])[1]);
        if(owned && stamp && Math.abs(now-stamp)<24*60*MIN){
          // A prior attempt safely stopped without clicking Send, leaving
          // our own identified draft in the dedicated monitor tab.
          // Resume it once; never touch a non-monitor user's draft.
          const prior=await inPage(t.id,findMarker,[owned,c.cid]);
          if(prior&&prior.found){
            c.lastError="";c.nextAt=now+m*MIN;c.lastResult="previously_sent";
            await save(c);return;
          }
          c.phase="sending";c.marker=owned;c.lastAt=now;c.lastError="";
          await save(c);
          const sent=await inPage(t.id,submitOwnedMonitorDraft,[c.cid,owned]);
          if(!sent || !sent.attempted){
            c.phase="idle";c.marker="";c.nextAt=Date.now()+2*MIN;
            c.lastError="ยังไม่ได้ส่งร่างของระบบ: "+String(sent&&sent.reason||"unknown");
            await save(c);return;
          }
          let observed=false;
          for(let attempts=0;attempts<16;attempts++){
            await delay(1000);
            try{
              const found=await inPage(t.id,findMarker,[owned,c.cid]);
              if(found&&found.found){observed=true;break;}
            }catch(_){}
          }
          if(!observed){
            c.phase="uncertain";c.enabled=false;
            c.lastError="กดส่งข้อความติดตามแล้วแต่ยังไม่ยืนยัน ต้องตรวจในแชทก่อนส่งรอบใหม่";
            await save(c);return;
          }
          c.phase=s.complete?"complete":"idle";c.enabled=!s.complete;
          c.marker="";c.sentCount++;c.dailyCount++;c.confirmedAt=Date.now();
          c.lastResult=s.complete?"finished_sent":"sent_from_saved_draft";
          c.nextAt=s.complete?0:Date.now()+m*MIN;c.lastError="";
          await save(c);return;
        }
      }
      if(!check.ok){
        c.nextAt=now+2*MIN;
        c.lastError=check.why||"แชทติดตามยังไม่พร้อมส่ง";
        await save(c);return;
      }
      const marker="TMF-"+String(now)+"-"+String((c.sentCount||0)+1);
      const prompt=message(s,marker,m);
      c.phase="sending";c.marker=marker;c.lastAt=now;c.lastError="";
      await save(c);
      const curr=await chrome.tabs.get(t.id);
      await chrome.windows.update(curr.windowId,{state:"normal",focused:true});
      await chrome.tabs.update(t.id,{active:true});
      const lastCheck=await status();
      if(lastCheck.effect_review_pending){
        await finishFollowup(c,"awaiting_effect_selection","");
        return;
      }
      const stillEnabled=await load();
      if(!stillEnabled.enabled||stillEnabled.stopRequested)return;
      const result=await injected.page(t.id,injected.send,[{
        type:"chat",conversation_id:c.cid,prompt,images:[],files:[]
      }]);
      let confirmed=!!(result&&result.ok&&result.user_message_id);
      if(!confirmed)confirmed=!!(await inPage(t.id,findMarker,[marker,c.cid])).found;
      if(!confirmed){
        if(result&&result.send_state==="not_sent"){
          c.phase="idle";c.marker="";c.nextAt=Date.now()+10*MIN;
          c.lastError=String(result.error||"ข้อความยังไม่ส่ง").slice(0,200);
        }else{
          c.phase="uncertain";c.enabled=false;
          c.lastError="ไม่สามารถยืนยันการส่ง หยุดเพื่อไม่ส่งข้อความซ้ำ";
        }
        await save(c);return;
      }
      c.phase=s.complete?"complete":"idle";c.enabled=!s.complete;
      c.marker="";c.sentCount++;c.dailyCount++;c.confirmedAt=Date.now();
      c.errors=0;c.lastResult=s.complete?"finished_sent":"sent";
      c.nextAt=s.complete?0:Date.now()+m*MIN;c.lastError="";await save(c);
    }catch(e){
      c=await load();
      if(c.phase==="sending"){
        c.phase="uncertain";c.enabled=false;
        c.lastError="เกิดข้อผิดพลาดหลังเริ่มส่ง ต้องตรวจแชทก่อน: "+String(e.message||e).slice(0,150);
      }else{
        c.errors=(c.errors||0)+1;
        c.lastError=String(e.message||e).slice(0,200);c.nextAt=Date.now()+10*MIN;
        if(c.errors>=5){
          await finishFollowup(c,"blocked",c.lastError);
          return;
        }
      }
      await save(c);
      if(!c.enabled)await chrome.alarms.clear(ALARM);
    }finally{
      running=false;
      reportState().catch(()=>{});
    }
  }
  self.tmFollowupReport=()=>reportState().catch(()=>{});
  self.tmFollowupInit=(callbacks)=>{
    if(injected)return;
    injected={page:callbacks.inPage,send:callbacks.pageSend,getLink:callbacks.getLink};
    load().then(async c=>{
      if(c.enabled)await chrome.alarms.create(ALARM,{periodInMinutes:1});
      await reportState();
    }).catch(()=>{});
    chrome.alarms.onAlarm.addListener(a=>{if(a.name===ALARM)tick().catch(()=>{});});
    chrome.runtime.onMessage.addListener((msg,sender,reply)=>{
      if(!msg||!String(msg.type||"").startsWith("tm_followup_"))return;
      (async()=>{
        if(msg.type==="tm_followup_status"){
          let project=null;try{project=await status();}catch(e){project={error:String(e.message||e)};}
          return {ok:true,config:await load(),project,bridgeReady:!!injected};
        }
        if(msg.type==="tm_followup_diagnose"){
          const c=await load();
          if(!c.cid)return {ok:false,error:"No chat bound"};
          const t=await tab(c);
          const diag=await inPage(t.id,inspectComposer,[c.cid]);
          return {ok:true,diag};
        }
        if(msg.type==="tm_followup_start"){
          const parsed=parse(msg.url);
          if(!parsed)return {ok:false,error:"วางลิงก์ ChatGPT ของแชทนี้ให้ถูกต้อง"};
          const s=await status();
          if(s.complete||s.effect_review_pending)
        return {ok:false,error:"โปรเจกต์ถึงจุดหยุดหรือเสร็จแล้ว ไม่เริ่มติดตาม"};
          const c=await load();
          if(c.phase==="sending"||c.phase==="uncertain")
            return {ok:false,error:"มีรอบส่งเดิมที่ยังยืนยันไม่ได้ ต้องตรวจแชทก่อน"};
          c.enabled=true;c.cid=parsed.cid;c.url=parsed.url;c.nextAt=Date.now()+MIN;
      c.host=s.host;c.story=s.story;c.stopRequested=false;c.errors=0;
          c.phase="idle";c.lastError="";await save(c);
      chrome.alarms.create(ALARM,{periodInMinutes:1});
      return {ok:true,nextAt:c.nextAt};
        }
        if(msg.type==="tm_followup_stop"){
          const c=await load();
      await finishFollowup(c,"stopped","");
      return {ok:true};
        }
        if(msg.type==="tm_followup_reconcile"){
          const c=await load();
          if(c.phase!=="uncertain"||!c.marker)return {ok:false,error:"ไม่มีข้อความค้างให้ตรวจ"};
          const t=await tab(c);
          await ready(t,c.cid);
          const check=await inPage(t.id,findMarker,[c.marker,c.cid]);
          if(!check.found)return {ok:false,error:"ยังไม่ยืนยันข้อความรอบก่อน ห้ามส่งซ้ำ"};
          c.phase="idle";c.enabled=true;c.marker="";c.lastError="";
          c.confirmedAt=Date.now();c.nextAt=Date.now()+5*MIN;
      await save(c);chrome.alarms.create(ALARM,{periodInMinutes:1});
      return {ok:true};
        }
        if(msg.type==="tm_followup_now"){
          const c=await load();
          if(!c.enabled||c.phase!=="idle")return {ok:false,error:"ยังไม่พร้อมส่ง"};
          c.nextAt=Date.now();await save(c);tick(true).catch(()=>{});
          return {ok:true};
        }
        return {ok:false,error:"unknown_action"};
      })().then(reply).catch(e=>reply({ok:false,error:String(e.message||e)}));
      return true;
    });
    tick().catch(()=>{});
  };
})();
