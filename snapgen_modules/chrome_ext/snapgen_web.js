// SnapGen Web image generation inside the existing Tidmunz ChatGPT extension.
// Uses the real SnapGen web UI and the existing Chrome Google profile.
// No SnapGen generation API requests are made here. Fail closed on unknown sends.
const SNAPGEN_IMAGE_PAGE = "https://snapgen.ai/app/imagen/?provider=grok";
const COMPANY_MARKER = /tidmunz|ติดมัน/i;
const SNAPGEN_WAIT_MS = 9 * 60 * 1000;
const pauseSnap = ms => new Promise(resolve => setTimeout(resolve, ms));

async function snapInPage(tabId, fn, args = []) {
  const out = await chrome.scripting.executeScript({
    target: {tabId}, world: "MAIN", func: fn, args,
  });
  return out && out[0] ? out[0].result : null;
}
async function snapTab() {
  const stored = await chrome.storage.local.get("snapgenWebTabId");
  let tab = null;
  if (stored.snapgenWebTabId) {
    try {
      const got = await chrome.tabs.get(stored.snapgenWebTabId);
      if (/^https:\/\/snapgen\.ai\//.test(got.url || "")) tab = got;
    } catch (_) {}
  }
  if (!tab) {
    const wins = await chrome.windows.getAll({windowTypes:["normal"]});
    tab = await chrome.tabs.create({
      url: SNAPGEN_IMAGE_PAGE, active: false,
      ...(wins.length ? {windowId: wins[0].id} : {}),
    });
    await chrome.storage.local.set({snapgenWebTabId:tab.id});
  } else if ((tab.url || "") !== SNAPGEN_IMAGE_PAGE) {
    await chrome.tabs.update(tab.id,{url:SNAPGEN_IMAGE_PAGE});
  }
  return tab.id;
}
async function snapWait(tabId, check, timeoutMs = 35000) {
  const deadline=Date.now()+timeoutMs;
  while(Date.now()<deadline){
    try {
      const x=await snapInPage(tabId,check);
      if(x && x.ready)return x;
    } catch (_) {}
    await pauseSnap(900);
  }
  throw new Error("SnapGen Web page did not become ready");
}
function snapPageInfo() {
  const text = (document.body && document.body.innerText || "").slice(0,25000);
  const m = text.match(/Credits:\s*([\d,.]+)\s*remaining/i);
  const c = text.match(/This generation will cost:\s*([\d,.]+)\s*Credits/i);
  const emails = [...text.matchAll(/[\w.+%-]+@[\w.-]+\.[a-z]{2,}/gi)].map(x=>x[0]);
  const buttons = [...document.querySelectorAll("button")].map(x=>x.textContent.trim()).filter(Boolean);
  const textMarker = (text.match(/Tidmunz Studio|ติดมันส์\s*สตูดิโอ/ig) || []).length > 0;
  return {ready:!!document.body && !!text,
    url:location.href, loggedOut:buttons.some(x=>/^login$|^sign in$|เข้าสู่ระบบ$/i.test(x)),
    credits:m?Number(m[1].replace(/,/g,"")):null,
    cost:c?Number(c[1].replace(/,/g,"")):null,
    company:emails.some(e=>/tidmunz|ติดมัน/i.test(e)) || textMarker,
    buttons:buttons.slice(0,25)};
}
function snapClickText(want) {
  const b=[...document.querySelectorAll("button,a")].find(x=>String(x.textContent||"").trim().toLowerCase()===String(want).toLowerCase());
  if (!b) return {clicked:false};
  b.click(); return {clicked:true};
}
function snapPickCompanyGoogle() {
  if (location.hostname !== "accounts.google.com") return {status:"wrong_origin"};
  // Only select a *displayed* existing account with the company marker.
  // Never enter passwords or select another Google identity.
  const choices=[...document.querySelectorAll("[data-identifier],[data-email],[role=link],[role=button],li")];
  const target=choices.filter(e=>e.getBoundingClientRect().width>0)
    .find(e=>/tidmunz|ติดมัน/i.test((e.getAttribute("data-identifier") || "")+" "+(e.getAttribute("data-email")||"")+" "+(e.innerText||"").slice(0,220)));
  if (!target) return {status:"company_missing"};
  const label=(target.getAttribute("data-identifier")||target.getAttribute("data-email")||target.innerText||"");
  if (!/tidmunz|ติดมัน/i.test(label)) return {status:"company_missing"};
  target.click();
  return {status:"company_selected"};
}
async function snapLogin(tabId) {
  let verifiedCompany=false;
  // A user may have completed the OAuth step manually in THIS program profile.
  try {
    const existing=await snapInPage(tabId,snapPageInfo);
    const proof=(await chrome.storage.local.get("snapgenWebCompanyVerifiedUntil")).snapgenWebCompanyVerifiedUntil;
    if(existing && existing.loggedOut) {
      await chrome.storage.local.remove("snapgenWebCompanyVerifiedUntil");
    }
    const priorVerified=Number(proof)>Date.now();
    if(existing && !existing.loggedOut && Number(existing.credits)>0 &&
       (existing.company || priorVerified)) {
      await chrome.storage.local.remove("snapgenWebCompanyLoginFailures");
      return {ok:true,attempt:0,company:true};
    }
  }catch(_){}
  const stored=await chrome.storage.local.get("snapgenWebCompanyLoginFailures");
  const previous=Math.min(3,Math.max(0,Number(stored.snapgenWebCompanyLoginFailures)||0));
  if(previous>=3) return {ok:false,attempts:3,code:"login_required",
    error:"SnapGen Web: ล็อกอิน Google บริษัทไม่ผ่านครบ 3 ครั้ง — กรุณาเลือกบัญชีติดมันส์ด้วยตัวเองหนึ่งครั้งใน Chrome ของ Tidmunz Studio",
    send_state:"not_sent"};
  for(let attempt=previous+1;attempt<=3;attempt++){
    await chrome.storage.local.set({snapgenWebCompanyLoginFailures:attempt});
    // Preserve an already authenticated *verified* company session.
    try {
      const info=await snapInPage(tabId,snapPageInfo);
      if(info && !info.loggedOut && info.company && Number(info.credits)>0)
        return {ok:true,attempt,company:true};
    }catch(_){}
    await chrome.tabs.update(tabId,{url:"https://snapgen.ai/auth/login"});
    let login;
    try {login=await snapWait(tabId,() => ({
      ready:location.hostname==="snapgen.ai" && location.pathname.startsWith("/auth/login") &&
             [...document.querySelectorAll("button")].some(x=>x.textContent.trim()==="Google"),
      url:location.href,
    }),25000);}catch(_){continue;}
    let clicked = false;
    try {clicked=!!(await snapInPage(tabId,snapClickText,["Google"])).clicked;}catch(_){}
    if(!clicked)continue;
    // Website opens an ordinary Google OAuth popup. Inspect only the popup
    // specifically created for SnapGen, not unrelated Google account tabs.
    const started=Date.now();
    let selected=false;
    while(Date.now()-started<18000){
      const tabs=await chrome.tabs.query({});
      const popup=tabs.find(t => /^https:\/\/accounts\.google\.com\//.test(t.url||"") &&
                                    (t.url||"").includes("snapgen.ai"));
      if(popup){
        try{
          const pick=await snapInPage(popup.id,snapPickCompanyGoogle);
          if(pick && pick.status==="company_selected") {
            selected=true; verifiedCompany=true; break;
          }
        }catch(_){}
      }
      await pauseSnap(800);
    }
    // A single visible Google sign-in flow can complete with the already
    // selected account. If so the SnapGen profile must still prove company.
    for(let wait=0;wait<16;wait++){
      await pauseSnap(1000);
      try {
        const info=await snapInPage(tabId,snapPageInfo);
        if(info && !info.loggedOut && Number(info.credits)>0 &&
           (info.company || (selected && verifiedCompany))) {
          await chrome.tabs.update(tabId,{url:SNAPGEN_IMAGE_PAGE});
          await snapWait(tabId,()=>({ready:location.hostname==="snapgen.ai" &&
                                     location.pathname.startsWith("/app/imagen")}),20000);
          await chrome.storage.local.remove("snapgenWebCompanyLoginFailures");
          return {ok:true,attempt,company:true};
        }
      }catch(_){}
    }
  }
  return {ok:false,attempts:3,
    error:"SnapGen Web: ล็อกอินบัญชี Google บริษัทติดมันส์พร้อมเครดิตไม่สำเร็จครบ 3 ครั้ง — กรุณาล็อกอินด้วยตัวเองหนึ่งครั้งใน Chrome ของ Tidmunz Studio",
    send_state:"not_sent",code:"login_required"};
}
async function snapFill(tabId, job) {
  // All options are set in the web form; the visible price is checked once
  // more after the options/references have changed.
  return snapInPage(tabId,async (prompt, refs, ratio)=>{
    if(location.hostname!=="snapgen.ai"||!location.pathname.startsWith("/app/imagen"))
      return {error:"wrong page"};
    if(ratio!=="16:9")return {error:"Only 16:9 SnapGen Web Grok is supported"};
    if(refs.length>5)return {error:"SnapGen Web: เกิน 5 รูปอ้างอิงที่ทดสอบได้"};
    const choose=label=>{
      const el=[...document.querySelectorAll("label")].find(x=>x.innerText.trim()===label);
      if(el){el.click();return true;}return false;
    };
    if(!choose("1K") || !choose("Landscape (16:9)"))return {error:"Grok 1K 16:9 option unavailable"};
    const results=[...document.querySelectorAll("label,[role=radio]")].find(x=>x.innerText.trim()==="1");
    if(results)results.click();
    const images=[];
    for(let i=0;i<refs.length;i++){
      const raw=String(refs[i]||"");
      const found=raw.match(/^data:(image\/(?:png|jpeg|webp));base64,([\s\S]+)$/);
      if(!found)return {error:"Invalid reference image"};
      const bytes=Uint8Array.from(atob(found[2]),x=>x.charCodeAt(0));
      if(bytes.length>10*1024*1024)return {error:"Reference is above 10 MB"};
      const file=new File([bytes],"reference_"+(i+1)+(found[1]==="image/png"?".png":found[1]==="image/webp"?".webp":".jpg"),{type:found[1]});
      const select=[...document.querySelectorAll("button")].find(x=>x.textContent.trim()==="Select Image");
      if(!select)return {error:"Select Image button missing"};
      select.click();
      for(let n=0;n<18&&!document.querySelector("input[type=file]");n++)
        await new Promise(r=>setTimeout(r,250));
      const input=document.querySelector("input[type=file]");
      if(!input)return {error:"Image upload control unavailable"};
      const dt=new DataTransfer();dt.items.add(file);input.files=dt.files;
      input.dispatchEvent(new Event("change",{bubbles:true}));
      for(let n=0;n<30;n++){
        await new Promise(r=>setTimeout(r,300));
        if((document.body.innerText||"").includes("@image"+(i+1)))break;
      }
      if(!(document.body.innerText||"").includes("@image"+(i+1)))
        return {error:"Reference upload could not be verified"};
      images.push("@image"+(i+1));
    }
    const text=(images.join(" ")+"\n"+String(prompt||"")).trim();
    const area=document.querySelector("textarea[placeholder*='Describe the image']");
    if(!area || !text || text.length>5000)return {error:"Image prompt missing or above website limit"};
    const setter=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,"value").set;
    setter.call(area,text);area.dispatchEvent(new Event("input",{bubbles:true}));
    await new Promise(r=>setTimeout(r,650));
    const page=document.body.innerText;
    const cost=(page.match(/This generation will cost:\s*([\d,.]+)\s*Credits/i)||[])[1];
    const left=(page.match(/Credits:\s*([\d,.]+)\s*remaining/i)||[])[1];
    const buttons=[...document.querySelectorAll("button")];
    const button=buttons.find(x=>x.innerText.includes("Generate with Grok"));
    const credits=left===undefined?null:Number(left.replace(/,/g,""));
    const price=cost===undefined?null:Number(cost.replace(/,/g,""));
    const before=[...document.images].map(x=>x.currentSrc||x.src);
    return {ready:!!button&&!button.disabled,price,credits,button:!!button,
      before,ratio:"16:9",references:images.length,prepared:true};
  },[job.prompt,job.images||[],job.aspect_ratio||"16:9"]);
}
function snapClickGenerate() {
  const button=[...document.querySelectorAll("button")].find(x=>x.innerText.includes("Generate with Grok"));
  if(!button || button.disabled)return {clicked:false};
  button.click();
  return {clicked:true,at:Date.now()};
}
async function snapResult(tabId,before) {
  return snapInPage(tabId,async previous=>{
    const set=new Set(previous||[]);
    const all=[...document.images].filter(x=>x.naturalWidth>=600 && x.naturalHeight>=300 &&
       !set.has(x.currentSrc||x.src) && !/^data:/.test(x.src||""));
    // New images after Generate are ranked by proximity to the current output controls.
    for(const img of all.reverse()){
      const url=img.currentSrc||img.src;
      try{
        const response=await fetch(url,{credentials:"include"});
        if(!response.ok)continue;
        const blob=await response.blob();
        if(!blob.type.startsWith("image/")||blob.size<15000)continue;
        const data=await new Promise(resolve=>{
          const reader=new FileReader();reader.onload=()=>resolve(reader.result);
          reader.onerror=()=>resolve(null);reader.readAsDataURL(blob);
        });
        if(data)return {done:true,images:[data]};
      }catch(_){}
    }
    const text=document.body?document.body.innerText:"";
    if(/insufficient credits|not enough credits|generation failed|generation error|เครดิตไม่เพียงพอ/i.test(text))
      return {error:"SnapGen Web generation failed / not enough credits",send_state:"sent"};
    return {done:false};
  },[before]);
}
async function snapgenWebJob(job, recoverNavigation = true) {
  if(job.aspect_ratio!=="16:9" || job.model!=="grok-image")
    return {error:"SnapGen Web only supports Grok image 1K 16:9 in this fallback",send_state:"not_sent"};
  let tabId=null, clicked=false, heart=null;
  try{
    tabId=await snapTab();
    heart=setInterval(()=>{relay("/progress",{id:job.id,phase:"waiting"}).catch(()=>{});},4000);
    await snapWait(tabId,()=>({ready:location.hostname==="snapgen.ai" &&
      location.pathname.startsWith("/app/imagen") && !!document.querySelector("textarea")}),40000);
    const login=await snapLogin(tabId);
    if(!login.ok)return {error:login.error,send_state:"not_sent",code:login.code};
    const page=await snapWait(tabId,()=>({ready:location.hostname==="snapgen.ai" &&
      location.pathname.startsWith("/app/imagen") && !!document.querySelector("textarea")}),35000);
    const filled=await snapFill(tabId,job);
    if(!filled || filled.error)return {error:"SnapGen Web: "+(filled&&filled.error||"form unavailable"),send_state:"not_sent"};
    if(!filled.prepared || !filled.ready)
      return {error:"SnapGen Web: ยังไม่พร้อมกด Generate หรือยังไม่ได้แนบ Ref",send_state:"not_sent"};
    if(!Number.isFinite(filled.price) || filled.price<=0 || filled.price>3 ||
       !Number.isFinite(filled.credits) || filled.credits<filled.price ||
       filled.price>Number(job.price_ceiling||3)) {
      return {error:"SnapGen Web: ราคาหน้าเว็บเกิน 3 เครดิต/รูปหรือเครดิตไม่พอ — ไม่กดสร้าง",
        send_state:"not_sent",provider_status:402};
    }
    const pushed=await snapInPage(tabId,snapClickGenerate);
    if(!pushed || !pushed.clicked)
      return {error:"SnapGen Web generate button was not clickable",send_state:"not_sent"};
    clicked=true;
    const deadline=Date.now()+SNAPGEN_WAIT_MS;
    while(Date.now()<deadline){
      await pauseSnap(2500);
      const response=await snapResult(tabId,filled.before).catch(()=>null);
      if(response && response.done && (response.images||[]).length) {
        return {...response,web_price:filled.price,account_source:"company_google",send_state:"sent"};
      }
      if(response && response.error)
        return {...response,web_price:filled.price,send_state:"sent"};
    }
    return {error:"SnapGen Web accepted Generate but no image was recoverable — check website history, do not send again",
      send_state:"sent",code:"result_unknown"};
  }catch(e){
    const detail=String(e&&e.message||e);
    if (!clicked && recoverNavigation && /navigation rejected|no tab with id|no current window/i.test(detail)) {
      // A navigation rejected BEFORE the paid Generate click is definitely safe
      // to recover in a fresh dedicated tab. Never recover after clicking.
      if (heart) { clearInterval(heart); heart=null; }
      await chrome.storage.local.remove("snapgenWebTabId").catch(()=>{});
      return snapgenWebJob(job,false);
    }
    return {error:"SnapGen Web: "+detail.slice(0,400),
      send_state:clicked?"unknown":"not_sent"};
  }finally{
    if(heart)clearInterval(heart);
  }
}
self.snapgenWebJob=snapgenWebJob;


// Inspection is non-paid and runs only in the program Chrome's extension profile.
async function snapgenWebInspect(job) {
  const tabId=await snapTab();
  if (job && job.manual_company_verified === true) {
    // Applied only after the trusted native UI selected the identifiable
    // Tidmunz company Google account and SnapGen displayed positive credits.
    // Scoped to the program profile; expires after one day and cleared on logout.
    await snapWait(tabId,()=>({ready:location.hostname==="snapgen.ai" &&
      location.pathname.startsWith("/app/imagen")}),30000);
    const info=await snapInPage(tabId,snapPageInfo);
    if(!info || info.loggedOut || !(Number(info.credits)>0))
      return {error:"Cannot verify an authenticated account with credits",send_state:"not_sent"};
    await chrome.storage.local.set({snapgenWebCompanyVerifiedUntil:Date.now()+24*60*60*1000});
    await chrome.storage.local.remove("snapgenWebCompanyLoginFailures");
    return {ok:true,verified_company_from_native_google_selection:true,
            credits:info.credits,paid_job_sent:false};
  }
  if (job && job.account_probe === true) {
    await snapWait(tabId,()=>({ready:location.hostname==="snapgen.ai" &&
      location.pathname.startsWith("/app/imagen")}),30000);
    const info=await snapInPage(tabId,()=>{
      const header=document.querySelector("header");
      if(!header)return {error:"header unavailable"};
      return {controls:[...header.querySelectorAll("button")].map((x,i)=>({
          i, text:(x.innerText||"").slice(0,70), html:x.outerHTML.slice(0,950)
        })).slice(-12)};
    });
    return {ok:true,account_ui:info,paid_job_sent:false};
  }
  if (job && job.page_probe === true) {
    const tabs=await chrome.tabs.query({});
    const out=[];
    for (const t of tabs) {
      if(!/^https:\/\/(snapgen\.ai|accounts\.google\.com)\//.test(t.url||""))continue;
      let ui=null;
      try {ui=await snapInPage(t.id,()=>({
        host:location.hostname,path:location.pathname,title:document.title,
        text:(document.body&&document.body.innerText||"").slice(0,1450),
        buttons:[...document.querySelectorAll("button")].map(x=>x.textContent.trim()).filter(Boolean).slice(0,25),
        controls:[...document.querySelectorAll("header button,header a,nav button,nav a")].slice(0,30)
          .map(x=>({text:(x.innerText||"").trim().slice(0,55),
                    title:x.getAttribute("title"),aria:x.getAttribute("aria-label"),
                    slot:x.getAttribute("data-slot"),
                    outer:x.outerHTML.slice(0,280)}))
      }));}catch(e){ui={error:String(e.message||e).slice(0,130)};}
      out.push({id:t.id,active:t.active,tab_status:t.status,ui});
    }
    return {ok:true,profile:"tidmunz_program",paid_job_sent:false,tabs:out};
  }
  if (job && job.auth_probe === true) {
    // Single, user-authorized Google button click in the same program Chrome.
    // Diagnostic ONLY: do not select an account until identity is inspected.
    const tab=await chrome.tabs.get(tabId);
    await chrome.windows.update(tab.windowId,{state:"normal",left:95,top:55,width:1080,height:785,focused:true});
    await chrome.tabs.update(tabId,{url:"https://snapgen.ai/auth/login",active:true});
    await snapWait(tabId,()=>({ready:location.hostname==="snapgen.ai" &&
      location.pathname.startsWith("/auth/login") &&
      [...document.querySelectorAll("button")].some(x=>x.textContent.trim()==="Google")}),25000);
    const clicked=await snapInPage(tabId,snapClickText,["Google"]);
    if(!clicked || !clicked.clicked)return {error:"Google button was not found",send_state:"not_sent"};
    await pauseSnap(4200);
    const tabs=await chrome.tabs.query({});
    const result=[];
    for(const target of tabs) {
      const origin=String(target.url||"");
      if(!/^https:\/\/(accounts\.google\.com|snapgen\.ai)\//.test(origin))continue;
      if(!/^https:\/\/accounts\.google\.com\//.test(origin) && target.id!==tabId)continue;
      let info=null;
      try {info=await snapInPage(target.id,()=>({
        path:location.pathname,
        title:document.title,
        text:(document.body&&document.body.innerText||"").slice(0,1600),
        choices:[...document.querySelectorAll("[data-identifier],[data-email]")].slice(0,15)
          .map(e=>({identifier:e.getAttribute("data-identifier")||e.getAttribute("data-email")||"",
                    text:(e.innerText||"").slice(0,130)}))
      }));}catch(e){info={error:String(e.message||e).slice(0,100)};}
      result.push({google:origin.startsWith("https://accounts.google.com/"),tab_id:target.id,info});
    }
    return {ok:true,google_clicked:true,paid_job_sent:false,tabs:result};
  }
  if (job && job.manual_login === true) {
    // The automatic 3-attempt budget was exhausted; do not silently repeat.
    await chrome.storage.local.set({snapgenWebCompanyLoginFailures:3});
    // Reveal ONLY this extension's Chrome: the Tidmunz Studio profile.
    const tab=await chrome.tabs.get(tabId);
    await chrome.tabs.update(tabId,{url:"https://snapgen.ai/auth/login",active:true});
    await chrome.windows.update(tab.windowId,{
      state:"normal",left:100,top:65,width:1080,height:790,focused:true
    });
    return {ok:true,manual_login_required:true,
            browser:"Tidmunz Studio Chrome",paid_job_sent:false};
  }
  await snapWait(tabId,()=>({
    ready:location.hostname==="snapgen.ai" &&
      location.pathname.startsWith("/app/imagen") &&
      !!document.querySelector("textarea")
  }),35000);
  if(job && job.login === true) {
    const login=await snapLogin(tabId);
    if(!login.ok)return {error:login.error,code:login.code,
                          send_state:"not_sent",attempts:login.attempts};
  }
  const info=await snapInPage(tabId,snapPageInfo);
  return {ok:true,channel:"snapgen_web_grok",profile:"tidmunz_program",
          logged_out:!!info.loggedOut,company_verified:!!info.company,
          credits:Number.isFinite(info.credits)?info.credits:null,
          visible_price:Number.isFinite(info.cost)?info.cost:null};
}
self.snapgenWebInspect=snapgenWebInspect;
