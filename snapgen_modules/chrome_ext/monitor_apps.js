// Native ChatGPT app mentions for Tidmunz's existing Chrome-profile extension.
// This function is serialized by chrome.scripting.executeScript into chatgpt.com.
// It MUST use the real composer/menu, never inject plain Markdown @bot names.
// Any ambiguous send remains unverified; the caller must not retry blindly.
self.tmMonitorComposeWithApps = async function (payload) {
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const editor = () => [...document.querySelectorAll('form [contenteditable="true"]')]
    .find(e => e.closest("form") && visible(e));
  const expected = [
    ["Tidmunz Studio AI Operator", "app://plugins_6aebd38bc5588191808c3cbd710ded69"],
    ["Dino Bot Tunnel", "app://asdk_app_6afac8c38ba88191afe3e6f5a07f43eb"],
  ];
  const visible = node => {
    if (!node || typeof node.getBoundingClientRect !== "function") return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  if (location.hostname !== "chatgpt.com")
    return {attempted:false,error:"Not chatgpt.com"};
  if (payload.cid && !location.pathname.endsWith("/c/" + payload.cid))
    return {attempted:false,error:"Wrong conversation"};
  if (!payload.cid && location.pathname !== "/")
    return {attempted:false,error:"Not a blank ChatGPT chat"};
  for (let attempt=0; attempt<30 && !editor(); attempt++) await sleep(400);
  const input=editor();
  if (!input) return {attempted:false,error:"ChatGPT composer not available"};
  if ((input.innerText || "").trim())
    return {attempted:false,error:"ChatGPT composer contains a draft"};
  const addButton = () => [...document.querySelectorAll("button")].find(b =>
    /(เพิ่มไฟล์และอื่นๆ|add files and more|add files)/i.test(b.getAttribute("aria-label") || "") && visible(b));
  async function selectFromMenu(name) {
    const plus=addButton();
    if (!plus) return false;
    plus.click();
    await sleep(400);
    const findChoice=()=>[...document.querySelectorAll("button")].find(el => {
      const value=(el.innerText || "").trim();
      return visible(el) && value.startsWith(name) && value.length < name.length*3 + 12;
    });
    let button=findChoice();
    if (!button && name === "Dino Bot Tunnel") {
      // In the actual ChatGPT UI, Tidmunz is available via the Plus menu,
      // while Dino is surfaced by typing @dino into the same real composer.
      document.dispatchEvent(new KeyboardEvent("keydown",{
        key:"Escape",code:"Escape",bubbles:true
      }));
      const paragraph=input.querySelector("p:last-child") || input;
      const selection=window.getSelection(),range=document.createRange();
      range.selectNodeContents(paragraph);range.collapse(false);
      selection.removeAllRanges();selection.addRange(range);
      input.focus();
      if (!document.execCommand("insertText",false," @dino")) return false;
      await sleep(600);
      button=findChoice();
    }
    if (!button) return false;
    button.click();
    await sleep(350);
    return true;
  }
  for (const [name,path] of expected) {
    const ok=await selectFromMenu(name);
    if (!ok)
      return {attempted:false,error:"App not selectable in ChatGPT menu: "+name};
    const actual=[...input.querySelectorAll("[app-mention-path]")].map(el => el.getAttribute("app-mention-path"));
    if (!actual.includes(path))
      return {attempted:false,error:"ChatGPT did not create a real app mention: "+name};
  }
  const apps=[...input.querySelectorAll("[app-mention-path]")].map(el => el.getAttribute("app-mention-path"));
  if (!expected.every(([,path])=>apps.includes(path)) || apps.length !== 2)
    return {attempted:false,error:"Required two-app binding not verified"};
  const last=input.querySelector("p:last-child") || input;
  const selection=window.getSelection(), range=document.createRange();
  range.selectNodeContents(last);range.collapse(false);
  selection.removeAllRanges();selection.addRange(range);
  input.focus();
  if (!document.execCommand("insertText",false," "+String(payload.prompt||"")))
    return {attempted:false,error:"Cannot enter monitor instructions"};
  if (!(input.innerText||"").includes(String(payload.marker||"")))
    return {attempted:false,error:"Monitor marker missing after editing"};
  const form=input.closest("form");
  const send=[...(form ? form.querySelectorAll("button") : [])].find(el =>
    !el.disabled && visible(el) && (
      ["ส่ง","send","send message"].includes(String(el.getAttribute("aria-label")||"").toLowerCase()) ||
      el.getAttribute("data-testid") === "send-button"
    ));
  if (!send) return {attempted:false,error:"ChatGPT Send control not available"};
  send.click();
  return {attempted:true,appMentionsVerified:true,appCount:apps.length};
};
