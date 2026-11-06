// Tidmunz ChatGPT: runs Tidmunz Studio's ChatGPT jobs in this Chrome's own ChatGPT tab.
// Tidmunz (127.0.0.1) hands out jobs; at most two image jobs run in isolated tabs. Text is serial.
// Each worker types the prompt, attaches
// reference pictures, waits for ChatGPT to finish and sends back the text / pictures.
// Pairing: a folder install gets port + token from config.js; the Chrome Web Store build
// asks Tidmunz for them at /pair (Tidmunz only answers requests coming from an extension).
try { importScripts("config.js"); } catch (e) { self.TZ_CONFIG = null; }

const PORTS = [8766, 8767, 8768];
const JOB_LIMIT_MS = 12 * 60 * 1000;
const CHAT_JOB_LIMIT_MS = 3 * 60 * 1000;
let running = false;
let link = self.TZ_CONFIG || null;  // {port, token}

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function pair() {
  if (self.TZ_CONFIG) return self.TZ_CONFIG;
  for (const port of PORTS) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/pair`);
      if (response.ok) {
        const data = await response.json();
        if (data && data.token) return {port, token: data.token};
      }
    } catch (e) {}
  }
  return null;
}

async function relay(path, body) {
  if (!link) link = await pair();
  if (!link) throw new Error("Tidmunz is not open");
  const url = `http://127.0.0.1:${link.port}${path}${path.includes("?") ? "&" : "?"}token=${encodeURIComponent(link.token)}`;
  const opts = body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)};
  const response = await fetch(url, opts);
  if (response.status === 403 && !self.TZ_CONFIG) link = null;  // Tidmunz restarted with a new token: pair again
  if (response.status === 204) return null;
  if (!response.ok) throw new Error(`relay ${response.status}`);
  return response.json();
}

function badge(text, color) {
  try { chrome.action.setBadgeText({text}); chrome.action.setBadgeBackgroundColor({color}); } catch (e) {}
}

// Which ChatGPT account this Chrome profile is logged into and its picture quota (shown in Tidmunz).
let account = {email: "", images: "", reset: "", plan: "", used: "", checked: 0};
let accountRefresh = null;
async function accountJSON(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(url, {...options, signal: controller.signal});
    if (!response.ok) throw new Error(`account HTTP ${response.status}`);
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

async function chatgptAccount() {
  if (Date.now() - account.checked < 120000) return account;
  const next = {...account, checked: Date.now()};
  account.checked = next.checked;
  try {
    const session = await accountJSON("https://chatgpt.com/api/auth/session", {credentials: "include"});
    next.email = (session && session.user && session.user.email) || "";
    next.plan = (session && session.account && (session.account.planType || session.account.plan_type)) || "";
    if (session && session.accessToken) {
      // The same call chatgpt.com makes when it opens: it reports what is left of each limit.
      const init = await accountJSON("https://chatgpt.com/backend-api/conversation/init", {
        method: "POST", credentials: "include",
        headers: {"Authorization": "Bearer " + session.accessToken, "Content-Type": "application/json"},
        body: JSON.stringify({requested_default_model: null, conversation_id: null,
                              timezone_offset_min: new Date().getTimezoneOffset(), conversation_origin: null})});
      const image = (init.limits_progress || []).find(f => f.feature_name === "image_gen");
      const blocked = (init.blocked_features || []).find(f => f.name === "image_gen" || f.feature_name === "image_gen");
      if (blocked) { next.images = "0"; next.reset = blocked.resets_after || blocked.reset_after || ""; }
      else if (image) { next.images = String(image.remaining); next.reset = image.reset_after || ""; }
      // ChatGPT's "remaining" stays at the full number until the limit is near. The account's picture
      // library holds every picture made on it (from every PC), so it tells how many the last 24 hours took.
      try {
        const library = await accountJSON("https://chatgpt.com/backend-api/my/recent/image_gen?limit=200", {
          credentials: "include", headers: {"Authorization": "Bearer " + session.accessToken}});
        const since = Date.now() / 1000 - 86400;
        if (Array.isArray(library.items)) next.used = String(library.items.filter(i => (i.created_at || 0) > since).length);
      } catch (e) {}
    }
  } catch (e) {}
  account = next;
  return account;
}

async function loop() {
  if (running) return;
  running = true;
  const active = new Map();
  const workerKeys = ["workerTabId", "workerTabId2"];
  let imagePauseUntil = 0;
  const pauseImages = seconds => {
    imagePauseUntil = Math.max(imagePauseUntil, Date.now() + Math.max(30, Number(seconds) || 30) * 1000);
  };
  const drain = () => Promise.all([...active.values()].map(item => item.promise));
  async function perform(job, workerKey) {
    let result;
    try {
      if (job.type === "image" && Date.now() < imagePauseUntil) {
        result = {error: "ChatGPT image queue is cooling down — message not sent", provider_status: 429,
                  send_state: "not_sent", retry_after: Math.ceil((imagePauseUntil - Date.now()) / 1000)};
      } else {
        try {
          result = await runJob(job, workerKey, pauseImages);
        } catch (e) {
          if (!/No current window/i.test(String(e && e.message || e))) throw e;
          await ensureWindow();
          result = await runJob(job, workerKey, pauseImages);
        }
        // GPT answered with a question/text but no picture: tell it once, in the same chat, to draw now.
        // A policy refusal is left alone so the program can reword the prompt.
        if (job.type === "image" && result && result.done && !(result.images || []).length &&
            result.conversation_id && !/policy|นโยบาย|ละเมิด|violat|can.?t help|ไม่สามารถ/i.test(result.text || "")) {
          result = await runJob({...job, prompt: "สร้างรูปเลย ไม่ต้องถาม ใช้ข้อมูลที่ให้ไปแล้ว", images: [], files: [],
                                 conversation_id: result.conversation_id}, workerKey, pauseImages);
        }
      }
    } catch (e) {
      result = {error: String(e && e.message || e)};
    }
    if (job.type === "image" && result && result.provider_status === 429) pauseImages(result.retry_after);
    try { await relay("/result", {id: job.id, ...result}); } catch (e) {}
    if (!result || !result.error) {
      try {
        const saved = (await chrome.storage.local.get(workerKey))[workerKey];
        if (saved) await chrome.tabs.update(saved, {url: "https://chatgpt.com/"});
      } catch (e) {}
    }
    if (job.type === "image") account.checked = 0;
  }
  try {
    // Clean up worker tabs left by older extension builds before waiting for the next job.
    try {
      const saved = (await chrome.storage.local.get("workerTabId")).workerTabId;
      const tabs = await chrome.tabs.query({});
      if (saved || tabs.some(isWorkerTab)) await workerTab();
    } catch (e) {}
    for (;;) {
      if (active.size >= 2) await Promise.race([...active.values()].map(item => item.promise));
      let job = null;
      try {
        // Account/quota requests are optional display data, never a prerequisite for taking work.
        if (!accountRefresh && Date.now() - account.checked >= 120000) {
          accountRefresh = chatgptAccount().catch(() => {}).finally(() => { accountRefresh = null; });
        }
        const who = account;
        job = await relay(`/next?wait=5&v=${chrome.runtime.getManifest().version}&email=${encodeURIComponent(who.email)}` +
                          `&images=${encodeURIComponent(who.images)}&reset=${encodeURIComponent(who.reset)}&plan=${encodeURIComponent(who.plan)}` +
                          `&used=${encodeURIComponent(who.used)}`);
        badge("ON", "#10A37F");
      } catch (e) {
        badge("OFF", "#9CA3AF");  // Tidmunz is not open: look again later
        await sleep(5000);
        continue;
      }
      if (!job) continue;
      if (job.reload) { await drain(); chrome.runtime.reload(); return; }
      badge("…", "#F59E0B");
      if (job.type !== "image") {
        await drain();
        await perform(job, workerKeys[0]);
      } else {
        const sameChat = job.conversation_id && [...active.values()].find(item => item.cid === job.conversation_id);
        if (sameChat) await sameChat.promise;
        const key = workerKeys.find(candidate => !active.has(candidate));
        const promise = perform(job, key).finally(() => {
          active.delete(key);
          badge(active.size ? "…" : "ON", active.size ? "#F59E0B" : "#10A37F");
        });
        active.set(key, {promise, cid: job.conversation_id});
      }
      if (!active.size) badge("ON", "#10A37F");
    }
  } finally {
    await drain();
    running = false;
  }
}

// ── the ChatGPT tab ──
// A window for the work tab when the profile has none left (Chrome keeps running for the extension).
async function ensureWindow() {
  const wins = await chrome.windows.getAll();
  if (wins.length) return;
  const win = await chrome.windows.create({url: "https://chatgpt.com/", type: "normal", focused: false, populate: true});
  const tab = win && win.tabs && win.tabs.find(t => Number.isInteger(t.id));
  if (tab) {
    try { await chrome.tabs.update(tab.id, {pinned: true, autoDiscardable: false}); } catch (e) {}
    try { await chrome.storage.local.set({workerTabId: tab.id}); } catch (e) {}
  } else {
    try { await chrome.storage.local.remove("workerTabId"); } catch (e) {}
  }
}

function isWorkerTab(tab) {
  return /^https:\/\/chatgpt\.com\//.test(tab.url || tab.pendingUrl || "") &&
    tab.pinned === true && tab.autoDiscardable === false;
}

async function pruneWorkerTabs(keepId) {
  let tabs = [];
  try { tabs = await chrome.tabs.query({}); } catch (e) { return; }
  const saved = await chrome.storage.local.get(["workerTabId", "workerTabId2"]);
  const keep = new Set([keepId, saved.workerTabId, saved.workerTabId2]);
  await Promise.all(tabs.filter(tab => !keep.has(tab.id) && isWorkerTab(tab))
    .map(tab => chrome.tabs.remove(tab.id).catch(() => {})));
}

async function workerTab(workerKey = "workerTabId") {
  const previous = workerTab.pending || Promise.resolve();
  let release;
  workerTab.pending = new Promise(resolve => { release = resolve; });
  await previous;
  try {
    const assigned = await chrome.storage.local.get(["workerTabId", "workerTabId2"]);
    const saved = assigned[workerKey];
    const otherIds = new Set(Object.entries(assigned).filter(([key]) => key !== workerKey).map(([, id]) => id));
    let id = null;
    if (saved) {
      try {
        const tab = await chrome.tabs.get(saved);
        if (tab && /^https:\/\/chatgpt\.com\//.test(tab.url || tab.pendingUrl || "")) id = tab.id;
      } catch (e) {}
    }
    if (id === null) {
      // A previous extension build may have been reloaded: session storage is cleared but its
      // pinned, non-discardable worker tab survives. Adopt one and close only matching worker tabs.
      let tabs = [];
      try { tabs = await chrome.tabs.query({}); } catch (e) {}
      const oldWorkers = tabs.filter(tab => isWorkerTab(tab) && !otherIds.has(tab.id)).sort((a, b) =>
        Number(b.active) - Number(a.active) || (b.lastAccessed || 0) - (a.lastAccessed || 0));
      if (oldWorkers.length) id = oldWorkers[0].id;
    }
    if (id === null) {
      let tab;
      try {
        // Name the window: the program's Chrome window sits inside Tidmunz, and Chrome may not count it as the
        // "current" window, so a tab without a windowId fails with "No current window" although a window is open.
        const wins = await chrome.windows.getAll({windowTypes: ["normal"]});
        const where = wins.length ? {windowId: wins[0].id} : {};
        tab = await chrome.tabs.create({url: "https://chatgpt.com/", active: false, pinned: true, ...where});
      } catch (e) {
        if (!/No current window/i.test(String(e && e.message || e))) throw e;
        // The service worker can stay connected after the profile's last window closed.
        // Open a window in this extension's profile before sending anything to ChatGPT.
        const win = await chrome.windows.create({
          url: "https://chatgpt.com/", type: "normal", focused: false, incognito: false, populate: true,
        });
        tab = win && win.tabs && win.tabs[0];
        if (!tab || !Number.isInteger(tab.id))
          throw new Error("Cannot open ChatGPT work tab — open the program's Chrome window, then try again");
        await chrome.tabs.update(tab.id, {pinned: true});
      }
      id = tab.id;
    }
    // Chrome's memory saver must not unload (and reload) the work tab in the middle of a job.
    try { await chrome.tabs.update(id, {autoDiscardable: false}); } catch (e) {}
    await chrome.storage.local.set({[workerKey]: id});
    await pruneWorkerTabs(id);
    return id;
  } finally { release(); }
}

async function waitLoaded(tabId, limitMs) {
  const start = Date.now();
  for (;;) {
    await sleep(700);
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === "complete") return;
    if (Date.now() - start > limitMs) throw new Error("ChatGPT page did not load");
  }
}

// Chrome can refuse to navigate the work tab ("Navigation rejected": a leave-site prompt, a stuck or
// discarded page). Then drop that tab and open a fresh one, so one bad tab never fails every job.
async function freshTab(tabId, url, workerKey = "workerTabId") {
  try { await chrome.tabs.remove(tabId); } catch (e) {}
  try { await chrome.storage.local.remove(workerKey); } catch (e) {}
  const id = await workerTab(workerKey);
  await chrome.tabs.update(id, {url});
  return id;
}

async function openPage(tabId, url, retryWithFreshTab = true, isCancelled = () => false, workerKey = "workerTabId") {
  if (isCancelled()) throw new Error("ChatGPT operation cancelled");
  try {
    const current = await chrome.tabs.get(tabId);
    if (current.url !== url || current.pendingUrl) await chrome.tabs.update(tabId, {url});
  } catch (e) {
    if (!/navigation rejected|no tab with id|cannot access/i.test(String(e && e.message || e))) throw e;
    tabId = await freshTab(tabId, url, workerKey);
  }
  // Do not wait for "complete": ChatGPT keeps loading in the background; the composer is what counts.
  let seen = "", reloaded = false;
  const start = Date.now();
  while (Date.now() - start < 120000) {
    if (isCancelled()) throw new Error("ChatGPT operation cancelled");
    await sleep(1000);
    let ready = null;
    try {
      ready = await inPage(tabId, targetUrl => {
        const body = document.body ? document.body.innerText.slice(0, 300) : "";
        const page = (document.title + " | " + body).replace(/\s+/g, " ").slice(0, 160);
        if (/^\/auth\/(?:login|logout)(?:\/|$)/i.test(location.pathname)) return {state: "logged_out", page};
        if (/just a moment|verify you are human|ยืนยันว่าคุณเป็นมนุษย์|checking your browser/i.test(page)) return {state: "challenge", page};
        const target = new URL(targetUrl);
        if (location.origin !== target.origin || location.pathname !== target.pathname)
          return {state: "navigating", page};
        if (document.querySelector('form div.ProseMirror[role="textbox"]') ||
            document.querySelector('form #prompt-textarea[contenteditable="true"]')) return {state: "ok", page};
        return {state: "", page};
      }, [url]);
    } catch (e) {}  // still navigating
    if (ready && ready.state === "ok") return tabId;
    if (ready && ready.page) seen = ready.page;
    if (ready && ready.state === "challenge")
      throw new Error("ChatGPT asks to confirm you are human — open the program's Chrome window and confirm, then try again");
    if (ready && ready.state === "logged_out")
      throw new Error("ChatGPT is logged out in the program's Chrome window — log in, then try again");
    if (!reloaded && Date.now() - start > 45000) {  // stuck once: reload the tab and wait again
      reloaded = true;
      try { await chrome.tabs.reload(tabId); } catch (e) {}
    }
  }
  if (retryWithFreshTab) {
    if (isCancelled()) throw new Error("ChatGPT operation cancelled");
    const replacement = await freshTab(tabId, url, workerKey);
    return openPage(replacement, url, false, isCancelled, workerKey);
  }
  throw new Error("ChatGPT page not ready after 2 minutes — the window shows: " + (seen || "nothing"));
}

async function inPage(tabId, func, args) {
  const [{result}] = await chrome.scripting.executeScript({target: {tabId}, world: "MAIN", func, args: args || []});
  return result;
}

let imageSendTail = Promise.resolve();

async function runJob(job, workerKey = "workerTabId", onRateLimit = () => {}) {
  let cancelled = false, checking = false, finished = false, tabId = null;
  const report = async phase => {
    if (cancelled) throw new Error("ChatGPT operation cancelled");
    try {
      const reply = await relay("/progress", {id: job.id, phase});
      if (finished) return;
      if (reply && reply.active === false) {
        cancelled = true;
        throw new Error("ChatGPT operation cancelled");
      }
    } catch (e) { if (cancelled) throw e; }
  };
  const heartbeat = setInterval(async () => {
    if (checking || cancelled) return;
    checking = true;
    try { await report(); }
    catch (e) {
      // Reload only this job's dedicated worker tab to abort an in-page fetch/script after Stop.
      if (!finished && tabId !== null) try { await chrome.tabs.reload(tabId); } catch (ignored) {}
    } finally { checking = false; }
  }, 2000);
  try {
  await report("opening");
  tabId = await workerTab(workerKey);
  const url = job.conversation_id ? `https://chatgpt.com/c/${job.conversation_id}` : "https://chatgpt.com/";
  tabId = await openPage(tabId, url, true, () => cancelled, workerKey);
  // Messages already in an existing chat, read before sending: if the send's own answer is lost, a chat that
  // gained messages shows the job went out.
  let known = null;
  if (job.conversation_id) {
    try { known = await inPage(tabId, pageNodes, [job.conversation_id, job.type]); } catch (e) { known = null; }
  }
  let started = null;
  await report("sending");
  try {
    if (job.type === "image") {
      const previous = imageSendTail;
      let release;
      imageSendTail = new Promise(resolve => { release = resolve; });
      await previous;
      try {
        const tab = await chrome.tabs.get(tabId);
        await chrome.windows.update(tab.windowId, {state: "normal", focused: true});
        await chrome.tabs.update(tabId, {active: true});
        started = await inPage(tabId, pageSend, [job]);
      } finally { release(); }
    } else {
      // Text insertion also needs the foreground document, not merely editor.focus().
      const tab = await chrome.tabs.get(tabId);
      if (chrome.windows && chrome.windows.update)
        await chrome.windows.update(tab.windowId, {state: "normal", focused: true});
      if (chrome.tabs.update) await chrome.tabs.update(tabId, {active: true});
      started = await inPage(tabId, pageSend, [job]);
    }
  } catch (e) {
    // Script execution may have failed after the click. Treat delivery as ambiguous; do not resend.
    started = {error: "ChatGPT page stopped responding after the send attempt: " + String(e && e.message || e),
               send_state: "unknown"};
  }
  if (cancelled) return {error: "ChatGPT operation cancelled"};
  let deliveryBaseline = Array.isArray(known) ? known :
    (started && Array.isArray(started.before) ? started.before : null);
  const reconcileUnknownSend = async () => {
    if (!started || !started.error || started.send_state !== "unknown") return;
    if (!job.conversation_id) {
      // A new chat can confirm acceptance only after its new conversation contains this prompt.
      for (let i = 0; i < 10 && started.send_state === "unknown"; i++) {
        if (cancelled) return;
        await sleep(1500);
        try {
          const tab = await chrome.tabs.get(tabId);
          const created = (tab.url || "").match(/^https:\/\/chatgpt\.com\/c\/([0-9a-f-]{20,})(?:[/?#]|$)/);
          if (created) {
            const newJob = {...job, conversation_id: created[1]};
            const baseline = Array.isArray(deliveryBaseline) ? deliveryBaseline : [];
            const verified = await inPage(tabId, pageVerifyDelivery, [newJob, baseline]);
            if (verified && verified.state === "sent")
              started = {ok: true, before: baseline, oldPointers: [], dom_before: baseline,
                         conversation_id: created[1], user_message_id: verified.user_message_id,
                         send_state: "sent"};
            if (started.send_state === "sent") return;
          }
        } catch (e) {}
      }
    } else if (Array.isArray(deliveryBaseline)) {
      // Give the UI time to expose the new message, then verify its exact prompt server-side.
      for (let i = 0; i < 10 && started.send_state === "unknown"; i++) {
        if (cancelled) return;
        await sleep(1500);
        try {
          const now = await inPage(tabId, pageNodes, [job.conversation_id, job.type]);
          if (Array.isArray(now) && now.length > deliveryBaseline.length) break;
        } catch (e) {}
      }
    }
    if (started.send_state !== "unknown" || !Array.isArray(deliveryBaseline)) return;
    try {
      const verified = await inPage(tabId, pageVerifyDelivery, [job, deliveryBaseline]);
      if (verified && verified.state === "sent") {
        started = {ok: true, before: deliveryBaseline, oldPointers: [], dom_before: deliveryBaseline,
                   dom_mode: job.type === "chat", user_message_id: verified.user_message_id,
                   conversation_id: job.conversation_id || null, send_state: "sent"};
      } else if (verified && verified.state === "not_sent") {
        started = {error: "ChatGPT confirmed no new prompt reached the conversation; safe to retry once",
                   send_state: "not_sent", dom_before: deliveryBaseline};
      }
    } catch (e) {} // A failed or rate-limited verification remains unknown; never guess.
  };
  await reconcileUnknownSend();
  if (cancelled) return {error: "ChatGPT operation cancelled"};
  if (started && started.error && started.send_state === "not_sent" && started.code !== "prompt_too_long") {
    // Retry only after a failure before the click or an authoritative no-new-message check.
    try {
      await report("opening");
      tabId = await freshTab(tabId, url, workerKey);
      tabId = await openPage(tabId, url, true, () => cancelled, workerKey);
      await report("sending");
    } catch (e) {
      return {error: "Prompt was not sent; retry in a fresh ChatGPT tab failed: " + String(e && e.message || e),
              send_state: "not_sent"};
    }
    try {
      const tab = await chrome.tabs.get(tabId);
      if (chrome.windows && chrome.windows.update)
        await chrome.windows.update(tab.windowId, {state: "normal", focused: true});
      if (chrome.tabs.update) await chrome.tabs.update(tabId, {active: true});
      started = await inPage(tabId, pageSend, [job]);
    } catch (e) {
      started = {error: "ChatGPT page stopped responding after the retry send attempt: " + String(e && e.message || e),
                 send_state: "unknown"};
    }
    if (!job.conversation_id && started && Array.isArray(started.dom_before))
      deliveryBaseline = started.dom_before;
    await reconcileUnknownSend(); // confirm this one retry, but never send a third time
  }
  if (cancelled) return {error: "ChatGPT operation cancelled"};
  if (!started || started.error) return started || {error: "ChatGPT page did not answer (no message reached the chat)"};
  await report("waiting");
  // The job's state lives here, not in the page: a reloaded tab keeps going from the conversation itself.
  const state = {before: started.before, oldPointers: started.oldPointers, sentAt: Date.now(),
                 cid: started.conversation_id || job.conversation_id || null, idle: 0,
                 dom_before: started.dom_before || [], dom_mode: Boolean(started.dom_mode),
                 user_message_id: started.user_message_id || null};
  let deadline = Date.now() + (job.type === "chat" ? CHAT_JOB_LIMIT_MS : JOB_LIMIT_MS);
  const hardDeadline = state.sentAt + JOB_LIMIT_MS;
  let throttles = 0;
  while (Date.now() < deadline) {
    if (cancelled) return {error: "ChatGPT operation cancelled"};
    await sleep(3000);  // short calls keep this worker alive while ChatGPT works
    let result = null;
    try {
      const tab = await chrome.tabs.get(tabId);
      if (tab.status !== "complete") continue;  // reloading: look again when it is back
      result = await inPage(tabId, pagePoll, [job.type, state]);
    } catch (e) {
      continue;  // the page was navigating; the conversation keeps the answer
    }
    if (!result) continue;
    if (result.cid) state.cid = result.cid;
    if (result.idle != null) state.idle = result.idle;
    if (result.dom_reply_id != null) {
      state.dom_reply_id = result.dom_reply_id;
      state.dom_reply_text = result.dom_reply_text;
    }
    if (result.rate_limited) {
      // A prompt already went out: wait and read this same conversation, never call pageSend again.
      const seconds = Math.max(Number(result.retry_after) || 0, Math.min(300, 30 * 2 ** Math.min(throttles++, 4)));
      if (job.type === "image") onRateLimit(seconds);
      // ponytail: fixed wall-clock limit; 429 backoff must not extend a sent job.
      let left = Math.min(seconds * 1000, Math.max(0, deadline - Date.now()));
      while (left > 0) {
        if (cancelled) return {error: "ChatGPT operation cancelled"};
        let progress = null;
        try { progress = await relay("/progress", {id: job.id, retry_after: Math.ceil(left / 1000)}); } catch (e) {}
        if (progress && progress.active === false) return {error: "ChatGPT cooldown recovery interrupted — prompt already sent", provider_status: 429, send_state: "sent"};
        await chrome.tabs.get(tabId);  // Keep this MV3 worker alive during long provider cooldowns.
        const step = Math.min(left, 5000);
        await sleep(step);
        left -= step;
      }
      continue;
    }
    throttles = 0;
    if (result.done || result.error) return result;
    // Only evidence from this reply extends the idle limit; errors/429 do not.
    if (job.type === "chat" && result.generating)
      deadline = Math.min(hardDeadline, Date.now() + CHAT_JOB_LIMIT_MS);
  }
  // One final read of the same conversation can recover a reply completed at the boundary.
  if (job.type === "chat" && !cancelled && throttles === 0) {
    try {
      const result = await inPage(tabId, pagePoll, [job.type, state]);
      if (result && result.done) return result;
    } catch (e) {}
  }
  if (job.type === "chat" && Date.now() >= hardDeadline)
    return {error: "ChatGPT took longer than 12 minutes; original prompt may have been sent; do not resend", send_state: "sent", conversation_id: state.cid};
  return {error: job.type === "chat" ? "ChatGPT response timed out after 3 minutes; original prompt may have been sent; do not resend" : "ChatGPT took longer than 12 minutes"};
  } finally {
    finished = true;
    clearInterval(heartbeat);
  }
}

// ── functions below run inside the chatgpt.com page ──
async function pageNodes(cid, kind) {
  if (kind === "chat" && location.pathname === `/c/${cid}`) {
    const nodes = [...document.querySelectorAll('[data-message-id][data-message-author-role]')];
    if (["user", "assistant"].every(role => nodes.some(n => n.getAttribute("data-message-author-role") === role)))
      return nodes.map(n => n.getAttribute("data-message-id"));
  }
  const session = await (await fetch("/api/auth/session")).json();
  const r = await fetch(`/backend-api/conversation/${cid}`, {headers: {Authorization: "Bearer " + session.accessToken}});
  if (!r.ok) return null;
  return Object.keys((await r.json()).mapping || {});
}

// A clicked Send with no visible confirmation is ambiguous. Retry only when two fresh,
// identical conversation reads prove no prompt arrived and the same composer draft is still ready.
async function pageVerifyDelivery(job, before) {
  const previous = Array.isArray(before) ? before : [];
  const normalize = value => String(value || "").normalize("NFKC").replace(/[\s\p{Cf}]+/gu, "");
  const expected = normalize(job.prompt);
  if (!expected) return {state: "unknown"};
  const routeCid = (location.pathname || "").match(/^\/c\/([0-9a-f-]{20,})(?:[/?#]|$)/i);
  const cid = String(job.conversation_id || (routeCid && routeCid[1]) || "");
  const domNodes = [...document.querySelectorAll('[data-message-id][data-message-author-role]')];
  const domMatch = domNodes.find(node => node.getAttribute("data-message-author-role") === "user" &&
    !previous.includes(node.getAttribute("data-message-id") || "") &&
    normalize(node.innerText || node.textContent || "").includes(expected));
  if (domMatch) return {state: "sent", user_message_id: domMatch.getAttribute("data-message-id")};
  if (cid) {
    if (job.conversation_id && location.pathname !== `/c/${cid}`) return {state: "unknown"};
    for (let attempt = 0; attempt < 2; attempt++) {
      if (attempt) await new Promise(resolve => setTimeout(resolve, 3000));
      let entries;
      try {
        const session = await (await fetch("/api/auth/session", {cache: "no-store"})).json();
        if (!session || !session.accessToken) return {state: "unknown"};
        const response = await fetch(`/backend-api/conversation/${cid}`, {
          cache: "no-store", headers: {Authorization: "Bearer " + session.accessToken}
        });
        if (!response.ok) return {state: "unknown", provider_status: response.status};
        const data = await response.json();
        entries = Object.entries(data.mapping || {}).filter(([, node]) => node && node.message);
      } catch (e) { return {state: "unknown"}; }
      const fresh = entries.filter(([id]) => !previous.includes(id));
      const matchingUser = fresh.find(([, node]) => {
        if (!node.message.author || node.message.author.role !== "user") return false;
        const parts = node.message.content && node.message.content.parts || [];
        return normalize(parts.filter(part => typeof part === "string").join("\n")).includes(expected);
      });
      if (matchingUser) return {state: "sent", user_message_id: matchingUser[0]};
      // Any unexplained change is ambiguous; only two unchanged snapshots can prove not-sent.
      if (fresh.length || entries.length !== previous.length) return {state: "unknown"};
    }
    // A newly created conversation without the exact prompt is still ambiguous.
    if (!job.conversation_id && routeCid) return {state: "unknown"};
  } else {
    // The new-chat page has no authoritative conversation read; never retry an ambiguous click.
    return {state: "unknown"};
  }

  const editor = document.querySelector('form div.ProseMirror[role="textbox"]') ||
    document.querySelector('form #prompt-textarea[contenteditable="true"]');
  const form = editor && editor.closest("form");
  const send = form && form.querySelector('button[type="submit"]');
  const draft = normalize(editor && (editor.innerText || editor.textContent || ""));
  const buttons = form ? [...form.querySelectorAll("button")] : [];
  const busy = buttons.some(button => button.getAttribute("data-testid") === "stop-button" ||
    /^(stop|หยุด|停止|detener|arrêter|stopp)/i.test((button.getAttribute("aria-label") || "").trim()));
  const uploading = Boolean(form && form.querySelector('[role="progressbar"], [aria-busy="true"], circle[stroke-dasharray]'));
  const attached = buttons.filter(button => /^(ลบ|remove)\s/i.test((button.getAttribute("aria-label") || "").trim())).length;
  const expectedAttachments = (job.images || []).length + (job.files || []).length;
  if (editor && editor.isConnected !== false && form && form.isConnected !== false &&
      send && send.isConnected !== false && !send.disabled && !busy && !uploading &&
      draft === expected && attached >= expectedAttachments)
    return {state: "not_sent"};
  return {state: "unknown"};
}

async function pageSend(job) {
  let sendAttempted = false;
  let sendBaseline = null;
  let sendDomBaseline = null;
  try {
    return await pageSendInner(job, (baseline, domBaseline) => {
      sendAttempted = true; sendBaseline = baseline; sendDomBaseline = domBaseline;
    });
  } catch (e) {
    return {error: "ChatGPT page error while sending: " + (e && e.message ? e.message : String(e)),
            send_state: sendAttempted ? "unknown" : "not_sent",
            ...(Array.isArray(sendBaseline) ? {before: sendBaseline} : {}),
            ...(Array.isArray(sendDomBaseline) ? {dom_before: sendDomBaseline} : {})};
  }
  async function pageSendInner(job, markSendAttempted) {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  let session = null;
  let before = [];  // messages already in the chat: everything else is this job's answer
  const oldPointers = [];  // pictures already in the chat (earlier pictures, references): never the answer
  const domNodes = typeof document.querySelectorAll === "function"
    ? [...document.querySelectorAll('[data-message-id][data-message-author-role]')] : [];
  const domBefore = domNodes.map(n => n.getAttribute("data-message-id"));
  const domReady = job.type === "chat" && (!job.conversation_id || (
    location.pathname === `/c/${job.conversation_id}` &&
    ["user", "assistant"].every(role => domNodes.some(n => n.getAttribute("data-message-author-role") === role))));
  if (!domReady || !job.conversation_id) {
    session = await (await fetch("/api/auth/session")).json();
    if (!session || !session.accessToken) return {error: "ChatGPT is logged out in Chrome — log in, then try again"};
  }
  if (domReady) before = domBefore;
  if (job.conversation_id && !domReady) {
    // A just-created chat may not yet be readable after navigation. Retry GET
    // only, never send the prompt twice or silently start another chat.
    let check;
    for (let attempt = 0; attempt < 3; attempt++) {
      check = await fetch(`/backend-api/conversation/${job.conversation_id}`,
        {cache: "no-store", headers: {Authorization: "Bearer " + session.accessToken}});
      if (check.status !== 404 || attempt === 2) break;
      await sleep(1500);
    }
    if (check.status === 404) return {error: "ChatGPT conversation failed: 404 — not found for this account", not_found: true};
    if (!check.ok) {
      const raw = check.headers && check.headers.get("Retry-After");
      const retry = raw ? (/^\d+(\.\d+)?$/.test(raw.trim()) ? Number(raw) : (Date.parse(raw) - Date.now()) / 1000) : 0;
      return {error: `ChatGPT conversation read failed: HTTP ${check.status} — message not sent`,
              provider_status: check.status, send_state: "not_sent", retry_after: Number.isFinite(retry) ? Math.max(0, retry) : 0};
    }
    const data = await check.json();
    before = Object.keys(data.mapping || {});
    for (const node of Object.values(data.mapping || {}))
      for (const part of (node.message && node.message.content && node.message.content.parts) || [])
        if (part && typeof part === "object" && part.asset_pointer) oldPointers.push(part.asset_pointer);
  }
  // ChatGPT can replace the composer between openPage's readiness check and this script.
  // Re-query briefly instead of dereferencing a missing/stale editor and failing every resume.
  let editor = null, form = null;
  const composerUntil = Date.now() + 15000;
  while (Date.now() < composerUntil) {
    const candidate = document.querySelector('form div.ProseMirror[role="textbox"]') ||
      document.querySelector('form #prompt-textarea[contenteditable="true"]');
    const candidateForm = candidate && candidate.closest("form");
    if (candidate && candidate.isConnected && candidateForm && candidateForm.isConnected) {
      editor = candidate;
      form = candidateForm;
      break;
    }
    await sleep(250);
  }
  if (!editor || !form)
    return {error: "ChatGPT prompt box is still loading or changed — wait for the composer in the program's Chrome window, then retry",
            send_state: "not_sent"};
  const images = job.images || [];
  const files = job.files || [];
  const expectedAttachments = images.length + files.length;
  if (expectedAttachments) {
    const inputs = [...document.querySelectorAll('input[type=file]')];
    const input = (files.length && inputs.find(i => i.multiple &&
      (!i.accept || /text|json|pdf|doc|\.txt/i.test(i.accept))))
      || inputs.find(i => i.multiple && /image/.test(i.accept))
      || inputs.find(i => i.multiple);
    if (!input) return {error: "ChatGPT file input not found", code: "file_upload_unavailable", send_state: "not_sent"};
    const dt = new DataTransfer();
    images.forEach((data, n) => {
      const [head, b64] = data.split(",");
      const mime = (head.match(/data:([^;]+)/) || [])[1] || "image/png";
      const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
      dt.items.add(new File([bytes], `ref_${n + 1}.${mime.split("/")[1] || "png"}`, {type: mime}));
    });
    files.forEach((item, n) => {
      const b64 = String(item && item.file_data || "");
      const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
      const name = String(item && item.filename || `attachment_${n + 1}.txt`).replace(/[\\/:*?"<>|]/g, "_");
      const mime = String(item && item.mime_type || "text/plain");
      dt.items.add(new File([bytes], name, {type: mime}));
    });
    input.files = dt.files;
    input.dispatchEvent(new Event("change", {bubbles: true}));
    // Newer ChatGPT builds can ignore the hidden input: no chip appears and Send waits forever.
    // Fall back to pasting the same files into the composer, which ChatGPT always accepts.
    const chips = () => [...form.querySelectorAll("button")].filter(b =>
      /^(ลบ|remove)\s/i.test((b.getAttribute("aria-label") || "").trim())).length;
    const pasteBy = Date.now() + 8000;
    while (!chips() && Date.now() < pasteBy) await sleep(500);
    if (!chips()) {
      editor.focus();
      editor.dispatchEvent(new ClipboardEvent("paste", {clipboardData: dt, bubbles: true, cancelable: true}));
    }
  }
  editor.focus();
  document.execCommand("selectAll", false, null);
  const insertAccepted = document.execCommand("insertText", false, job.prompt);
  // Wait until every picture sits in the composer and has finished uploading. The send button is
  // enabled by the text alone, so pressing it early sent the words without the picture (an image
  // check then answered "all fine" about a sheet it never saw).
  const until = Date.now() + 120000;
  let send = null, attached = 0, settled = 0;
  while (Date.now() < until) {
    await sleep(800);
    attached = [...form.querySelectorAll("button")].filter(b =>
      /^(ลบ|remove)\s/i.test((b.getAttribute("aria-label") || "").trim())).length;
    const uploading = form.querySelector('[role="progressbar"], [aria-busy="true"], circle[stroke-dasharray]');
    send = form.querySelector('button[type="submit"]');
    const ready = send && !send.disabled && attached >= expectedAttachments && !uploading;
    settled = ready ? settled + 1 : 0;
    if (settled >= 2) break;  // ready twice in a row: the upload is really done
  }
  if (expectedAttachments && attached < expectedAttachments)
    return {error: `ChatGPT did not take the attached files (${attached}/${expectedAttachments} attached) — not sent`,
            code: "file_upload_unavailable", send_state: "not_sent"};
  if (!send || send.disabled)
    return {error: "ChatGPT did not accept the attachments / prompt in time", send_state: "not_sent"};
  // ChatGPT can replace the composer while attachments finish uploading. Resolve the live
  // editor/form/button again immediately before clicking so a detached stale button cannot eat the send.
  const latestEditor = document.querySelector('form div.ProseMirror[role="textbox"]') ||
    document.querySelector('form #prompt-textarea[contenteditable="true"]');
  const latestForm = latestEditor && latestEditor.closest("form");
  const latestSend = latestForm && latestForm.querySelector('button[type="submit"]');
  const normalizePrompt = str => String(str || "").normalize("NFKC").replace(/[\s\p{Cf}]+/gu, "");
  const latestDraft = normalizePrompt(latestEditor && (latestEditor.innerText || latestEditor.textContent || ""));
  const expectedPrompt = normalizePrompt(job.prompt);
  const latestButtons = latestForm ? [...latestForm.querySelectorAll("button")] : [];
  const latestAttached = latestButtons.filter(b => /^(ลบ|remove)\s/i.test((b.getAttribute("aria-label") || "").trim())).length;
  const latestUploading = latestForm && latestForm.querySelector('[role="progressbar"], [aria-busy="true"], circle[stroke-dasharray]');
  const latestBusy = latestButtons.some(b => b.getAttribute("data-testid") === "stop-button" ||
    /^(stop|หยุด|停止|detener|arrêter|stopp)/i.test((b.getAttribute("aria-label") || "").trim()));
  if (!latestEditor || latestEditor.isConnected === false || !latestForm || latestForm.isConnected === false ||
      !latestSend || latestSend.isConnected === false || latestSend.disabled || latestUploading || latestBusy ||
      latestDraft !== expectedPrompt || latestAttached < expectedAttachments)
    return {error: "ChatGPT composer changed before Send — prompt not sent; retrying in a fresh tab is safe",
            send_state: "not_sent"};
  editor = latestEditor;
  form = latestForm;
  send = latestSend;
  const tooLongSelectors = '[role="alert"], [role="status"], [aria-live], [data-sonner-toast], [data-testid*="toast"]';
  const tooLongPattern = /ข้อความ(?:ที่คุณส่ง)?ยาวเกินไป|(?:your\s+)?message\s+(?:is|was)\s+too\s+long|message.{0,40}too\s+long/i;
  const bodyBeforeSend = String(document.body && document.body.innerText || "");
  const currentAlerts = () => typeof document.querySelectorAll === "function"
    ? [...document.querySelectorAll(tooLongSelectors)] : [];
  const oldAlerts = new Set(currentAlerts().map(node =>
    String(node.innerText || node.textContent || "").trim()));
  const promptTooLongNotice = () => {
    for (const node of currentAlerts()) {
      const text = String(node.innerText || node.textContent || "").trim();
      if (text && !oldAlerts.has(text) && tooLongPattern.test(text)) return text;
    }
    const bodyText = String(document.body && document.body.innerText || "");
    if (bodyText !== bodyBeforeSend && !tooLongPattern.test(bodyBeforeSend) && tooLongPattern.test(bodyText)) {
      const match = bodyText.match(tooLongPattern);
      return match ? match[0] : "ChatGPT rejected the message because it was too long";
    }
    return "";
  };
  markSendAttempted(before, domBefore);
  send.click();
  let sendClicks = 1;
  let userMessageId = null;
  if (job.type === "chat" || job.type === "image") {
    const previous = new Set([...before, ...domBefore]);
    const normalized = str => str.normalize("NFKC").replace(/[\s\p{Cf}]+/gu, "");
    const expected = normalized(String(job.prompt || ""));
    const findUserMessage = () => {
      const nodes = [...document.querySelectorAll('[data-message-id][data-message-author-role]')];
      const anchor = domBefore.length ? nodes.findIndex(n => n.getAttribute("data-message-id") === domBefore[domBefore.length - 1]) : -1;
      for (const node of nodes.slice(anchor + 1)) {
        const id = node.getAttribute("data-message-id");
        if (!id || previous.has(id) || node.getAttribute("data-message-author-role") !== "user") continue;
        if (!expected || !normalized(node.innerText || node.textContent || "").includes(expected)) continue;
        return id;
      }
      return null;
    };
    const waitForUserMessage = async () => {
      for (let attempt = 0; attempt < 60 && !userMessageId; attempt++) {
        await sleep(250);
        const rejected = promptTooLongNotice();
        if (rejected) return rejected;
        userMessageId = findUserMessage();
      }
      return "";
    };
    const rejection = await waitForUserMessage();
    if (!userMessageId && rejection)
      return {error: "ChatGPT rejected the prompt because it was too long: " + rejection,
              code: "prompt_too_long", send_state: "not_sent", before, dom_before: domBefore};
    if (!userMessageId) {
      // A failed confirmation after the click is ambiguous. Never click Send again here;
      // runJob may retry only if this function proved the prompt was never sent.
    }
    if (!userMessageId) {
      const currentEditor = document.querySelector('form div.ProseMirror[role="textbox"]') ||
        document.querySelector('form #prompt-textarea[contenteditable="true"]');
      const currentForm = currentEditor && currentEditor.closest("form");
      const currentSend = currentForm && currentForm.querySelector('button[type="submit"]');
      const draft = String(currentEditor && (currentEditor.innerText || currentEditor.textContent || "") || "");
      const nodes = [...document.querySelectorAll('[data-message-id][data-message-author-role]')];
      const freshUsers = nodes.filter(n => n.getAttribute("data-message-author-role") === "user" &&
        !previous.has(n.getAttribute("data-message-id")));
      const currentButtons = currentForm ? [...currentForm.querySelectorAll("button")] : [];
      const activeResponse = currentButtons.some(b => b.getAttribute("data-testid") === "stop-button" ||
        /^(stop|หยุด|停止|detener|arrêter|stopp)/i.test((b.getAttribute("aria-label") || "").trim()));
      const uploadPending = Boolean(currentForm && currentForm.querySelector(
        '[role="progressbar"], [aria-busy="true"], circle[stroke-dasharray]'));
      const attachedNow = currentButtons.filter(b => /^(ลบ|remove)\s/i.test((b.getAttribute("aria-label") || "").trim())).length;
      const draftMatches = normalized(draft) === expected;
      const textMatches = freshUsers.some(n => normalized(n.textContent || "").includes(expected));
      const deliveryDebug = {
                prompt_chars: String(job.prompt || "").length, draft_chars: draft.length,
                draft_matches: draftMatches, insert_accepted: insertAccepted === true,
                send_clicks: sendClicks, document_focused: typeof document.hasFocus === "function" && document.hasFocus(),
                editor_focused: document.activeElement === currentEditor, page_visible: document.visibilityState === "visible",
                existing_chat: Boolean(job.conversation_id), chat_route: /^\/c\//.test(location.pathname),
                before_nodes: domBefore.length, current_nodes: nodes.length, new_user_nodes: freshUsers.length,
                role_only_users: document.querySelectorAll('[data-message-author-role="user"]').length,
                text_content_matches: textMatches, active_response: activeResponse, upload_pending: uploadPending,
                attached_images: attachedNow, expected_images: images.length,
                expected_attachments: expectedAttachments,
                send_button_found: Boolean(currentSend), send_disabled: Boolean(currentSend && currentSend.disabled),
                send_is_expected: Boolean(currentSend && (currentSend.id === "composer-submit-button" ||
                  typeof currentSend.getAttribute === "function" && currentSend.getAttribute("data-testid") === "send-button")),
              };
      return {error: "ChatGPT page did not answer: the prompt was not confirmed in the conversation; no reply wait started; delivery=" + JSON.stringify(deliveryDebug),
              send_state: "unknown", delivery_debug: deliveryDebug, before, dom_before: domBefore};
    }
  }
  return {ok: true, before, oldPointers, dom_before: domBefore,
          dom_mode: domReady && Boolean(userMessageId), user_message_id: userMessageId};
  }
}

async function pagePoll(kind, state) {
  const busy = [...document.querySelectorAll("form button, button[data-testid]")].some(b =>
    b.getAttribute("data-testid") === "stop-button" ||
    /^(stop|หยุด|停止|detener|arrêter|stopp)/i.test((b.getAttribute("aria-label") || "").trim()));
  const match = location.pathname.match(/\/c\/([0-9a-f-]{20,})/);
  const cid = state.cid || (match ? match[1] : null);
  const idle = busy ? 0 : (state.idle || 0) + 1;
  const elapsed = (Date.now() - state.sentAt) / 1000;
  if (!cid || elapsed < 6) return {done: false, cid, idle};

  if (kind === "chat" && state.user_message_id) {
    const previous = new Set([...(state.before || []), ...(state.dom_before || [])]);
    const nodes = [...document.querySelectorAll('[data-message-id][data-message-author-role]')];
    const userIndex = nodes.findIndex(n => n.getAttribute("data-message-id") === state.user_message_id &&
      n.getAttribute("data-message-author-role") === "user");
    // ChatGPT can replace a message ID during rerender. Fall back to any assistant message
    // added since send, instead of staying in DOM mode forever with no API fallback.
    const freshAssistants = nodes.filter(n => n.getAttribute("data-message-author-role") === "assistant" &&
      !previous.has(n.getAttribute("data-message-id")));
    const candidates = userIndex >= 0
      ? nodes.slice(userIndex + 1).filter(n => n.getAttribute("data-message-author-role") === "assistant")
      : freshAssistants;
    for (const node of candidates.reverse()) {
      const id = node.getAttribute("data-message-id");
      if (!id || previous.has(id) || node.getAttribute("data-message-author-role") !== "assistant") continue;
      const blocks = [...node.querySelectorAll(".markdown")];
      const block = blocks[blocks.length - 1] || node;
      const codes = [...block.querySelectorAll("pre code")];
      const code = codes.length ? (codes[codes.length - 1].textContent || "").trim() : "";
      const text = (/^[{\[]/.test(code) ? code : (block.innerText || block.textContent || "")).trim();
      if (!text) continue;
      const stable = state.dom_reply_id === id && state.dom_reply_text === text;
      if (!stable) return {done: false, cid, idle, generating: true, dom_reply_id: id, dom_reply_text: text};
      // A complete JSON object is a finished reply even if ChatGPT's Stop button is stale.
      let completeJson = false;
      try { const value = JSON.parse(text); completeJson = Boolean(value && typeof value === "object"); } catch (e) {}
      if (busy && !completeJson) return {done: false, cid, idle, generating: true, dom_reply_id: id, dom_reply_text: text};
      return {done: true, text, images: [], conversation_id: cid, message_id: id, source: "chatgpt_page"};
    }
    // Prefer the visible UI, but if it has no assistant node for 30s, recover from the conversation API.
    // This avoids both tight API polling and an unbounded wait on a missing/replaced DOM node.
    if (state.dom_mode && elapsed < 30) return {done: false, cid, idle};
  }

  const token = (await (await fetch("/api/auth/session")).json()).accessToken;
  const auth = {headers: {Authorization: "Bearer " + token}};
  const response = await fetch(`/backend-api/conversation/${cid}`, {...auth, cache: "no-store"});
  if (!response.ok) {
    if (response.status === 429) {
      const raw = response.headers && response.headers.get("Retry-After");
      const retry = raw ? (/^\d+(\.\d+)?$/.test(raw.trim()) ? Number(raw) : (Date.parse(raw) - Date.now()) / 1000) : 0;
      return {done: false, cid, idle, rate_limited: true,
              retry_after: Number.isFinite(retry) ? Math.max(0, retry) : 0};
    }
    if (response.status === 404 && elapsed < 30) return {done: false, cid, idle};
    return {error: `ChatGPT conversation read failed: HTTP ${response.status} — reply not recovered`,
            provider_status: response.status};
  }
  const data = await response.json();
  const nodes = Object.entries(data.mapping || {}).filter(([id, n]) => n.message && !state.before.includes(id))
    .map(([, n]) => n.message).sort((a, b) => (a.create_time || 0) - (b.create_time || 0));
  const skip = new Set(state.oldPointers || []);
  const pointers = [];
  let text = "";
  for (const m of nodes) {
    const role = m.author && m.author.role;
    const parts = (m.content && m.content.parts) || [];
    if (role === "user") {  // the pictures we attached come back in answers too
      for (const part of parts) if (part && typeof part === "object" && part.asset_pointer) skip.add(part.asset_pointer);
      continue;
    }
    for (const part of parts)
      if (part && typeof part === "object" && part.asset_pointer && !pointers.includes(part.asset_pointer)) pointers.push(part.asset_pointer);
    if (role === "assistant" && m.content && m.content.content_type === "text") {
      const t = parts.filter(p => typeof p === "string").join("\n").trim();
      if (t) text = t;
    }
    if (m.content && m.content.content_type === "system_error") text = (m.content.text || text);
  }
  // Do not turn an empty or still-streaming conversation snapshot into a completed reply.
  if (kind === "chat") {
    const last = [...nodes].reverse().find(m => m.author && m.author.role === "assistant" &&
      m.content && m.content.content_type === "text");
    if (!text || !last || last.status !== "finished_successfully" || last.end_turn === false)
      return {done: false, cid, idle, generating: Boolean(last && last.status === "in_progress")};
  }
  const fresh = pointers.filter(p => !skip.has(p));
  // A picture can still be drawing after the reply text: give it time unless ChatGPT answered instead.
  // ponytail: a text-first reply ("generating…") used to end the job with no picture; now it waits too.
  // A refusal still returns after 4 min; raise this if real pictures arrive later than that.
  if (kind === "image" && !fresh.length && elapsed < 240) return {done: false, cid, idle};
  const images = [];
  for (const pointer of (kind === "image" ? fresh.slice(-1) : fresh)) {  // one picture per job: the newest
    const id = pointer.replace(/^[a-z-]+:\/\//, "");
    const info = await (await fetch(`/backend-api/files/download/${id}?conversation_id=${cid}&inline=false`, auth)).json();
    if (!info.download_url) continue;
    const blob = await (await fetch(info.download_url)).blob();
    images.push(await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result); fr.readAsDataURL(blob); }));
  }
  return {done: true, text, images, conversation_id: cid, message_id: data.current_node || null};
}

chrome.alarms.create("tidmunz-wake", {periodInMinutes: 0.5});
chrome.alarms.onAlarm.addListener(() => loop());
chrome.runtime.onStartup.addListener(() => loop());
chrome.runtime.onInstalled.addListener(() => loop());
loop();
