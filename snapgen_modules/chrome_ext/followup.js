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
  async function save(x,{allowRestart=false}={}){
    const previous=(await chrome.storage.local.get(STORE))[STORE]||{};
    if(previous.stopRequested===true && !allowRestart && !x.stopRequested)return;
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
        checking:running,phase:c.phase,next_at:c.retryAt||c.nextAt||0,
        interval_minutes:c.retryAt?Math.min(10,c.errors*2):c.intervalMinutes||0,story:c.story||"",host:c.host||"",
        tool_state:c.lastToolMarker?"awaiting_proof":
          c.lastResult==="dino_invoked_and_auto_advanced"?"verified_dino":
          c.lastResult==="dino_invoked_repair_unverified"?"repair_unverified":
          /^(no_tool_invocation|other_tool_called_dino_not_verified|tool_invocation_unverified)$/
            .test(c.lastResult||"")?"not_verified":"not_checked"
      })
    });
  }
  async function finishFollowup(c,phase,reason){
    c.enabled=false;c.stopRequested=true;c.phase=phase;c.nextAt=0;c.retryAt=0;
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
    const response=await fetch(url,{cache:"no-store",signal:globalThis.AbortSignal?.timeout(10000)});
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
      "นี่คือข้อความติดตามอัตโนมัติของ Tidmunz Studio ไม่ใช่งานใหม่ของผู้ใช้ "+
      "ไม่จำเป็นต้องอ่านแชทเดิม ให้ตรวจสถานะจริงจากเครื่องมือของเครื่องนี้.\n"+
      "บอทของเครื่องนี้: @"+s.monitor_bot+" เท่านั้น สำหรับเครื่อง "+s.host+
      " ห้ามเรียกบอทของเครื่องอื่นหรือเดาชื่อเครื่อง.\n"+
      "ลิงก์ Tailscale ของเครื่องนี้: "+s.tailscale_url+"\n"+
      "เว็บ Tailscale ใช้ดูสถานะประกอบการตรวจ ส่วนการแก้ไขต้องใช้ @"+
      s.monitor_bot+" ของเครื่อง "+s.host+" โดยตรงเท่านั้น.\n"+
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
  // Chrome can render two independent composers for the same ChatGPT chat.
  // Check ALL visible/connected forms: a Stop button in the second form means
  // GPT is replying even if the first blank composer looks idle.
  function composer(cid){
    if(location.hostname!=="chatgpt.com"||!location.pathname.endsWith("/c/"+cid))
      return {ok:false,why:"wrong_conversation"};
    const editors=[...document.querySelectorAll('form div.ProseMirror[role="textbox"],form #prompt-textarea[contenteditable="true"],form [contenteditable="true"]')]
      .filter(e=>e.isConnected&&e.closest("form"));
    if(!editors.length)return {ok:false,why:"composer_unavailable"};
    const busy=[...document.querySelectorAll("form button")].some(b=>
      b.dataset.testid==="stop-button" || /^(stop|หยุด|停止)/i.test(b.getAttribute("aria-label")||""));
    const draft=editors.some(e=>String(e.innerText||e.textContent||"").trim().length>0);
    return {ok:!busy&&!draft,why:busy?"assistant_busy":draft?"draft_exists":""};
  }
  function inspectComposer(cid){
    if(location.hostname!=="chatgpt.com")return {error:"not_chatgpt"};
    const editors=[...document.querySelectorAll('form div.ProseMirror[role="textbox"],form #prompt-textarea[contenteditable="true"],form [contenteditable="true"]')]
      .filter(e=>e.isConnected&&e.closest("form"));
    const edit=editors.find(e=>/\bTMF-[0-9]{13}-[0-9]+\b/.test(String(e.innerText||e.textContent||""))) ||
      editors.find(e=>String(e.innerText||e.textContent||"").trim()) || editors[0];
    const form=edit&&edit.closest("form");
    const buttons=form?[...form.querySelectorAll("button")]:[];
    const draft=String(edit&&(edit.innerText||edit.textContent)||"").trim();
    // Real ChatGPT app mentions precede the monitor marker in the composer.
    const newer=draft.match(/\[Tidmunz Studio \| สคริปต์ติดตามงานอัตโนมัติ \| (TMF-[0-9]{13}-[0-9]+)\]/);
    const legacy=draft.match(/\[Tidmunz Auto Follow-up: (TMF-[0-9]{13}-[0-9]+)\]/);
    return {
      route:location.pathname,match:location.pathname.endsWith("/c/"+cid),
      formCount:document.querySelectorAll("form").length,
      editor:edit?{tag:edit.tagName,id:edit.id,role:edit.getAttribute("role"),
        editable:edit.getAttribute("contenteditable"),className:String(edit.className).slice(0,85),
        draftLength:draft.length,monitorMarker:(newer&&newer[1])||(legacy&&legacy[1])||null}:null,
      buttons:buttons.map(b=>({type:b.type,testid:b.dataset.testid||"",
        aria:(b.getAttribute("aria-label")||"").slice(0,65),
        title:(b.getAttribute("title")||"").slice(0,65),
        text:(b.innerText||"").slice(0,30),disabled:b.disabled,
        html:b.outerHTML.slice(0,180)})).slice(-25),
      submitCount:form?form.querySelectorAll('button[type="submit"],button[data-testid="send-button"],button[aria-label="ส่งข้อความ"]').length:0
    };
  }
  function submitOwnedMonitorDraft(cid,marker,story,host){
    if(location.hostname!=="chatgpt.com" || !location.pathname.endsWith("/c/"+cid))
      return {attempted:false,reason:"wrong_conversation"};
    const editors=[...document.querySelectorAll('form div.ProseMirror[role="textbox"],form #prompt-textarea[contenteditable="true"],form [contenteditable="true"]')]
      .filter(e=>e.isConnected&&e.closest("form"));
    const edit=editors.find(e=>{
      const draft=String(e.innerText||e.textContent||"").trim();
      return draft.includes("[Tidmunz Studio | สคริปต์ติดตามงานอัตโนมัติ | "+marker+"]") ||
        draft.includes("[Tidmunz Auto Follow-up: "+marker+"]");
    });
    const form=edit&&edit.closest("form");
    const text=String(edit&&(edit.innerText||edit.textContent)||"").trim();
    if(!form || !story || !host || !text.includes("เครื่อง: "+host+"; โปรเจกต์: "+story+";"))
      return {attempted:false,reason:"not_owned_monitor_draft"};
    // Old plain-text monitor drafts must NOT be sent as a fake bot mention.
    const apps=[...edit.querySelectorAll("[app-mention-path]")].map(x=>x.getAttribute("app-mention-path"));
    if(!["app://plugins_6aebd38bc5588191808c3cbd710ded69",
          "app://asdk_app_6afac8c38ba88191afe3e6f5a07f43eb"].every(x=>apps.includes(x)))
      return {attempted:false,reason:"real_app_mentions_missing"};
    if([...document.querySelectorAll('[data-message-author-role="user"]')]
        .some(x=>(x.innerText||x.textContent||"").includes(marker)))
      return {attempted:false,reason:"marker_already_visible"};
    const busy=[...document.querySelectorAll("form button")].some(b=>
      b.dataset.testid==="stop-button" || /^(stop|หยุด|停止)/i.test(b.getAttribute("aria-label")||""));
    const send=[...form.querySelectorAll("button")].find(b=>
      !b.disabled && (b.type==="submit" || b.dataset.testid==="send-button" ||
        b.id==="composer-submit-button" ||
        /^(send|ส่ง)/i.test((b.getAttribute("aria-label")||"").trim())));
    if(busy || !send)
      return {attempted:false,reason:busy?"assistant_busy":"composer_not_ready"};
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
  async function inspectToolProof(marker,cid){
    // Read-only provider history. A sent user message is not proof of a tool
    // call, and a tool call is not proof that Tidmunz Auto was fixed.
    if(!location.pathname.endsWith("/c/"+cid))return {ok:false,error:"wrong_chat"};
    try{
      const session=await(await fetch("/api/auth/session",{cache:"no-store"})).json();
      if(!session.accessToken)return {ok:false,error:"logged_out"};
      const response=await fetch("/backend-api/conversation/"+cid,
        {cache:"no-store",headers:{Authorization:"Bearer "+session.accessToken}});
      if(!response.ok)return {ok:false,error:"history_http_"+response.status};
      const data=await response.json();
      const messages=Object.values(data.mapping||{})
        .map(node=>node&&node.message).filter(Boolean)
        .sort((a,b)=>(a.create_time||0)-(b.create_time||0));
      const index=messages.findLastIndex(msg=>msg.author&&msg.author.role==="user"&&
        ((msg.content&&msg.content.parts)||[]).some(x=>typeof x==="string"&&x.includes(marker)));
      if(index<0)return {ok:false,error:"monitor_marker_not_found"};
      const later=messages.slice(index+1);
      const toolMessages=later.filter(msg=>
        (msg.author&&msg.author.role==="tool") ||
        (msg.author&&msg.author.role==="assistant"&&
         msg.recipient&&msg.recipient!=="all"&&msg.recipient!==""));
      const dinoConfirmed=toolMessages.some(msg=>{
        const evidence=JSON.stringify({
          recipient:msg.recipient,
          author:msg.author,
          metadata:msg.metadata,
          content:msg.author&&msg.author.role==="assistant"?msg.content:null,
        });
        return /Dino[_ -]?Bot[_ -]?Tunnel|dino-bot-tunnel|asdk_app_6afac8c38ba88191afe3e6f5a07f43eb/i.test(evidence);
      });
      const finished=later.some(msg=>msg.author&&msg.author.role==="assistant"&&
        msg.end_turn===true && (!msg.recipient||msg.recipient==="all"));
      return {ok:true,finished,toolCalls:toolMessages.length,dinoConfirmed};
    }catch(_){return {ok:false,error:"history_unreadable"};}
  }

  const MONITOR_TAB="tmMonitorOwnedTabId";
  async function safeToSwitch(t) {
    // Never navigate away from a user's draft or a GPT response in progress.
    try {
      const result=await inPage(t.id,() => {
        const input=document.querySelector('form [contenteditable="true"]');
        const form=input && input.closest("form");
        const hasDraft=!!(input && (input.innerText||"").trim());
        const hasChips=!!(form && form.querySelector("[app-mention-path]"));
        const responding=!!document.querySelector(
          'button[data-testid="stop-button"],button[aria-label="Stop generating"],button[aria-label="หยุดสร้าง"]');
        return {ready:!!input,hasDraft,hasChips,responding};
      });
      return !!(result&&result.ready&&!result.hasDraft&&!result.hasChips&&!result.responding);
    }catch(_){return false;}
  }
  async function reuseMonitorTab({blank=false}={}){
    const windowId=await injected.programWindowId();
    // Only an ID explicitly created/adopted by this extension may be
    // repurposed for a NEW project. The saved follow-up tabId can point to
    // the user's active ChatGPT conversation and must never be hijacked.
    const saved=(await chrome.storage.local.get(MONITOR_TAB));
    const candidates=[saved[MONITOR_TAB]].filter(id=>Number.isInteger(id)&&id>0);
    for (const id of candidates) {
      let t=null;
      try{t=await chrome.tabs.get(id);}catch(_){}
      if(!t||t.windowId!==windowId||!/^https:\/\/chatgpt\.com\//.test(t.url||t.pendingUrl||""))continue;
      if(blank&&(t.url||"")!=="https://chatgpt.com/"){
        if(!await safeToSwitch(t))
          throw Error("แท็บติดตามเดิมยังมีข้อความร่างหรือ GPT กำลังตอบ ห้ามเปิดแท็บใหม่ซ้ำ");
        t=await chrome.tabs.update(t.id,{url:"https://chatgpt.com/"});
      }else if(blank && !await safeToSwitch(t)) {
        throw Error("แท็บติดตามเดิมยังมีข้อความร่าง ห้ามเปิดแท็บใหม่ซ้ำ");
      }
      await chrome.storage.local.set({[MONITOR_TAB]:t.id});
      return t;
    }
    const t=await chrome.tabs.create({windowId,
      url:"https://chatgpt.com/",active:false,pinned:false});
    await chrome.tabs.update(t.id,{autoDiscardable:false}).catch(()=>{});
    await chrome.storage.local.set({[MONITOR_TAB]:t.id});
    return t;
  }
  async function tab(conf){
    // The user may have explicitly bound the existing project chat. Use
    // that tab only for the SAME conversation, not to start a new project.
    const windowId=await injected.programWindowId();
    if(conf.tabId){
      try{
        const existing=await chrome.tabs.get(conf.tabId);
        if(existing.windowId===windowId&&parse(existing.url||"")?.cid===conf.cid)return existing;
      }catch(_){}
    }
    const sameChat=(await chrome.tabs.query({windowId,url:"https://chatgpt.com/*"}))
      .find(t=>parse(t.pendingUrl||t.url||"")?.cid===conf.cid);
    if(sameChat)return sameChat;
    // All automatically opened monitor chats share the extension-owned tab.
    // Image workers stay separate so parallel image jobs are not interrupted.
    const t=await reuseMonitorTab();
    if(conf.tabId!==t.id){conf.tabId=t.id;await save(conf);}
    return t;
  }
  async function ready(t,cid){
    const target="https://chatgpt.com/c/"+cid;
    const matches=(raw)=>{
      try{const u=new URL(raw);return u.hostname==="chatgpt.com"&&u.pathname.endsWith("/c/"+cid);}
      catch(_){return false;}
    };
    if(!matches(t.url||"")&&!matches(t.pendingUrl||"")){
      if(!await safeToSwitch(t))
        throw Error("แท็บติดตามเดิมมีข้อความร่างหรือ GPT ยังตอบอยู่ ไม่สลับแชตทิ้ง");
      await chrome.tabs.update(t.id,{url:target});
    }
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
    let c;
    reportState().catch(()=>{});
    try{
      c=await load();
      if(!c.enabled||!c.cid||!injected)return;
      if(!force&&Date.now()<(c.retryAt||0))return;
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
      if(["sending","uncertain"].includes(c.phase)&&c.marker){
        if(!force&&c.phase==="uncertain"&&Date.now()<(c.nextAt||0))return;
        const t=await tab(c);
        await ready(t,c.cid);
        const check=await inPage(t.id,findMarker,[c.marker,c.cid]);
        if(check&&check.found){
          c.lastToolMarker=c.marker;c.lastToolAt=c.lastAt||Date.now();
          c.phase="idle";c.marker="";c.confirmedAt=Date.now();
          c.sentCount++;c.dailyCount++;c.errors=0;c.lastError="";
          c.nextAt=Date.now()+5*MIN;c.lastResult="recovered_confirmation";
        }else if(Date.now()-(c.lastAt||0)>=20*MIN){
          await finishFollowup(c,"uncertain","ยังยืนยันข้อความเดิมไม่ได้ ต้องตรวจในแชทก่อนส่งใหม่");
          return;
        }else{
          c.phase="uncertain";c.nextAt=Date.now()+2*MIN;
          c.lastError="กำลังตรวจข้อความเดิมอีกครั้ง";
        }
        await save(c);return;
      }
      if(c.lastToolMarker){
        const current=await tab(c);
        await ready(current,c.cid);
        let proof=null;
        try{proof=await inPage(current.id,inspectToolProof,[c.lastToolMarker,c.cid]);}
        catch(_){}
        if(proof&&proof.ok&&proof.finished){
          c.lastToolMarker="";
          c.lastResult=proof.dinoConfirmed?"dino_bot_invoked":
            proof.toolCalls?"other_tool_called_dino_not_verified":"no_tool_invocation";
          if(!proof.dinoConfirmed){
            c.lastError="GPT ไม่ยืนยันว่าเรียก Dino Bot Tunnel จริง ต้องติดตามแก้ไขต่อ";
            c.nextAt=Math.min(c.nextAt||Date.now()+5*MIN,Date.now()+5*MIN);
          }else{
            // A real tool invocation alone is not evidence of a repaired Auto.
            // The existing program's authenticated status must advance.
            let after=null;
            try{after=await status();}catch(_){}
            const before=c.lastProgress||{};
            const advanced=after && after.story===c.story && after.host===c.host && (
              (before.busy===false && after.busy===true) ||
              (after.stage && after.stage!==before.stage) ||
              Number(after.clips||0)>Number(before.clips||0) ||
              Number(after.images||0)>Number(before.images||0) ||
              after.effect_review_pending===true || after.complete===true
            );
            if(!advanced){
              c.lastResult="dino_invoked_repair_unverified";
              c.lastError="เรียกบอทแล้ว แต่ Auto ยังไม่ยืนยันว่ากลับมาทำงาน; ตรวจและแก้ต่อ";
              c.nextAt=Math.min(c.nextAt||Date.now()+5*MIN,Date.now()+5*MIN);
            }else{
              c.lastResult="dino_invoked_and_auto_advanced";
              c.lastError="";
            }
          }
          await save(c);
        }else{
          if(Date.now()-(c.lastToolAt||c.lastAt||Date.now())>20*MIN){
            c.lastResult="tool_invocation_unverified";
            c.lastError="GPT ไม่ยืนยันการเรียกบอทภายใน 20 นาที ตรวจแชตเดิมก่อนส่งซ้ำ";
          }
          c.nextAt=Date.now()+2*MIN;await save(c);return;
        }
      }
      if(c.errors||c.retryAt){c.errors=0;c.retryAt=0;await save(c);}
      if(!force&&Date.now()<(c.nextAt||0))return;
      // Do not send an unbound bot name or a Tailscale link for another PC.
      if(!live.monitor_bot || !live.tailscale_url){
        c.lastError="ไม่ได้ตั้งค่าบอทและลิงก์ Tailscale ของเครื่องนี้";
        c.nextAt=Date.now()+5*MIN;await save(c);return;
      }
      const s=live,now=Date.now(),m=minutes(s,c.lastProgress);
      c.lastProgress={clips:s.clips,images:s.images,busy:s.busy,
                      stage:String(s.stage||""),at:now};
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
          const sent=await inPage(t.id,submitOwnedMonitorDraft,[c.cid,owned,c.story,c.host]);
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
            c.phase="uncertain";c.nextAt=Date.now()+2*MIN;
            c.lastError="กดส่งข้อความติดตามแล้วแต่ยังไม่ยืนยัน ต้องตรวจในแชทก่อนส่งรอบใหม่";
            await save(c);return;
          }
          c.phase=s.complete?"complete":"idle";c.enabled=!s.complete;
          c.marker="";c.sentCount++;c.dailyCount++;c.confirmedAt=Date.now();
          c.lastToolMarker=owned;c.lastToolAt=Date.now();
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
      await chrome.tabs.update(t.id,{active:true});
      const lastCheck=await status();
      if(lastCheck.story!==c.story||lastCheck.host!==c.host){
        await finishFollowup(c,"wrong_project","The selected machine or story changed; follow-up stopped");
        return;
      }
      if(lastCheck.complete){await finishFollowup(c,"complete","");return;}
      if(lastCheck.effect_review_pending){
        await finishFollowup(c,"awaiting_effect_selection","");
        return;
      }
      const stillEnabled=await load();
      if(!stillEnabled.enabled||stillEnabled.stopRequested)return;
      if(typeof self.tmMonitorComposeWithApps!=="function")
        throw Error("Real ChatGPT app mention helper unavailable; plain text is forbidden");
      const result=await inPage(t.id,self.tmMonitorComposeWithApps,[{
        cid:c.cid,prompt,marker
      }]);
      if(!result || !result.attempted || !result.appMentionsVerified){
        c.phase="idle";c.marker="";c.nextAt=Date.now()+2*MIN;
        c.lastError=String(result&&result.error||"Cannot select both actual apps").slice(0,200);
        await save(c);return;
      }
      let confirmed=false;
      for(let attempts=0;attempts<16;attempts++){
        await delay(1000);
        try{
          const found=await inPage(t.id,findMarker,[marker,c.cid]);
          if(found&&found.found){confirmed=true;break;}
        }catch(_){}
      }
      if(!confirmed){
        if(result&&result.send_state==="not_sent"){
          c.phase="idle";c.marker="";c.nextAt=Date.now()+10*MIN;
          c.lastError=String(result.error||"ข้อความยังไม่ส่ง").slice(0,200);
        }else{
          c.phase="uncertain";c.nextAt=Date.now()+2*MIN;
          c.lastError="ยังยืนยันการส่งไม่ได้ จะตรวจข้อความเดิมอีกครั้ง";
        }
        await save(c);return;
      }
      c.phase=s.complete?"complete":"idle";c.enabled=!s.complete;
      c.marker="";c.sentCount++;c.dailyCount++;c.confirmedAt=Date.now();
      c.errors=0;
      // Message delivery and app selection are proven. Whether GPT actually
      // invoked Dino's remote tool (and repaired Auto) is not proven here.
      c.lastResult=s.complete?"finished_sent":"sent_with_real_apps_awaiting_tool_proof";
      c.lastToolMarker=marker;
      c.lastToolAt=Date.now();
      c.nextAt=s.complete?0:Date.now()+m*MIN;c.lastError="";await save(c);
    }catch(e){
      if(!c)return;
      c=await load();
      if(!c.enabled||c.stopRequested)return;
      if(c.phase==="sending"){
        c.phase="uncertain";c.nextAt=Date.now()+2*MIN;
        c.lastError="เกิดข้อผิดพลาดหลังเริ่มส่ง ต้องตรวจแชทก่อน: "+String(e.message||e).slice(0,150);
      }else{
        c.errors=(c.errors||0)+1;
        c.lastError=String(e.message||e).slice(0,200);
        c.retryAt=Date.now()+Math.min(10,c.errors*2)*MIN;
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
  // Called through the program's EXISTING /job relay before story analysis.
  // A separate, real chat is created for each project key. Never repeat a
  // possibly sent first message just because Chrome or GPT answered slowly.
  self.tmFollowupBootstrap=async function(job){
    if(!injected||!self.tmMonitorComposeWithApps)
      return {error:"Tidmunz Chrome app-mention bridge is unavailable"};
    const projectKey=String(job.project_key||"");
    const story=String(job.story||"").trim(),host=String(job.host||"").trim();
    if(!/^[a-f0-9]{64}$/.test(projectKey)||!story||story.length>160||
       !/^DESKTOP-[A-Za-z0-9-]{4,40}$/.test(host))
      return {error:"Invalid story/device bootstrap key"};
    const live=await status();
    if(live.story!==story||live.host.toUpperCase()!==host.toUpperCase())
      return {error:"Project/host changed; refusing wrong-machine chat"};
    if(live.complete||live.effect_review_pending)
      return {error:"Project already passed the monitor handoff"};
    let c=await load();
    const KEY="tmMonitorStoryChats", PENDING="tmMonitorBootstrapPending";
    const all=(await chrome.storage.local.get([KEY,PENDING]));
    const existing=all[KEY]||{},mapped=existing[projectKey];
    const priorUncertain=c.phase==="sending"||c.phase==="uncertain";
    const requested=parse(job.existing_url);
    const savedPending=all[PENDING];
    const sameStoryPending=savedPending && savedPending.story===story &&
      String(savedPending.host).toUpperCase()===host.toUpperCase();
    const replacementAllowed=job.wake===true && !mapped;
    if(priorUncertain && !mapped && !sameStoryPending &&
       !(replacementAllowed && c.story===story && c.host===host))
      return {error:"Earlier follow-up unconfirmed; no reserved chat for safe recovery"};
    if(mapped && (mapped.story!==story || mapped.host!==host))
      return {error:"Saved monitor chat belongs to another machine or story"};
    if(mapped && requested && mapped.cid!==requested.cid && mapped.replacedCid!==requested.cid)
      return {error:"Project key is bound to another chat; reconcile before continuing"};
    if(requested && !mapped && !replacementAllowed)
      return {error:"Project has a chat URL but Chrome has no confirmed app-bound record; reconcile manually"};
    let binding=mapped||null;
    async function bind(entry){
      const parsed=parse(entry.url);
      if(!parsed)throw Error("Invalid confirmed ChatGPT conversation URL");
      if(c.enabled && c.host===host && c.story===story && c.cid===parsed.cid){
        if(job.wake && c.phase==="idle"){
          c.nextAt=Date.now();c.retryAt=0;c.errors=0;
          await save(c);
          if(!await chrome.alarms.get?.(ALARM))
            await chrome.alarms.create(ALARM,{periodInMinutes:1});
        }
        return {ok:true,cid:parsed.cid,url:parsed.url,reused:true,real_apps:2};
      }
      if(priorUncertain){
        // Preserve the older uncertain follow-up receipt as audit evidence.
        // This never resends its marker or treats it as a new chat message.
        await chrome.storage.local.set({tmMonitorPreviousUncertain:{
          marker:c.marker||"",cid:c.cid||"",story:c.story||"",
          phase:c.phase,lastResult:c.lastResult||"",archivedAt:Date.now()
        }});
      }
      c.enabled=true;c.stopRequested=false;c.phase="idle";c.marker="";
      c.lastToolMarker="";c.lastToolAt=0;c.lastProgress=null;
      c.cid=parsed.cid;c.url=parsed.url;c.host=host;c.story=story;
      c.errors=0;c.retryAt=0;c.lastError="";c.lastResult="project_chat_bound";
      c.nextAt=Date.now()+(job.wake?0:MIN);
      await save(c,{allowRestart:true});
      await chrome.alarms.create(ALARM,{periodInMinutes:1});
      return {ok:true,cid:parsed.cid,url:parsed.url,reused:!!entry.reused,real_apps:2};
    }
    if(binding){
      const result=await bind(binding);
      if(!mapped){
        existing[projectKey]={url:result.url,cid:result.cid,story,host};
        await chrome.storage.local.set({[KEY]:existing});
      }
      return result;
    }
    let pending=savedPending, t;
    let replacement=Boolean(requested && replacementAllowed);
    if(pending && pending.projectKey!==projectKey && !(replacementAllowed && sameStoryPending))
      return {error:"Another project chat creation is awaiting confirmation; no duplicates"};
    if(pending){
      try{t=await chrome.tabs.get(pending.tabId);}catch(_){}
      if(t){
        if(t.windowId!==await injected.programWindowId())
          return {error:"Reserved chat is outside the Studio Chrome window"};
        await chrome.storage.local.set({[MONITOR_TAB]:t.id});
      }else{
        if(!replacementAllowed || !sameStoryPending || pending.replacement)
          return {error:"An earlier story-chat send may have succeeded; its tab is missing; manual reconciliation required"};
        await chrome.storage.local.set({tmMonitorPreviousBootstrap:{
          ...pending,archivedAt:Date.now()
        }});
        await chrome.storage.local.remove(PENDING);
        pending=null;
        replacement=true;
      }
    }
    if(!pending){
      // The next project must navigate our one owned monitor tab rather than
      // append another ChatGPT tab per project or per failed bootstrap.
      try{t=await reuseMonitorTab({blank:true});}
      catch(e){return {error:String(e.message||e)};}
      pending={projectKey,story,host,tabId:t.id,marker:"TMB-"+Date.now(),
               attempted:false,replacement,createdAt:Date.now()};
      await chrome.storage.local.set({[PENDING]:pending});
    }
    let cid=null;
    async function discover(){
      const tab=await chrome.tabs.get(t.id);
      const found=parse(tab.url||"");
      if(!found)return false;
      cid=found.cid;
      try{const check=await inPage(t.id,findMarker,[pending.marker,cid]);return !!(check&&check.found);}
      catch(_){return false;}
    }
    if(!pending.attempted){
      // Check the actual reserved tab before the FIRST send. If it has
      // navigated to a conversation already, the send may have succeeded.
      // Never send a second first-message under that ambiguous condition.
      const reserved=await chrome.tabs.get(t.id);
      if((reserved.url||"").split("?")[0]!=="https://chatgpt.com/")
        return {error:"Reserved story tab no longer blank; reconcile original send, do not retry"};
      for(let attempt=0;attempt<36;attempt++){
        try{
          const check=await inPage(t.id,()=>{
            return location.hostname==="chatgpt.com" && location.pathname==="/" &&
              !!document.querySelector('[contenteditable="true"]');
          });
          if(check)break;
        }catch(_){}
        await delay(700);
        if(attempt===35)return {error:"New ChatGPT composer not ready"};
      }
      await chrome.tabs.update(t.id,{active:true});
      const prompt="[Tidmunz Studio | เริ่มแชตติดตามเรื่อง | "+pending.marker+"]\n"+
        "เรื่อง: "+story+"; เครื่อง: "+host+". นี่คือแชตหลักสำหรับติดตามเรื่องนี้เท่านั้น. "+
        "ให้ใช้ Tidmunz Studio AI Operator ร่วมกับ Dino Bot Tunnel ของเครื่องนี้จริง: "+
        "ตรวจยืนยันเครื่องและสถานะ Auto แบบอ่านอย่างเดียวก่อน ห้ามสร้างคลิปหรือแก้ไฟล์ในการเริ่มแชต. "+
        "เมื่อส่วนขยายส่งข้อความติดตามในรอบถัดไป จึงค่อยตรวจ แก้ไขเมื่อปลอดภัย สั่งทำต่อ และยืนยันผล. "+
        "ห้ามใช้บอทจากเครื่องอื่น ห้ามส่งงานที่มี UUID รอผลซ้ำ และหยุดก่อนรวมวิดีโอเพื่อรอเลือกเสียง.";
      pending.attempted=true;
      await chrome.storage.local.set({[PENDING]:pending});
      const result=await inPage(t.id,self.tmMonitorComposeWithApps,[{prompt,marker:pending.marker}]);
      if(!result || !result.attempted){
        if(result?.attempted===false){
          pending.attempted=false;
          await chrome.storage.local.set({[PENDING]:pending});
        }
        return {error:"Cannot select real apps in new chat: "+
          String(result&&result.error||"unknown").slice(0,150)};
      }
    }
    let confirmed=false;
    for(let i=0;i<75;i++){
      await delay(1000);
      if(await discover()){confirmed=true;break;}
    }
    if(!confirmed)
      return {error:"Story-chat send unconfirmed; check the dedicated Chrome tab before retrying"};
    binding={cid,url:"https://chatgpt.com/c/"+cid,story,host,
             ...(requested && {replacedCid:requested.cid})};
    existing[projectKey]=binding;
    await chrome.storage.local.set({[KEY]:existing});
    await chrome.storage.local.remove(PENDING);
    return await bind(binding);
  };

  self.tmFollowupReport=()=>reportState().catch(()=>{});
  self.tmFollowupInit=(callbacks)=>{
    if(injected)return;
    const programWindowId=callbacks.programWindowId || (async()=>{
      const windows=await chrome.windows.getAll({windowTypes:["normal"]});
      if(windows.length!==1)throw Error("ต้องมีหน้าต่าง Chrome ของ Tidmunz Studio หนึ่งหน้าต่าง");
      return windows[0].id;
    });
    injected={page:callbacks.inPage,send:callbacks.pageSend,getLink:callbacks.getLink,programWindowId};
    load().then(async c=>{
      if(c.enabled&&!(await chrome.alarms.get?.(ALARM)))
        await chrome.alarms.create(ALARM,{periodInMinutes:1});
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
      c.host=s.host;c.story=s.story;c.stopRequested=false;c.errors=0;c.retryAt=0;
          c.lastToolMarker="";c.lastToolAt=0;c.lastProgress=null;
          c.phase="idle";c.lastError="";await save(c,{allowRestart:true});
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
          if(c.enabled||c.phase!=="uncertain"||!c.marker)return {ok:false,error:"ไม่มีข้อความค้างให้ตรวจ"};
          const live=await status();
          if(live.host!==c.host||live.story!==c.story||live.complete||live.effect_review_pending)
            return {ok:false,error:"โปรเจกต์เดิมไม่พร้อมติดตาม"};
          const t=await tab(c);
          await ready(t,c.cid);
          const check=await inPage(t.id,findMarker,[c.marker,c.cid]);
          if(!check.found)return {ok:false,error:"ยังไม่ยืนยันข้อความรอบก่อน ห้ามส่งซ้ำ"};
          c.lastToolMarker=c.marker;c.lastToolAt=c.lastAt||Date.now();
          c.phase="idle";c.enabled=true;c.stopRequested=false;c.marker="";c.lastError="";
          c.confirmedAt=Date.now();c.nextAt=Date.now()+5*MIN;
      await save(c,{allowRestart:true});chrome.alarms.create(ALARM,{periodInMinutes:1});
      return {ok:true};
        }
        if(msg.type==="tm_followup_now"){
          const c=await load();
          if(!c.enabled||!["idle","uncertain"].includes(c.phase))return {ok:false,error:"ยังไม่พร้อมตรวจ"};
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
